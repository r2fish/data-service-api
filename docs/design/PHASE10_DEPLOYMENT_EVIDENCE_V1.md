# フェーズ10 実施設計: 配備面の証拠 (契約 1.8.0「資源制限の適用単位」)

## 0. 版数・位置づけ

- 版数: **v1.3 (2026-09-08)**。**改版履歴**: **v1.0 (2026-09-08)** 起草初稿 (設計レビュー 1 / 2 の対象)。**v1.1 (2026-09-08)** — **設計レビュー 1 / 2 (2026-09-08) の反映。D-1 を再定義し (A-1 socket adapter は既存 HTTP adapter の composition を継承する / A-2 本番 composition root の証拠は新条件 C-26 が担う)、C-26 を新設した。** **v1.2 (2026-09-08)** — **差分レビュー (2026-09-08) の反映: D-10 の付け替え (L9-15 の閉止は control 面 discovery を駆動条件にする形へ)、基底 http adapter の hook 抽出、C-26 の xdist group と (4) の主張の縮小、harness 全体の起動予算。** **v1.3 (2026-09-08)** — **依頼者が提示した 2 本目の外部レビュー (基準 main `b16afdd`) の監督検証の反映** (依頼者裁定 2026-09-08、逐語:「フェーズ 10 に組み込めるのであれば組み込んでください。」)。**足したのは §5 の U-7〜U-13、§3 D-13 (同一 idempotency key の同時送信の直列化 = WP-6d と新条件 C-27)、§3 D-14 (小修正の束 = WP-1c)、D-5 (ii) の区分 (iii) への追補、D-2 への WP-3 追跡是正 (follow-up) 項目、D-8 (3) への WP-8 前提条件、§6.2 の C-27 行、§8 / §8.1 の WP-1c / WP-6d-i / WP-6d-ii、§9 の完了ゲート 14〜17 である。** **既存の決定・裁定・却下は 1 つも撤回していない。** 計画文書側の起票は `docs/design/ROADMAP_POST_PHASE7_V1.md` (v1.8) §1.0d と §8 の **R-24〜R-33** である。 レビュー指摘そのものは**監督保管**である。
- 位置づけ: **監督が確定した枠 (2026-09-08) の実施設計**である。計画文書 `docs/design/ROADMAP_POST_PHASE7_V1.md` (v1.6) の **§5 フェーズ10 節**・**§4**・**§8**・**§9** が**正本**であり、本書 §1.1 / §2.1 はそれを**逐語で転記する** (計画文書 §9 の 1、`docs/work-orders/OPERATING_CONDITIONS.md` §1.8 の 53)。**§1.2 は逐語転記ではなく要約である。** §3 の D-1〜D-14 と §4 の A-1〜A-9 は**監督確定**、**§5 の U-1〜U-13 は依頼者委任 (2026-09-07 / 2026-09-08) に基づく監督確定**である (**D-13 / D-14 と U-7〜U-13 は v1.3 の新設である**)。
- テーマ: **「宣言が真であることの証拠を、配備の面まで伸ばす」**。フェーズ9 までの証拠は **1 プロセス内**で完結していた — 4 plug はすべて `httpx.ASGITransport` の in-process 経路であり (`r2db-api/conformance/conformance_adapter_r2db_http.py:1060`)、`surfaces` の宣言 URL は到達不能な合成ドメインであり (`:155`)、`limit_enforcement: enforced` が**どの単位について真なのか**を契約が定義していなかった。本フェーズはこの 3 点を、**実 socket・reverse proxy 越しの plug** (D-1 (A))、**本番 composition root を実起動して観測する新条件 C-26** (D-1 (B))、**適用単位を定義する契約 1.8.0 と配備者宣言 `process_ceilings`** (D-5) で埋める。
- **契約は変わる** (1.7.0 → **1.8.0**)。したがって**設計レビューは 2 回**である (計画文書 §9 の 3)。**計画文書 §5 の見出しは「契約変更なし」と書いており実際と食い違う** — 訂正註の確定文を §10.1 に置く (R-14)。
- 作業指示書は `docs/work-orders/WORK_ORDER_PHASE10_DEPLOYMENT_EVIDENCE_V1.md` であり、**計画文書 §9 の 9 に従い WP ごとの Change Set Manifest 形式で書く** (フェーズ10 がそう定められた最初のフェーズである)。**設計の逐語表・裁定文・却下案・背景は manifest に写さず本書の節番号で指し、各 WP の完了条件と変異は manifest 側で確定する。**
- 台帳 ID 族: **L10-N** (**正本は本書 §10**)。族の登録は script 自身の規約により別個の明示コミットで行う — 経緯と現行の正規表現は **D-7** に置く。
- 設計原則 (依頼者、2026-09-02): 先送りしない / シンプル / 制約・制限で回避しない / 誇れる成果物。**既定の重み付けは「最小変更」ではなく「長期に正しい形」。利用設計者は AI エージェントであり、宣言は確実に読まれる。** 応える G は **G-2** (比類なきセキュリティ・信頼性) が主対象で、**G-3** に実ダイヤルと C-26、**G-4** に D-8 の実測と D-12 の記録で応える。
- **公開規律**: 実値を一切書かない — 実ホスト名・cloud project 識別子・実 e-mail・実 credential_id・作業機の絶対パス・IAM principal・実 DSN を含まない (`OPERATING_CONDITIONS.md` §1.9 の 60〜63)。**file:line はすべてリポジトリ相対パス**である。**契約 1.8.0 の確定文言は監督保管の確定文ファイルから逐語で複製する** (常設規律 4、同 §1.5 の 35〜36)。

---

## 1. 問題設定

### 1.1 計画文書 §5「フェーズ10」節の転記

計画文書 `docs/design/ROADMAP_POST_PHASE7_V1.md` §5 のフェーズ10 節 (`:222-227`) を以下に**転記する** (再導出しない)。

> ### フェーズ10 — 配備面の証拠 (契約変更なし、フェーズ9 と並行可)
>
> - **L7-2** 実 socket を持つ HTTP plug (5・6 番目の plug)。reverse proxy 込み。ここで初めて `surfaces` の「宣言 URL の実在」が load-bearing になる (L6-5 / L6-12)。
> - **L6-5a** `surfaces` を DB 側単一真実へ載せる (Q4 と同じ機構)。相互ダイヤルによる健全性検査は採らない (§6)。
> - **着手条件**: CI が実サーバ起動の場を持つこと (フェーズ7 D-3 で成立済み)。フェーズ9 と触るファイルが重ならないことを設計で確認する。
> - **【追記 2026-09-08 (v1.6)】着手前・同フェーズ内の是正 (§8 の R-17〜R-23)。** **着手前**: **R-21** (`CONTROL_MAPPING.md` SI-08 行と両 README の陳腐化を現物から書き直す)。**本フェーズの範囲に足す**: **R-17** の再発防止検査 (追跡中の `.md` が 0 バイトなら赤)、**R-19** (本番 image / 配備手順を `constraints.txt` の exact-pin に揃える)、**R-18** の裁定 (資源制限 `enforced` の適用単位。配備面の証拠を扱う本フェーズが最も近い)、**R-20** の実測 (L7-2 の実 socket adapter で同時要求下の tail latency を測ってから方式を決める)。**設計文書 §1〜§2 に転記する (§9 の 1)。** 変更クラスは各行の記載による (§9 の 8)。

### 1.2 計画文書 §8 の R-17〜R-23 の要約

**本節は逐語転記ではなく要約である** (監督裁定 2026-09-08、レビュー 1 M-4)。**正本は計画文書 §8 の各行である。R-18 行が持つ枝ごとの変更クラスは D-5 に写した。**

| 記号 | 要旨 | 行き先 |
|---|---|---|
| **R-17** | 公開ゲート実施記録が 0 バイト化していた (`.gdoc` 変換の巻き添え) | **本体は閉じた** (計画文書 v1.6)。**残**: 0 バイト検査 (**Class B**) → D-7 / WP-1 |
| **R-18** | 資源制限 `enforced` の適用単位が契約で未定義 (プロセス単位か、公開 base URL が表す配備全体か)。MitateDB の rate / concurrency は 1 プロセス 1 個の in-memory 状態で、Cloud Run の data service は `--max-instances` を固定していない。r2db は単一 uvicorn なので実害は MitateDB 配備に限られるが、**契約の沈黙は共通** | **本フェーズ設計で裁定** (枝 (a)〜(d) と枝ごとのクラスは §5 U-1 / D-5) |
| **R-19** | 本番 image の依存解決が CI と一致しない (CI は `-c constraints.txt`、Dockerfile は素の `pip install .`) | **本フェーズ (Class B)** → D-6 / WP-2 |
| **R-20** | 両 peer の HTTP handler が同期の service / psycopg を直接呼ぶ (機能不良は未確認) | **L7-2 で実測してから決める。実測前に直さない** → D-8 |
| **R-21** | 正本文書の陳腐化 (`CONTROL_MAPPING.md` SI-08 行、両 peer の README) | **着手前に是正**。CONTROL_MAPPING は **Class D**、README 2 本は **Class A** → D-9 / WP-0 (**完了**) |
| **R-22** | 保守性 (長大なモジュール・関数、`CONTROL_MAPPING.md` の 1 invariant 1 行という形) | **依頼者判断待ち。本フェーズの範囲外。** ただし計画文書の同行は**「R-21 の是正時に再編を同時に行うかを依頼者に問う」**と定めており、**WP-0 が SI-08 行を書き直し §7 がそこに 1 統制を足す本フェーズがその時点にあたる** — **フェーズ完了報告で問う** (§9 の 13) |
| **R-23** | AI エージェント向けの不足 (catalog が schema 本体・例・discovery URL を一体提供しない) | **フェーズ11 以降。本フェーズの範囲外** |

### 1.3 監督が確定した枠による再定義 (枠 §1。本節は再導出ではなく、正本と現物の食い違いの解消である)

計画文書は正本であるが、**その文言が書かれた後に事実が動いた箇所が 2 つある。** 本節はその 2 点を確定し、正本側は訂正註で直す (R-14、本文は消さない。文案は §10.1)。

**(1) L6-5a の残余は「機構の新設」ではなく「本番経路での実証」である。**

計画文書 §5 は「`surfaces` を DB 側単一真実へ載せる (Q4 と同じ機構)」と**未来形で**書くが、**機構は Q4 フェーズで閉じている**。

- 閉止註そのもの: `docs/design/PHASE6_CONTRACT_160_CLIENT_DISCOVERY_V1.md:796` の **「【閉止 2026-09-05】Q4 フェーズで閉じた」** (設計 `docs/design/Q4_DB_SIDE_SINGLE_TRUTH_V1.md` D-2、migration r2db `0008` / MitateDB `0007`)。宣言表・読み出し・`ops declare-surfaces` (`r2db-api/src/r2db_api/ops.py:1200-1231`)・`ops verify-declarations` (`:1361-1415`)・配備 step (`r2db-api/deploy/scripts/part1c_declare_surfaces.sh`) はすべて現物として在り、廃止 env は定義されているだけで起動を拒否する (`r2db-api/src/r2db_api/platform_declarations.py:119`、F-2)。

**したがってフェーズ10 の残余は Q4 設計 §12 の LQ4-11 である** — **「conformance の HTTP plug への影響は peer で非対称であり、本機構は共通 conformance では検証されない」** (`docs/design/Q4_DB_SIDE_SINGLE_TRUTH_V1.md:938`、`:965`)。MitateDB HTTP plug は control-plane composition root を env 付きで呼ぶので宣言表を通るが、**r2db HTTP plug は `surfaces` を明示注入する** (`r2db-api/conformance/conformance_adapter_r2db_http.py:837` の `_SURFACES` 定義、`:1048` / `:1219` / `:2097` の使用) ので宣言表を通らない。**本フェーズはこの非対称を、本番 composition root を実起動する新条件 C-26 で閉じる** (D-1 (B) / D-4)。

**(2) 着手条件のうち「CI が実サーバ起動の場を持つこと」は、PostgreSQL については成立しており、HTTP サーバについては本フェーズが作る。** フェーズ7 D-3 が用意したのは実 PostgreSQL の起動場であり (`.github/workflows/ci.yml:144-163`)、**実 HTTP サーバの起動場は無い** (`uvicorn.run` / `uvicorn.Server` の呼び出しはリポジトリ全体で 0 件)。**本フェーズはこの場そのものを作る** (D-1 / D-2 / D-3 / D-11)。**nginx の CI 導入には先例がある** (`deploy-assets-lint` job の `.github/workflows/ci.yml:349`)。

**フェーズ9 と触るファイルが重ならないことの確認は無条件に成立する** — フェーズ9 は完了済み (main `b3cfc0c`) であり、並行しない。

**本フェーズが閉じ得る既存台帳の一覧と閉止条件は §10.0 に置く** (重複を避けるため本節には表を持たない)。

---

## 2. 守るべき条件

### 2.1 計画文書 §4 (P-1〜P-9) の転記

計画文書 `docs/design/ROADMAP_POST_PHASE7_V1.md` §4 (`:152-165`) を以下に**転記する** (再導出しない)。

| 記号 | 条件 | 根拠 |
|---|---|---|
| **P-1** | **1 要求 = 1 原子単位。往復をまたぐサーバ保持状態を持ち込まない。** plan・sandbox・resumable upload・保持 lock はすべてこれに当たる。無状態化 (決定的トークン、実行して rollback) で同じ目的を満たす | 契約 `transactions.interactive`、SI-08、両 peer の同型性 (状態は同型性を「持ち方」と「失効」の 2 回壊す) |
| **P-2** | **エージェントの 1 周を閉じることを優先する**: catalog を読む → 要求を作る → 判定を受ける → 安全に再送する。この周回に欠けているものが最優先で、周回の外の機能は実需の実証を待つ | G-1、ai-agent 前提 |
| **P-3** | **宣言は真であり、検査される。** 新しい宣言 (制約・能力・limit) は、宣言と実挙動の一致を共通条件として同時に追加する。advisory な宣言 (強制されない説明文) を catalog に載せない | C-05 / C-17、L6-6 |
| **P-4** | **catalog と schema 操作は同じ版で動く。** 片方だけ先行させない | L6-6 |
| **P-5** | **bound は安全上必要なものだけ。** 機能の問題を TTL・件数上限・除外リストで消さない。要求単位 budget は配備上限を下回る方向にのみ効く | 設計原則 3、SI-08 |
| **P-6** | **peer 同型性を維持する。** 同名 helper は正規化 diff で固定し、コードは共有しない。platform 固有の実現 (PostgreSQL / SQLite / in-memory) が異なっても、契約上の意味は一致させる | peer-symmetry 規約 (2026-09-03) |
| **P-7** | **契約はエージェントが読める長さと形を保つ。** 経緯文は companion へ、現行の意味だけを契約本体に置く。派生の機械可読 artifact は再生成一致テストで正本に縛る | G-1、R-8 / R-10 |
| **P-8** | **各フェーズは性能の差分を記録する。** 基準値 (R-12) 確定後、完了ゲートに p50 / p95 の記録を添える。退行は初期は記録のみ、基準値が 2 フェーズ安定した後にゲート化を審議する | G-4 |
| **P-9** | **クラウド製品・任意 SQL・自然言語クエリ・管理画面・ORM 互換は共通契約に入れない** | CLAUDE.md 境界、CCR-01、提案 II の同趣旨 |

### 2.2 本フェーズで特に効く条件と運転条件 (枠 §2、`OPERATING_CONDITIONS.md` §1 の全 63 項)

- **P-3 が中心である。** 足す宣言は 3 種 — **適用単位の定義** (D-5 (i))、**`process_ceilings`** (D-5 (ii))、port の **`transport_kind`** (D-1) — で、**いずれも一致条件を同時に置く** (C-05 の改訂と peer-local 写像 pin と **C-26 (4) の実起動観測** / 起動時 fail-fast と F 検査 / C-19 の実ダイヤル枝)。**共通 suite が観測できない部分 (プロセス横断の同時性) は開示する。**
- **P-5 と設計原則 3 が R-18 の (b) 枝を却下する** (§4 A-2)。**P-8 が「閾値を置かない」を縛る** (D-8 / D-12)。**P-1 / P-4 / P-7 / P-9 は受動的である** (往復またぎ状態を作らず、catalog と schema 操作の版を動かさず、契約に足すのは 4 片だけであり、クラウド製品を共通契約に入れない)。
- **P-6 と `OPERATING_CONDITIONS.md` §1.5 の 38 / §1.2 の 16〜17 が形を縛る** — `process_ceilings` の機構・socket adapter・C-26 の launcher をすべて両 peer 同型で置き、**`_ISOMORPHIC_TARGETS` への行追加は監督の pair-closing commit で行う** (集合の増減は **Class D**。計画文書 §9 の 8)。
- **§1.3 の 24 (残骸を残さない 3 経路: 正常終了・`atexit`・起動時 sweep) を、プロセスと port にも同じ形で適用する** (D-2)。**完了ゲートに残骸 0 を足す** (§9 の 2)。**§1.3 の 26 (skip 禁止) により nginx が無ければ fail する** (D-3)。**唯一の例外は docker であり、その非対称は L10-6 に開示する。**
- **§1.4 の 28〜31 / §1.5 の 32〜40** — 完了条件 1 項目につき変異 1 つ (対応表は作業指示書)。**§1.6 の 42 / 45** — 並列度は実測に基づいて調整する (L10-1)。**§1.7 の 52** — plug の分類は `transport_kind` の宣言を読み**名前や属性形状から推測しない** (D-4 / D-12)。**§1.9 の 60〜63** — nginx conf は本番 example から写すが**実ホスト名・実証明書パスは写さず、traceback を文書に貼らない。**

---

## 3. 決定 (D-1〜D-14。**D-13 / D-14 は v1.3 の新設である**)

各 D は **決定 / 根拠 / 実装の形 / 壊すとどう見えるか** を持つ。**「壊すとどう見えるか」は、その決定が守っている性質を壊したときに何が赤くなるかを 1 文で書いたもの**であり、作業指示書の変異表の出所である。

### D-1 実 socket plug と本番 composition root の証拠 — 2 つの成果物に分ける

**決定 (監督再定義 2026-09-08、設計レビュー 1 / 2 の反映)**: **L7-2 を 2 つの成果物に分ける。**

**(A) 5・6 番目の plug = 既存 HTTP adapter の composition を「実 socket + reverse proxy」で serve する完全 adapter。** `r2db-api-socket` / `MitateDB-api-socket` を新設し、`conformance-tests/registry.json` を **6 件・全て `required: true`** にする。**各 socket adapter は既存 HTTP adapter (`conformance_adapter_r2db_http.py` / `conformance_adapter_mitatedb_http.py`) を継承する。** `httpx.ASGITransport` の代わりに、**同一プロセス内で uvicorn (`uvicorn.Server` を thread 実行) を loopback port に bind して composition 済みの ASGI app を serve** し、その前に **nginx subprocess** を置き、client は `httpx.AsyncClient(base_url="http://127.0.0.1:<nginx port>")` の**実 TCP** で叩く。**composition は既存 HTTP adapter と同一であり、注入もそのまま継承する** — 変わるのは transport (実 HTTP/1.1 framing、実 proxy、実 connection 並行性) だけである。

**(B) 本番 composition root の証拠 = 新条件 C-26「配備 composition の証拠」。** 各 peer は、**文書化された composition root (`<peer>.main:app` / `<peer>.control_main:app`) を、文書化された env だけで**実起動できる launcher を `conformance/real_server_<peer>.py` に置き、`registry.json` の新節 `composition_roots` に登録する。共通テスト `conformance-tests/test_c26_composition_root.py` が launcher ごとに下記 1〜6 を観測する。

**根拠**: **現行 port (`ConformanceAdapter`) はプロセス内の手 (`hold_in_flight` の monkeypatch、`flush_audit_buffer`、`set_authorization_state_available`、隔離 surface への limits 注入、テストごとの application provision) を前提にしており、「本番 composition root を env だけで起動する完全 adapter」は plug あたり約 470 テストぶんの再起動を要してこの port と両立しない** — **4 つの非両立点を file:line 付きで §4 A-9 に記録した** (v1.0 の D-1 はこの形を採っており、監督が 2026-09-08 に撤回した)。**分割により (A) では「transport だけが違う」が真に成立し、in-process の手と perf harness の `_resolve_cell` / `backend_calls` を既存実装のまま継承できる。L7-2 が求める「required な完全 adapter」は (A) が、「本番経路での実証」(L6-5a 残余 = LQ4-11) は (B) が満たす。**

**実装の形 (A)**:

1. **既存 HTTP adapter を継承し、transport 層だけを差し替える** — `httpx.AsyncClient` の transport と `base_url`、uvicorn thread、前段の nginx instance。**差し替えは下記 6 の hook 経由で行う** (現物の client 構築は `__init__` にベタ書きであり、継承だけでは差し替え点が無い)。**DB 隔離 (admin DSN / startup sweep / throwaway prefix / advisory lock / migration / 実 CLI による bootstrap・reset) は継承し、prefix だけ socket 用の別系統にする** (既存 HTTP plug と同時実行しても衝突しない)。
2. **`surfaces` の値は既存の注入経路のまま、値を実 URL (自分の nginx の URL) にする** (D-4)。
3. **隔離 surface は自分専用の uvicorn thread + nginx instance を持つ** (port 別、遅延起動、`with` 終了で停止)。**隔離 profile の bound 値は既存 HTTP plug と同じにする** (`conformance_adapter_r2db_http.py:856`)。**socket plug のためだけに bound を動かさない** (L8-12)。
4. **`ConformanceAdapter` に class 属性 `transport_kind` を足す** (監督裁定 2026-09-08、起草疑義 4 / レビュー 1 M-3)。**値は `"in_process"` / `"asgi"` / `"socket"` の 3 値、既定は無い (各 adapter が明示する抽象属性)。** in-process 2 plug は ASGI を通らないので `"asgi"` を継がせない — **偽の宣言を導入しない** (P-3)。**port の版数を上げる** (§6.3)。
5. **readiness 判定** (監督裁定 2026-09-08、起草疑義 8): **proxy 経由で `GET /v1/capabilities` を Authorization 無しで送り、HTTP 応答 (status < 500。期待は 401) が返った時点で ready。上限 30 秒で fail する** (skip しない)。**data / control の両 upstream** で行う。**TCP connect だけでは app の import 失敗を見逃し、200 を条件にすると認証情報を readiness 経路に持ち込む。** **surface 1 面あたりの全体予算は D-2 (a) が別に持つ。**
6. **基底 http adapter に hook を抽出する (WP-3。挙動不変)** (監督裁定 2026-09-08、差分レビュー): 現物の client 構築は `__init__` にベタ書きで (`conformance_adapter_r2db_http.py:1060`、control は `:1127`)、reset 経路 (`:1532`)・`isolated_control_surface` (`:1970`)・`isolated_application_surface` (`:2075-2110`) が同じ形を繰り返し、`surfaces` はモジュール定数が構築時に焼き付く (`:1048`、`:1219`、`:2097`)。**継承先が transport と `surfaces` を差し替えるには基底側に 3 つの hook が要る** — **(a) `_build_client(app, base_url) -> httpx.AsyncClient`** (既定は `ASGITransport`)、**(b) `_surfaces_value() -> dict`** (既定はモジュール定数)、**(c) 隔離 surface の構築も同じ hook を通す。** **socket adapter は (a) (b) を override し、隔離 surface では自分専用の uvicorn thread + nginx を持つ (親の handle を共有しない)** — `copy.copy(self)` の上書きが漏れると**隔離面が親の共有 app を serve したまま緑で通り C-05 の隔離駆動が無音で誤る。** **挙動不変の固定は「抽出の前後で既存 4 plug の集計行が一致すること」** (WP-3 の完了条件)。**非 vacuity**: socket plug で隔離 surface の `base_url` が親と異なることを assert する。**抽出しない形は `isolated_application_surface` 全体の複製になり P-6 と衝突する。**

**実装の形 (B) — C-26 の観測項目** (launcher ごと):

1. 使い捨て platform を作り、**`ops declare-surfaces` と `ops declare-process-ceilings` を実 CLI で書いてから** data / control の uvicorn を **subprocess** で起動する。**順序は「free port 予約 → declare → uvicorn → nginx → readiness」** — `cmd_declare_surfaces` 自身が「新しい値を効かせるには両プロセスを再起動せよ (起動時スナップショット)」と出力する (`r2db-api/src/r2db_api/ops.py:1231`)。
2. **宣言表由来の `surfaces.data` / `surfaces.control` に実 TCP で GET し、同じ文書が返る** (data / control の両面)。
3. **`tools/deploy_smoke.py` を subprocess で実行して緑である。**
4. **`process_ceilings` を 1 で宣言した起動と 2 で宣言した起動 (再起動 1 回) で、`limit_enforcement` の写像 (`enforced` ↔ `deployment_required`) を観測する** — **共通 suite が「宣言値 → `limit_enforcement` の写像が実起動で成立すること」を観測できる唯一の場である** (監督裁定 2026-09-08、差分レビュー)。**実プロセス数そのものは観測しない** — launcher が起動するのは 1 プロセスであり、`process_ceilings: 2` はその起動については偽の宣言である。**topology と宣言の一致は runbook 規律 + 配備後チェックが担う** (**LQ4-15 と同じ射程**。L10-2)。
5. **行が無ければ起動が fail-fast する** (stderr に F-15 相当の文言)。
6. **終了時のプロセス・port 残骸が 0 である。**
7. **非 vacuity**: `composition_roots` が **2 件以上**であることを registry-guards で assert する。
8. **xdist group を launcher ごとに分ける** (監督裁定 2026-09-08、差分レビュー): `conformance-tests/conftest.py:95-97` は `adapter` param を持たない item をすべて `registry-guards` group に入れる。C-26 は `composition_roots` で parametrize され `adapter` param を持たないので、**そのままでは registry 横断 guard 群と同居して 1 worker に直列化される。** **C-26 の item は launcher ごとの `xdist_group` (例 `c26-<peer>`) に置き、`conftest.py` を WP-6c の触るファイルに足す** (§8)。**7 の registry-guard は対象外である** (adapter を起動しない)。
9. **変更クラスは C** (§6.2)。**launcher の同名 helper を同型性表に載せる pair-closing commit は Class D である** (§8 WP-6c)。

**壊すとどう見えるか**: **(A)** nginx を経由せず uvicorn を直接叩く形に戻ると **C-05 の `request_bytes` 枝が「proxy を通った上で app が主体である」ことを観測しなくなる** (D-3)。**(B)** launcher が composition root ではなく adapter 側の composition を起動する形に変わると **宣言表の行を落とす変異が C-26 で赤にならない。**

### D-2 共通 harness の置き場 — `conformance-tests/socket_harness.py`

**決定**: プロセス・port・proxy の面倒を見る harness を **`conformance-tests/socket_harness.py` (共通)** に置く。**socket adapter (A) が使う thread 版と、C-26 (B) が使う subprocess 版の 2 つの起動関数を同じ harness が持つ。** **各 peer の socket adapter・launcher (env 組み立て、DSN、ops CLI 呼び出し) は peer の `conformance/` に置く。**

**根拠**: `conformance-tests/` は**既に共通の adapter 基盤を持つ場**である (`adapter.py:1028` の `ConformanceAdapter` ABC 以下 38 個超の抽象メソッド)。**peer 間でコードを共有しない規約 (P-6) は peer 実装と peer テストに掛かるものであって共通 suite の基盤には掛からない** — もし掛かるなら `adapter.py` 自体が規約違反になる。**プロセス管理は契約上の意味を持たない試験基盤である。** (§5 U-4)

**責務**: **(a) uvicorn** — thread 版と subprocess 版、readiness (D-1 の 5)、停止 (graceful shutdown → join / SIGTERM → SIGKILL)。**全体の起動予算 (監督裁定 2026-09-08、差分レビュー / レビュー 2 の 7)**: **harness は surface 1 面 (uvicorn 2 本 + nginx 1 本) の起動を合計 60 秒で fail とする** (skip しない)。**D-1 の 5 の 30 秒は upstream 1 本あたりの上限であり、面としての上限は別に要る** — 遅延起動 (g) は起動本数を減らすが 1 面あたりの上限は減らさない。**(b) nginx** — conf 生成では **prefix 配下に `pid` / `error_log` / `access_log off` / `client_body_temp_path` / `proxy_temp_path` を明示する** (これらはコンパイル時の**絶対**既定を持ち、CI の非 root 実行では root 所有の既定パスを指すので `-p <prefix>` だけでは効かない)。起動は **`nginx -p <prefix> -c <conf> -e <prefix>/error.log -g 'daemon off;'`** とし、**起動前に `nginx -t` を通す** (開発機 Homebrew と CI apt の版差が無音で効かないようにする)。**(c) free port の取得**、**(d) 終了時の確実な kill**、**(e) 異常終了時の `atexit`**、**(f) 起動時 sweep** (**自分の prefix 配下の pidfile を見て孤児を kill する**)。**(g) 遅延起動** — **最初の port 呼び出しまで何も起動しない。** `_discover_and_build()` は conftest の import 時に**registry の全 adapter** を build する (`conformance-tests/conftest.py:107-173`) ので、遅延起動が無ければ 1 テストも使わない worker が nginx と uvicorn を起こす。**起動本数の実測 (10 本か 12 本かは xdist の挙動で変わる) は WP-3 で取り §11 に記録する。**

**【追記 2026-09-08 (v1.3)。WP-3 の追跡是正 (follow-up) 項目。§5 U-12】** **責務 (f) の起動時 sweep に `pid <= 0` の明示 guard を置く** — **`pid <= 0` は「自分のものではない」扱いとし、pidfile だけを消して signal しない** (`os.kill(0, …)` はプロセスグループ、`os.kill(-1, …)` は全プロセスを指す)。**所有者検査そのものは既に在る** — 現行の実装は pidfile の pid の cmdline に harness の prefix marker が含まれるときだけ SIGTERM → SIGKILL を送る (監督裁定 2026-09-08)。**marker 検査が先行するので実害経路は無いが、guard は明示に置き、テストを 1 本足す。**

**【実施済み 2026-09-08。WP-3 は main `6055c69` にマージ済みなので rework ではなく follow-up として実施した。branch `phase10-wp3f` の `ea237e5`】** **`sweep_orphans` は解釈した pid が `0` 以下なら「自分のものではない」として扱う** — **pidfile を消し、`_process_cmdline` を呼ばず、signal しない。** **テストは `conformance-tests/test_socket_harness.py::test_sweep_orphans_never_signals_a_non_positive_pid` である。** **変異の実測: guard を外すと赤になり、`_process_cmdline must never be called with a non-positive pid, got -1` を出す。** **`conformance-tests/test_socket_harness.py` は `30 passed`、`tools/tests` は `61 passed` である。** **main へのマージは次のゲート束で監督が行う (現時点で main 未マージ)。** **外部レビュー 2 の起票は計画文書 §8 の R-27 である。**

**壊すとどう見えるか**: **終了処理 (d) / (e) を外すと完了ゲートの残骸 0 検査が赤になる** — suite 自体は緑のまま通り得るので**この性質はゲート側でしか捕まらない** (§9 の 2)。**遅延起動 (g) を外すと CI の所要時間が跳ね上がる** (L10-1)。

### D-3 reverse proxy の条件 — nginx を必須依存にし、bound を隠さない設定にする

**決定**: **nginx は必須依存**である (開発機は Homebrew、CI は apt)。**無ければ fail する (skip しない)。** `nginx` は **`NGINX_BIN` env か PATH** から探す。conformance 用 conf は **本番 example (`r2db-api/deploy/nginx/r2dbsvc-api-8443.conf.example`) の proxy 設定を写し**、listen / upstream / パスと D-2 (b) の prefix 系設定だけを差し替える。**proxy が app の bound を隠さないことを条件にする**: **`client_max_body_size 0`**、**`proxy_read_timeout` は app の `execution_ms` 上限より長い値を明示する**。**TLS は張らない** (§4 A-8、L10-5)。

**根拠**:

- **本番 example から写す**のは、conformance の proxy が**この配備が実際に置いている proxy と同じ形**であることを保証するためである。現物は `location /v1/` と `location /control/v1/` の 2 ブロック (`proxy_pass` / `proxy_http_version 1.1` / `Host` / `X-Real-IP` / `X-Forwarded-For` / `X-Forwarded-Proto` / `X-Request-Id ""` の各 `proxy_set_header`) である。
- **`client_max_body_size` は本番 example では `1100k`** (app の `request_bytes` 既定 1 MiB に約 7% の余裕を持たせ、**app 側の `RequestByteBoundMiddleware` が拒否の主体になる**ようにしている)。**conformance では `0` にする** — 本番の余裕は「app が主体」を**ほぼ常に**成立させるが、conformance は**常に**成立させる必要がある。**有限の潤沢な値 (例: `request_bytes` の 10 倍) でも同じ性質と同じ変異は成立する** — `0` を採るのは `request_bytes` が将来動いても conf を追随させなくてよいからであり、**「無制限だから安全」という主張ではない。** **`0` は >1 MiB の body を必ず temp file にバッファするので、temp path の明示 (D-2 (b)) が伴って初めて成立する。**
- **`proxy_read_timeout` は本番 example に存在しない** (既定 60 秒に依存)。**conformance conf が明示する分は本番 example との差分であり、開示事項である** — 本番側にも明示するかは WP-2 の作業指示書で確定する。
- **MitateDB は本番で nginx を使わない** (Cloud Run 前面) が、**conformance の proxy は「任意の HTTP 中継者」の代表**なので両 plug に同じものを置く (P-6)。

**壊すとどう見えるか**: **`client_max_body_size` を app の `request_bytes` より小さくすると、C-05 の `request_bytes` 枝が socket plug で「nginx の 413」を観測し、app の構造化拒否 (`LIMIT_EXCEEDED` + `limit_class`) を観測しなくなる。** **temp path の明示を外すと、同じ枝が nginx の 500 を観測する。**

### D-4 `surfaces` の 2 つの経路 — 実ダイヤル (socket plug) と本番経路 (C-26)

**決定**: `surfaces` について、**性質の違う 2 つの証拠**を置く。

1. **socket plug (D-1 (A))**: `surfaces` の値は**既存の注入経路のまま、値を自分の nginx の実 loopback URL にする** (`http://127.0.0.1:<port>/v1` と `.../control/v1`)。**これにより C-19 の declare-and-echo が「実ダイヤル」になる** — capabilities が返した `surfaces.data` / `surfaces.control` に**新しい client で実 TCP GET し、同じ文書が返る**ことを検査する。**data / control の両面をダイヤルする** (C-19 の D-2 vector が本来見ているのはもう一方の面である)。
2. **C-26 (D-1 (B))**: **宣言表からの読み出しという本番経路**を、launcher が `ops declare-surfaces` で書き、composition root が表から読み、テストがその値へ実 TCP GET する形で実証する。**LQ4-11 を閉じるのはこちらである。**

**根拠**: **L6-12 の原文が「declare-and-echo は同一 adapter への 2 回呼びの自己整合であり実ダイヤルではない」** (`docs/design/PHASE6_CONTRACT_160_CLIENT_DISCOVERY_V1.md:827`)、**L6-5 が「宣言された URL に本当に到達できることを独立に検証できるのは HTTP plug だけ」** (`:794`) と述べている。**「宣言 URL の実在」は値が実在することの検査であり、値の出所 (注入か宣言表か) とは別の性質である** — 1 は注入経路のままでも成立し、2 が出所の検査を担う。**両方を 1 つの plug に載せようとすると port の in-process 前提と衝突する** (§4 A-9)。

**実装の形**:

- **C-19 の実ダイヤル枝の判定は `adapter.transport_kind == "socket"`** (D-1 の 4)。**名前の接尾辞や URL の形から推測しない** (`OPERATING_CONDITIONS.md` §1.7 の 52)。**非 vacuity assert は「registry に `transport_kind == "socket"` の plug が 1 件以上ある」** — `registered_adapters()` / registry を読む形にする (`conformance-tests/conftest.py:178`。`--dist loadgroup` では suite 内の集約 assert が成立しないため)。
- **C-19 の honest limits (b) を改訂し、(a) が記録する「実ダイヤルには新しい port primitive が要る、監督レビュー待ち」という開示は本フェーズで解消したことを明記する** — 実ダイヤルは既存の port で成立する (`CredentialHandle.secret` が完全な bearer である。`conformance-tests/adapter.py:91`)。
- **L6-5 / L6-12 / LQ4-9 は socket plug と C-26 に限って閉じ、射程の開示 (in-process / ASGI plug では依然として自己整合である) は残す。**

**壊すとどう見えるか**: **socket adapter の `surfaces` の値を実 port と違う port にすると、C-19 の実ダイヤル枝が接続失敗で赤になる** (現行の自己整合 assert は緑のまま通る)。**C-26 の launcher が `declare-surfaces` を打たなければ composition root が fail-fast で起動しない。**

### D-5 R-18 の裁定 — 契約 1.8.0 と配備者宣言 `process_ceilings`

**決定 (監督確定。依頼者委任に基づく。§5 U-1)**: **(a) 契約に適用単位を明記する枝**と、**(d) 複数プロセス時は `deployment_required` を宣言する枝**を、**「宣言機構」として 1 つに統合して採る。** **計画文書 §8 の R-18 行は枝ごとの変更クラスを (a) C / (b) A / (c) B+C / (d) C と定めており、採った統合枝は C である。** 内訳は (i)〜(v) である。

#### (i) 契約 1.8.0 — 適用単位を定義する

**以下の 4 片は、監督保管の確定文ファイル (レビュー 1 M-2 / M-8 の訂正を反映済みの版) からの逐語である。言い換えない** (常設規律 4、`OPERATING_CONDITIONS.md` §1.5 の 35〜36)。

**(1) `capability_status.rules` に足す 1 文** (`spec/data-service-api.v1.json` の `capability_status.rules` 配列末尾。現行は 4 要素、`:217-222`):

> "limit_enforcement values describe the whole deployment reachable at the declared surfaces base URL, never one server process: a peer declares enforced for a limit class only when the bound holds across every process that may serve that base URL at the same time, and declares deployment_required when the bound is held per process and more than one process may serve that base URL."

**(2) `limits.profile` の文字列の末尾に足す 1 文** (**挿入先は `limits.profile` の文字列であり、新しいキーを作らない**):

> "Enforcement scope is the deployment behind the declared base URL (capability_status.rules); a bound kept in per-process memory is enforced for the deployment only while exactly one process serves that base URL."

**(3) `versioning.obligations` の 1.8.0 entry** (**キー名は既存 entry と同じ 4 キー**。他の形は置かない):

> {"version": "1.8.0", "subordinate_ruling": 13, "unconditional": ["limit_enforcement_scoped_to_deployment_behind_base_url"], "conditional": []}

**(4) `spec/CONTRACT_HISTORY.md` の anchor 文 (provenance companion)**:

> "1.8.0 (subordinate ruling 13, 2026-09-08): enforcement scope defined as the deployment behind the declared surfaces base URL. Reason: r2db-api serves each base URL from one process, MitateDB-api on Cloud Run may serve it from several; the contract had not said which unit the enforcement values describe."


#### (ii) 機構 — 配備者宣言 `process_ceilings` (両 peer 同型)

**決定**: 配備者の宣言 **`process_ceilings`** を `platform_declarations` に 1 行足す。**Q4 D-2 と同じ機構**である — **表が唯一の出所、`ops declare-process-ceilings` で書く、`ops verify-declarations` に F-15 を足す、行が無ければ起動時 fail-fast** (`surfaces` と同じ扱い)。**形は `surfaces` を写す**: `{"data": <int >= 1>, "control": <int >= 1>}` = **各 plane の base URL を同時に serve し得るプロセス数の上限**。

**`limit_enforcement` はこの値から決まる。写像は 3 区分である** (監督裁定 2026-09-08、レビュー 1 M-1):

| 区分 | limit class | ceiling = 1 | ceiling ≥ 2 |
|---|---|---|---|
| **(i) 要求単位で完結する** | `request_bytes` / `operation_depth` / `batch_items` / `batch_entities` / `result_items` / `query_complexity` / `schema_objects` / `enum_members` / `execution_ms` | **影響を受けない** | **影響を受けない** |
| **(ii) in-memory per process で bound する** | `requests_per_minute` / `concurrency` / `control_requests_per_minute` / `audit_requests_per_minute` | `enforced` | `deployment_required` |
| **(iii) DB 側で bound する** | `applications` / `credentials_per_application` / `idempotency_entries` | **同一 tx 内の lock 付き check-then-write なら `enforced`** | **同上 (ceiling に依らない)** |

**根拠**: **(ii) だけがプロセス数に比例して緩む** — MitateDB の `_LimitStateHolder` は docstring 自身が「process-wide (one per composition root)」と述べ (`MitateDB-api/src/mitatedb_api/cell.py:744-780`)、r2db は `service.py` の `_acquire_rate` / `_slot` が同じ役を持つ。**(i) はプロセスが何本あろうと 1 要求ごとに同じ判定になる。** **(iii) は「DB 側だから安全」ではない** — 現行は unit of work の**外**での read-then-write である (`r2db-api/src/r2db_api/control_plane.py:847`、`:944`。MitateDB は `control_plane.py:1513`、`:1600`。`idempotency_entries` は別トランザクションでの count → 後段 store、`r2db-api/src/r2db_api/postgres.py:1213-1221`)。**この形では ceiling ≥ 2 で bound が破れ得るが、確定文の `deployment_required` の条件は「bound is held per process」であり、DB 側で競合する bound はどちらの語にも当てはまらない。** **したがって WP-6 の実装担当は (iii) の各 class・各 peer で lock の有無を確認し、無ければ足す** — **写像を弱める側には倒さない。先送りしない。前例はフェーズ9 R-2 の `LOCK TABLE ... IN SHARE MODE` である。**

**【追記 2026-09-08 (v1.3)。区分 (iii) の 2 点の確定。§5 U-7、§3 D-13】**

- **(1) 同一 idempotency key の直列化は、区分 (iii) の件数 bound とは別の性質である。** 本節が WP-6 に課しているのは `idempotency_entries` の**件数**が ceiling に依らず保たれることだけであり、**「同一キーの同時要求が高々 1 回しか実行されない」ことは含まれていなかった。** **この性質は D-13 (WP-6d) が担う** — key 単位の `pg_advisory_xact_lock` を、効果と同じトランザクション・同じ接続で照会の**前**に取る形である。**外部レビュー 2 で二重実行が実測されており (計画文書 §8 の R-24)、区分 (iii) の lock を足すだけでは閉じない。**
- **(2) 件数 bound に採る lock は表単位の定数 key の `pg_advisory_xact_lock` であり、`LOCK TABLE ... IN SHARE MODE` ではない** (`r2db-api/src/r2db_api/ops.py:149` の `_RITUAL_ADVISORY_LOCK_KEY` と同系。MitateDB は `MitateDB-api/src/mitatedb_api/ops.py:220`)。**SHARE は SHARE 同士が衝突しないので、両者が SHARE を取ったまま INSERT で待ち合って deadlock する。** **フェーズ9 R-2 の前例は形が違う** (`alter_field` / `add_field` が自分の対象表を SHARE で固定して走査する、書き手 1 名の形。`r2db-api/src/r2db_api/postgres.py:2292`、`:2373`)。**実装担当はその前例の lock mode を現物で確認し、同じ誤りが無いことを報告する。**

**機構の実装点**: 表の `key` は `CHECK` で閉じた集合として固定されているので (`r2db-api/migrations/0008_platform_declarations_and_writer_timeouts.sql:136-139`、`MitateDB-api/migrations/0007_platform_declarations.sql:103-106`)、**追加は platform 単発 migration を要する** (Q4 D-2 (a))。**番号は r2db `0012` / MitateDB `0011`** (番号の違いは移行履歴が独立だからであり同型性の破れではない)。**MitateDB の `0008`〜`0010` は per-application upgrade script (`*_upgrade.sql`) で Q4 D-3 (d) の静的走査が命名で分類するので、platform 単発の `0011` を `_upgrade.sql` で終わらせてはならない** (例: `0011_process_ceilings.sql`)。**値側の CHECK は置かない** (検証は Python 側に一本化。Q4 D-2 (d))。**`verify-declarations` に足す番号は F-15、exit code は次の未使用値 14 である** (現行最大は `"F-14": 13`。`r2db-api/src/r2db_api/ops.py:1333-1352`)。**`_VERIFY_DECLARATIONS_EXIT_CODES` は両 peer で逐語同一の `_ISOMORPHIC_TARGETS` 登録対象なので、両 peer に同じ行を足す** (同 `:1314-1328`)。

**宣言表を通る全経路で、宣言を先に書く** (レビュー 1 H-1): **MitateDB HTTP plug の fixture seed** (`conformance_adapter_mitatedb_http.py:334-347` の隣。migration 一覧 `:292-305` に `0011`)、**その継承先である MitateDB socket plug**、**C-26 の両 launcher**、**両 peer の provision script / runbook**。**r2db HTTP plug は宣言表を読まないので影響を受けない** (`conformance_adapter_r2db_http.py:1030-1033`)。

#### (iii) 配備側

- **r2db**: 単一 uvicorn (`--workers` なし) なので **`{"data": 1, "control": 1}`** を宣言し、**`part1c_declare_surfaces.sh` と同系統の step を配備手順に足す。**
- **MitateDB (Cloud Run)**: **runbook の Invariant 1 を一般化する** — 現行は control service についてのみ `--max-instances=1` を「correctness requirement」と述べ (`MitateDB-api/docs/cloud-run-cloud-sql.md:1117-1130`)、data service は固定していない (`:549-552`)。**改訂後は「`--max-instances` は宣言した ceiling と一致させる (data / control 両方)」である。**
- **既存配備の upgrade 順序** (レビュー 1 L-3): **migration → `ops declare-process-ceilings` → 再起動**の順でしか上がらない (起動時スナップショットのため)。**`ops reset` は `applications` / `credentials` / 宣言表に触れないので再起動を要しない** (`r2db-api/src/r2db_api/ops.py:951`)。**必須キーが 2 つになるので、LQ4-24 (`part1_provision_host_and_db.sh` は `0008` も `declare-surfaces` も打たない) のままでは script 製ホストは落ちる** — **WP-6 の runbook 項で順序を明文化し LQ4-24 を参照する。**
- **Cloud Run 側の値を app は検証できない** (LQ4-15 と同種の限界)。**runbook 規律 + 配備後チェックが担う** (L10-2)。

#### (iv) peer-local テストと共通 suite の分担

- **peer-local**: **ceiling 1 → `enforced`、ceiling 2 → `deployment_required` の写像を両 peer で pin する** (実 PG テスト)。**(iii) 区分は「ceiling に依らず `enforced`」と、それを支える lock の存在を pin する。**
- **共通 suite**: **C-05 は従来どおり ceiling 1 の宣言の下で駆動し、1.8.0 の無条件義務そのものの共通検査は C-26 (4) が担う** (**宣言値から `limit_enforcement` への写像が実起動で成立することを、ceiling 1 と 2 の 2 通りで観測できる唯一の場である。実プロセス数そのものは観測しない**)。**「今このプロセスが何本いるか」を plug が知る手段は無く、topology と宣言の一致は runbook 規律 + 配備後チェックが担う** (LQ4-15 と同じ射程) ので、**C-05 の honest limits にその射程を開示する** (§6.2)。

#### (v) 版

**1.7.0 → 1.8.0。** 手順はフェーズ9 と同じである (契約 JSON + companion + obligations entry + `CCR_DISPOSITION.md` の従属判断 13 + catalog 再生成 + 3 複製 byte 一致 + pair-closing の版フリップ。触るファイルは §8 WP-5)。**現物を数え直した義務件数は 1.2.0 = 無条件 4 / 条件付き 0、1.3.0 = 3 / 0、1.4.0 = 3 / 6、1.5.0 = 0 / 1、1.6.0 = 2 / 2、1.7.0 = 2 / 5、1.8.0 = 1 / 0 である** (監督裁定 2026-09-08、レビュー 1 M-7)。**無条件義務の総数は 14 → 15。** **L9-10 が数えるのは 1.6.0 以降の累計であり 2 + 2 + 1 = 5 件である** — 2 つの数え方を混ぜない。

**壊すとどう見えるか**: **写像を「常に `enforced`」に固定すると、ceiling 2 の peer-local pin と C-26 (4) がともに赤になる。** **宣言表から `process_ceilings` 行を消すと、宣言表を通る経路の app が起動時 fail-fast で落ち、C-26 (5) がそれを観測する。**

### D-6 R-19 — 本番 image / 配備手順を exact-pin に揃える

**決定**:

1. **`MitateDB-api/docker/Dockerfile`** は repo root の `constraints.txt` を COPY し **`pip install --no-cache-dir -c constraints.txt .`** にする (**ビルドコンテキストは repo root** である。同 Dockerfile `:25-36`、`:50-51`)。**コメント (`:61-64`) を「CI と同じ exact-pin」に書き直す** — 現行は比較対象がローカルの `-e .[test]` install であって CI の install ではない。
2. **r2db の配備文書 3 箇所と script 1 箇所のコメントに `-c constraints.txt` を付ける** — `r2db-api/deploy/DEPLOYMENT_RUNBOOK.md:124`、`r2db-api/docs/POSTGRES_PROVISIONING_RUNBOOK.md:606` と `:1567`、`r2db-api/deploy/scripts/part1_provision_host_and_db.sh:425`。
3. **CI に `image-pins` job を足す** — image を `docker build` し、**image 内の `pip freeze` の各 package が `constraints.txt` の同名 pin と一致する**ことを検査する (**部分集合比較**: `constraints.txt` にあって image に無い test 依存では赤にしない)。**実行形は `docker run --entrypoint /opt/venv/bin/pip <image> freeze`** (runtime stage は非 root で shell を持たない)。**除外集合を逐語で列挙する: `pip`、`setuptools`、`wheel`、image 自身の distribution 名** — **`constraints.txt` はこの 4 種を意図的に外しているので、除外せずに比較すると必ず赤になる。**
4. **開発機 `.venv` を constraints に揃える** (監督作業。`OPERATING_CONDITIONS.md` §2 の 16 の実測不一致を閉じる)。
5. **docker が無い開発機では、この検査は CI が唯一の証拠である。** **nginx を必須依存とした D-3 との非対称であり、開示する** (L10-6) — nginx は harness が prefix 配下に自前の instance を起動するだけで済むが、image ビルドは daemon を要求する。

**根拠**: **「CI が緑である」ことと「本番 image が同じものを動かしている」ことは別の命題である** — 現行の Dockerfile は `pyproject.toml` の下限指定から解決するので、ビルド日が違えば違う版が入る。**コメントの主張を実測に変える** (常設規律 3)。

**実施状況**: WP-2 は 2026-09-08 に main `c9a937a` (実装 `79958a7`) へマージ済みである。

**壊すとどう見えるか**: **Dockerfile から `-c constraints.txt` を外すと `image-pins` が赤になる。** 検査自体の非 vacuity は、**`constraints.txt` の 1 行の版を image と違う値に変えて赤になることの実測**で示す。

### D-7 R-17 — 追跡中の `.md` が 0 バイトなら赤にする

**決定**: **`tools/check_doc_refs.py` に規則を 1 つ足す** — **`git ls-files -- '*.md'` が返す追跡中の `.md` のうち size 0 のものがあれば exit 1** で該当パスを列挙する (git 外では `rglob` にフォールバックする)。**テストは `tools/tests/test_check_doc_refs.py` に足す。**

**根拠**: **R-17 の文言は「追跡中の `.md`」である。** 参照解決の走査集合 (`iter_scan_files`、`:97-114`) では**足りない** — **実測 (2026-09-08): 追跡中 86 件に対し走査は 72 件**であり、未走査には**両 peer の README** (WP-0)、`r2db-api/deploy/DEPLOYMENT_RUNBOOK.md` (WP-2)、`MitateDB-api/docs/cloud-run-cloud-sql.md` (WP-6b)、`SECURITY.md`、`AGENTS.md` が含まれる。**0 バイト検査の走査集合は参照解決の走査集合とは別集合である** — 両者を混ぜない。**改訂前が検出しなかった理由**: `read_lines` は 0 バイトのファイルを `[]` として**読めてしまい**、`check_scan_readability` の fail 経路に乗らなかった。**実施状況: 空 `.md` 検査は 2026-09-08 に main `7d8bb0f` (実装 `f38716b`) へマージ済みであり、L10 登録 (2 つ目のコミット) は未了である。****配線は既存で足りる** (pre-commit `.pre-commit-config.yaml:16-26` と CI の `doc-refs` job `.github/workflows/ci.yml:315-326` が常時実行する)。

**同じ WP で L10 を登録する (別コミット)**: 現行の `L_REF_RE` (`:194`) は `\bL(?:Q4|[4-9])-\d{1,2}[a-z]?\b` であり **`L10-1` に一致しない** — 本書が登録前に main へ入っても `doc-refs` は赤にならないが、**それは「検査されていない」ことを意味する。** `L_REF_RE` を `L10-N` にも一致させ、`PHASE_CANONICAL` (`:208-214`) に本書のパスを足す。**script 冒頭の docstring (`:16-19`) がこの表の変更を「別個の明示コミット」と定めている**ので、**WP-1 は 2 コミットに分ける。**

**壊すとどう見えるか**: **size 判定を外すと新規テストが赤になる。** **L10 登録を外すと `L10-N` 参照が dangling として報告されない** — この不在は `doc-refs` の緑では判別できないので、**登録の完了条件は「本書に無い `L10-<N>` を別の docs に書くと赤になる」ことの実測である。**

### D-8 R-20 — 同時要求下の tail latency を実測し、判定規則で方式を決める

**(1) 計測**: **`tools/perf_baseline.py` に `--concurrency K` を足す** — **スレッドではなく adapter 自身の loop 上で K 本の coroutine を `asyncio.gather` で同時発行する** (監督裁定 2026-09-08、起草疑義 9)。**K = 1 も同じ gather 経路で測る** (経路の違う 2 点を比べない)。**測る K は {1, 3}、既定は `--n 100 --warmup 10`** — 既定 profile の `requests_per_minute` は credential あたり 600 (`r2db-api/src/r2db_api/limits.py:18`) なので、**`--n 200 --warmup 20` × K=3 では単一 credential で 660 要求となり `LIMIT_EXCEEDED` に入る。** **効いている bound は共有 surface の既定 `concurrency=32` (`:17`) であり隔離 profile の値ではない。** **既存の逐次計測と PERF 行形式は変えない (列を足す)。**

**(2) 判定規則を先に置く**: **K=3 の p50 が K=1 の p50 の 2 倍を超える** (= event loop 直列化の兆候) なら (3) を本フェーズで実施する。**超えなければ記録のみで閉じる。** **規則を先に置くのは、数値を見てから基準を作らないためである** (P-8)。

**(3) 方式 (条件付き)**: **両 peer の handler で「body 読み (async) の後の同期部分」を `starlette.concurrency.run_in_threadpool` に委譲する** (同型)。**前提の監査を実装前に行う** — `_LimitStateHolder` (`MitateDB-api/src/mitatedb_api/cell.py:744-780`) と r2db の同等物 (`service.py` の `_acquire_rate` / `_slot`) の lock、connection pool (`r2db-api/src/r2db_api/postgres.py:333`、`:586`、`MitateDB-api/src/mitatedb_api/pool.py:51`) の thread-safety を確認し、**無ければ足す。再計測して差分を記録する。**

**【追記 2026-09-08 (v1.3)。WP-8 の前提条件。§5 U-10】** **threadpool 委譲は「1 要求 1 接続 (または pool からの貸出) であり、cell が接続を跨いで共有しない」ことを先に満たす。** **MitateDB は cell ごとに `_runtime` / `_developer` の接続を 1 本ずつ保持して共有しており、そのままでは threadpool 化できない** (同じ接続を複数 thread が同時に使う形になる)。**WP-7 の判定が「超える」であっても、この前提を満たす変更を WP-8 に含めるか、フェーズ11 へ送るかは、WP-7 の結果を見て監督が裁定する。** **配備全体の資源保護そのものはフェーズ11 送りである** (計画文書 §8 の R-31)。

**根拠**: 計画文書 R-20 が「**実測前に直さない**」と定めており、**現行の `_measure` は逐次ループで同時要求を発生させられない。** **スレッドを採らないのは、測りたいのが server 側の event loop 直列化であり、client 側の GIL を混ぜないためである。**

**却下**: **uvicorn `--workers N`** (in-memory limiter が壊れ D-5 の写像で `deployment_required` になる — 目的と矛盾する)。**async psycopg への書き換え** (DB 層の全面改修。L10-4)。

**壊すとどう見えるか**: **`gather` ではなく順に `await` する形だと K=1 と K=3 の p50 がほぼ一致し、判定規則が常に「超えない」側に落ちる。** 非 vacuity は **「app 側に人工的な待ちを入れると K=3 の総所要が K=1 の 3 倍ではなく 1 倍に近づく」ことの実測**を WP の報告に添えて示す。

### D-9 R-21 — 正本文書の陳腐化を着手前に是正する (**完了**)

**決定**: **着手前に別 worktree で是正する** (Class D + A)。**2026-09-08 に完了し、main `bce2598` (実装コミット `c3d9fc9`) にマージ済みである。照合記録は §11 に置く。**

1. **`security/CONTROL_MAPPING.md` の SI-08 行**の MitateDB 記述を現行に更新する — 旧文の「remain unimplemented on this peer」は rate と concurrency については誤りである (`MitateDB-api/src/mitatedb_api/cell.py:4051` が `concurrency: "enforced"`、`:4055` が `requests_per_minute: "enforced"`。`execution_ms` は `reference_wall_clock`)。**旧文は `CONTROL_MAPPING_HISTORY.md` の `## SI-08` へ逐語で移す。** **Class D。内容は現状記述の更新であり security-contract の変更ではないことをコミットに明記する。**
2. **両 peer の README** を**現行コード・migration 一覧・Route 一覧から書き起こす** (旧文を写さない)。**Class A。**

**根拠**: 計画文書 R-21 の指示である (**本フェーズは SI-08 の統制記述にさらに 1 行足すので、足す先が誤ったままでは足せない**)。
**壊すとどう見えるか**: **機械検査が無いので、完了条件は「監査照合」であり、照合対象の逐語記録を §11 に残すこと自体が完了条件である** (`OPERATING_CONDITIONS.md` §1.5 の 40)。

### D-10 L9-15 の閉止 — C-25 (3) の駆動条件を control 面の宣言に付け替える

**決定 (監督裁定 2026-09-08、差分レビュー。v1.1 の「reader DSN を渡す」形は撤回した)**: **製品コードは変えない。** **C-25 (3) の駆動条件を、`audit_query` の「data 面の capability 文書での宣言」から「control 面 discovery が `audit_query: enabled` を宣言すること」に付け替える** (共通 suite の駆動設計の変更。**Class C、WP-5**)。**C-09 は既に control 面を読んでいるので付け替えを要さず、駆動 plug の記述だけを改める。**

**根拠**:

- **契約 C-25 の「where `audit_query` is available」は配備単位の可用性であり、権限は `control_or_audit` — control 面が host すれば成立する。**
- **v1.1 の形は空振りである** — 両 http adapter は **reader DSN を control composition に既に渡しており** (`r2db-api/conformance/conformance_adapter_r2db_http.py:1217` の `audit_dsn`、`MitateDB-api/conformance/conformance_adapter_mitatedb_http.py:926` の `MITATEDB_AUDIT_DSN`)、同 adapter のコメント自身が「reader DSN があれば control host は `enabled` を宣言する」と述べている (`:2166-2168`)。**「渡していない composition 点」は存在しない。**
- **data 面に `enabled` を書く形も採らない** — 両 peer の製品コードは data 面で `{"status": "unavailable", "authority": "control_or_audit"}` を定数で返し (`r2db-api/src/r2db_api/service.py:957`、`MitateDB-api/src/mitatedb_api/cell.py:3874`)、**host しない面で `enabled` を宣言すれば偽の宣言になる** (P-3)。
- **不成立だったのは配備ではなく共通テストの読み先である** — C-25 (3) は `adapter.capability_document()` (**data 面**、`conformance-tests/test_c25_result_request_id.py:47-48`)、C-09 は `control_credential()` + `control_capabilities()` (**control 面**、`conformance-tests/test_c09_audit_evidence.py:206-217`) を読む。**同じ性質を 2 つの面で判定していたことが L9-15 の実体である。**

**実装の形**: **(1)** `test_c25_result_request_id.py` の `_audit_query_status` を C-09 の `_audit_query_declaration` と同じ形 (control credential での `control_capabilities()` 読み) に改める。**port に新しい primitive を足さない** — `control_credential()` / `control_capabilities()` / `audit_query()` も `flush_audit_buffer` / `audit_visibility_lag_ms` も既存である (`conformance-tests/adapter.py:1231`、`:1431`)。**(2)** `CONDITIONS.md` の C-25 行の「4 plug すべてが `unavailable` なので (3) は駆動しない」という開示を実測に改める (旧文は履歴へ逐語。§6.2)。**(3) 駆動 plug は control 面で `enabled` を宣言する plug すべてである** — 既存 4 plug はいずれも control 面を読む同名 helper `_audit_query_status` を持ち (`conformance_adapter_r2db.py:820-835`、`conformance_adapter_mitatedb.py:1099-1111`、両 http adapter の同名 helper)、socket 2 plug は継承する。**裁定の見込みは「既存 http 2 plug + socket 2 plug」であり、実際の集合は宣言の実測で決まるので WP-5 の実測値を §11 に記録する** (主張と実測を混ぜない)。**(4)** 非 vacuity は C-09 の個別 guard と同じ機構 — `observed_branch` をその plug 自身の control 面の宣言が含意する枝と突き合わせる。**(5)** 既存 4 plug の宣言も製品コードも変えない。

**壊すとどう見えるか**: **駆動条件を data 面に戻すと C-25 (3) の分岐に 1 plug も入らなくなる** (フェーズ9 の状態)。**control composition から reader DSN を外すと control 面の宣言が `unavailable` に落ち、C-09 の全レジストリ guard と C-25 (3) がともに赤になる。**


### D-11 CI

**決定**: **(1)** `conformance` job に **nginx 導入 step**を足す (先例は `.github/workflows/ci.yml:349`)。**`sudo apt-get install -y nginx` の直後に `sudo systemctl disable --now nginx || sudo service nginx stop` を置く** (監督裁定 2026-09-08、起草疑義 7) — Debian 系は導入と同時に既定 conf の service を起動するので、止めないと (2) の残骸検査が常に赤になる。**(2)** socket plug と C-26 の**残骸 (プロセス・port) を job 終了時に検査する step**を足す。**照合は harness prefix 一致で行う** (prefix でスコープしない `pgrep` は runner の無関係なプロセスに当たる)。**表記は `sudo` 付きで統一する** (§8 と食い違わせない)。**(3)** **`image-pins` job** (D-6)。
**根拠**: **CI が「実サーバ起動の場」を持つことが着手条件そのものであり (§1.3 (2))、その場を作るのは本フェーズの成果物の一部である。** 残骸検査を CI にも置くのは**プロセス残骸が「次の実行を汚す」形で遅れて現れるからである。**

**壊すとどう見えるか**: **nginx 導入 step を消すと socket plug が fail する** (skip ではない)。**service 停止行を消すと残骸検査が常に赤になる。残骸検査を消すと harness の kill 漏れが CI で無音になる。**

### D-12 性能 (P-8)

**決定**: **完了ゲートに、従来の PERF 行 (逐次) + 新設の socket 列 + K=1 / K=3 の行を添える。閾値は置かない。** 形式はフェーズ8 / フェーズ9 §11.2 と同じ (`PERFRUN` 行 + `PERF` 表)、**同一 plug の版間差分のみを並記し plug 間の比較はしない** (L8-11)。**socket 2 plug は初回値として記録する。**

**`_classify_plug` (`tools/perf_baseline.py:158-201`) は `transport_kind` の宣言を読む形に改める** (監督裁定 2026-09-08、レビュー 2 の 12) — **現行は `-http` 接尾辞と `_loop` / `_client` 属性の一致を要求するが、ASGI plug と socket plug は属性形状が同一で名前しか効かず、代理指標にあたる** (`OPERATING_CONDITIONS.md` §1.7 の 52)。宣言を読めば in-process / asgi / socket の 3 ラベルが adapter の宣言 (D-1 の 4) と 1 対 1 になる。**名前と宣言が食い違う plug は従来どおり `UnknownAdapterShape` で非 0 終了する** (`:196-201`)。**同 docstring 自身が「fallback を広げず明示的に拡張せよ」と定めている。**

**`backend_calls` は socket plug でも従来どおり取れる** — socket adapter は composition を in-process で保持するので `_resolve_cell` (`:218-242`) が掴む対象がそのまま在る。**これは D-1 の再定義が副次的にもたらした性質であり、本番 composition root を別プロセスで起動する形では失われていた。**

**根拠**: P-8 (**L8-5 の閉止は「実 socket 列が加わること」そのものである**)。
**壊すとどう見えるか**: **`_classify_plug` が socket plug を `asgi-inprocess` と誤ラベルすると公開記録に誤った行が入る** — 宣言を読む形はこれを防ぐ。

### D-13 同一 idempotency key の同時送信を直列化する (**WP-6d**。新設 v1.3)

**決定 (監督確定 2026-09-08。依頼者委任と依頼者裁定「フェーズ 10 に組み込めるのであれば組み込んでください。」に基づく。§5 U-7 / U-8 / U-9)**: **同一 idempotency key の同時要求を、効果と同じトランザクション・同じ接続で直列化する。** **成果物を 2 つに分ける** — **6d-i** = 両 peer の backend lock + in-memory lock + peer-local テスト (**WP-3 に依存しない**)、**6d-ii** = **新条件 C-27** と adapter hook (**WP-3 の hook 抽出の後**)。

**根拠**: **現行は両 peer とも照会が lock を持たない。** r2db は `_idempotency_lookup` (`r2db-api/src/r2db_api/postgres.py:1188`) が素の SELECT で、`_idempotency_store` (`:1223`) の `INSERT ... ON CONFLICT (idempotency_key) DO UPDATE` に後追いを委ねる。MitateDB は照会が `_runtime` 上で自己 commit する別トランザクションであり、書き込みは同じ `ON CONFLICT DO UPDATE` である (`MitateDB-api/src/mitatedb_api/backend_postgres.py:1697` 付近。DDL 経路は `_developer` 接続に書くので**照会と書き込みの接続が違う**)。**監督は使い捨ての PostgreSQL 16 で二重実行を再現した** — read committed で同一キー 2 要求が両方とも照会結果 `None` を読み、効果行 2 件が commit され、digest が異なっても `CONFLICT` にならず後着が上書きした (計画文書 §8 の **R-24**)。**契約 1.7.0 の `idempotency.record` は「二度実行しない」と定めており、同時送信もその射程にある** — **契約の穴ではなく実装と検証の穴である。** **フェーズ9 の完了は取り消さない** — フェーズ9 が示したのは**逐次経路**の再送安全性であり、**同時送信**の再送安全性を示すのが本決定である (計画文書 §1.0d)。

**実装の形 (6d-i)**:

1. **順序は「lock → 照会 → (replay / `CONFLICT` / 続行) → 実行 → 記録 → commit」** である。**lock は key 単位の transaction-scoped advisory lock (`pg_advisory_xact_lock(hashtext(<key>))`)** であり、**key は Application ごとの DB に閉じているので Application 内一意で足りる。** **後着は先着の commit を待ってから照会する** — 同 digest なら replay、異 digest なら `CONFLICT`、**先着が失敗 (rollback) したなら新規要求として実行する。** **`ON CONFLICT DO UPDATE` の上書きは「期限切れの未回収行」のためだけに残す。**
2. **r2db**: `transact` / `apply_schema` の既存トランザクション内、**`_idempotency_lookup` の直前**に lock を取る。
3. **MitateDB の PostgreSQL backend**: **照会を自己 commit の別トランザクションから、書く側の接続** (`transact` は `_runtime`、DDL は `_developer`) **の同一トランザクション内へ移し、その前に lock を取る。** **接続が 2 本ある構造そのものは変えない** — 書く接続で lock と照会を行えばよい。 **【追記 2026-09-08。WP-8b との両立】** **フェーズ10 主セッションの裁定 (2026-09-08) で WP-8b は MitateDB の cell が要求ごとに `BoundedConnectionPool` から接続を借りて要求終了で返す形 (role ごとの共有接続 `_runtime` / `_developer` の廃止) を含む。本項の「書く側の接続」はその形では「その要求が借りた 1 本の接続」になり、lock → 照会 → 実行 → 記録が 1 要求 1 接続 1 トランザクションで閉じるという本項の不変条件はそのまま成り立つ。WP-6d-i と WP-8b のどちらが先に main へ入っても、後から入る側が接続の取得点を合わせる (`cell.py` / `backend_postgres.py` の同一ファイル別領域)。**
4. **in-memory cell** (r2db の `InMemoryCell`、MitateDB の `ApplicationCell` の dict): 単一プロセスでも uvicorn と将来の threadpool ではスレッドが並ぶので、**key 単位または cell 単位の `threading.Lock` で「照会 → 実行 → 記録」を囲む。**
5. **異キー競合 (`idempotency_entries` の件数、D-5 (ii) の区分 (iii))** は key lock では直列化されない — **表単位の定数 key の `pg_advisory_xact_lock` を件数検査の前に取る** (D-5 (ii) の追記 (2)。`LOCK TABLE ... IN SHARE MODE` は使わない)。
6. **性能**: **Application ごとの keyed write が表 lock で直列化される。** **完了ゲートの性能差分 (`OPERATING_CONDITIONS.md` §1.3 の 27) で計測して記録する。回避しない。**

**実装の形 (6d-ii) — 新条件 C-27「同一キー同時送信」**: **adapter hook で先着を照会の直後 (実行の前) に保持し、後着を送り、先着を解放する決定的な検査**である。**hook の名と形は `hold_in_flight` (C-05、port v1.12) に倣う。** 観測項目は **(i)** 同一 digest — **実行 1 回** (効果行 1、実行の監査 event 1)、後着は先着と同じ `request_id` の replay、**(ii)** 異 digest — 実行 1 回、後着は `CONFLICT` + `violated_declaration: idempotency_key`、**(iii)** **異キー 2 件を `idempotency_entries` 上限 −1 の状態で同時送信** — 1 件が `LIMIT_EXCEEDED` である。**4 plug すべてで駆動する** (http adapter は in-process の uvicorn なので monkeypatch が届く。C-05 の実例)。**socket adapter (WP-4) は継承する。** **変異注入は「lock を外すと (i) (ii) が赤になる」である。** **`CONDITIONS.md` の C-27 行は C-26 と同じ方式で先に置く** (宣言だけを置き、実行可能になるのは WP-6d-ii。§6.2)。

**契約 (U-9)**: **契約 1.8.0 の `idempotency.record` に「同時に到着した同一キーの要求も直列化され、高々 1 件が実行される。他方は先着の commit の後に再送として答えられる (replay または `CONFLICT`)。先着が失敗したなら新規要求として扱われる」の趣旨の 1 文を足す。** **1.8.0 は未公開 (branch `phase10-wp5` のみ) なので版は動かさない。** **packaged 複製 3 つを同一バイトに保つ。** **WP-5a の branch に足す追補コミットとして監督が実施する。** **【実施済み 2026-09-08。branch `phase10-wp5` の `73adbda`。WP-5a 本体は `654e23e` の時点で main `3d7f823` にマージ済みであり、追補 `73adbda` はそれに含まれないので、次のゲート束で監督がマージする】** **義務の id は `idempotency_concurrent_same_key_sends_serialized` (capability `idempotency`) であり、1.8.0 の `conditional` の 1 件目 (1) である。** 詳細は §5 U-9 の実施註である。

**C-27 とこの義務の関係**: **C-27 は、この条件付き義務 (1.8.0 の `conditional` (1)) の実行可能な条件である。** **したがって C-27 が拘束するのは「`contract_version` が 1.8.0 以上であり、かつその実装自身の `idempotency` が `unavailable` 以外である」plug に限られる** — **C-25 が 1.7.0 の宣言に結び付いているのと同じ形である** (§6.2 の C-25 行、`conformance-tests/CONDITIONS.md` の C-25 行の版 gate)。**両 peer は WP-6a / 6b の版フリップで 1.8.0 を宣言し、`idempotency` は両 peer とも `unavailable` 以外なので、フリップ後は 4 plug すべてで駆動する。** **版 gate の xfail は採らない (監督裁定 2026-09-08、U-8 追補): WP-1c 以後は CI が `xfailed == 0` を強制するので、フリップ前に C-27 を `xfail(strict=True)` で置く中間状態は CI を赤にする。したがって WP-6d-ii は WP-6a / 6b の版フリップの後に着手し、C-27 は最初から 4 plug で駆動する形で入る。順序は §8.1 の「WP-6a / 6b → WP-6d-ii」行が正本である。**

**壊すとどう見えるか**: **key lock を外すと C-27 の (i) (ii) と両 peer の peer-local 同時テストが赤になる。** **MitateDB で照会を書く側の接続の外 (自己 commit の別トランザクション) に戻すと、後着が先着の commit を待たずに読むので同じものが赤になる。** **表単位 lock を外すと C-27 の (iii) が赤になる。**

### D-14 外部レビュー 2 の小修正の束 (**WP-1c**。新設 v1.3)

**決定 (監督確定 2026-09-08。§5 U-11)**: **外部レビュー 2 が挙げた 3 件の小修正を 1 つの WP (Class B) にまとめ、WP-3 より先に main へ入れる。** **`.github/workflows/ci.yml` は WP-3 と領域が異なる** (WP-3 が触るのは conformance job の前段、本 WP が触るのは集計 step と比較 job) **ので、WP-3 は rebase で吸収する。**

1. **MitateDB の digest から `budget: {}` が落ちる不具合** (`MitateDB-api/src/mitatedb_api/cell.py:2702` の `if budget:`) を **`if budget is not None:`** に是正する (r2db は `r2db-api/src/r2db_api/service.py:1237` で既にこの形)。**是正範囲は `transact` だけではない** — **`cell.py` のスキーマ操作 3 箇所 (`create_collection` / `add_field` / `alter_field`) の digest 生成も同じ穴を持つ。** **HTTP 層は既に `digest_extra` で `budget` を渡していたが、in-process の cell 経路は渡していなかった** ので、同じ要求が経路によって別の digest になり得た。**両 peer に「budget の省略と `budget: {}` は異なる要求である」ことを示すテストを置く** — 同一キーの再送が `CONFLICT` になること、および plan digest が異なることの両方である (`digest_request` は plan digest も作るので同じ影響がある)。**計画文書 §8 の R-25。**
2. **CI に `skipped == 0` / `xfailed == 0` を強制する** — **集計 step と比較 job の両方**、**3.11 / 3.12 とも**である。**監督裁定 2026-09-08 (検査の拡張)**: **`xpassed` と `deselected` も `> 0` を赤にする** — **`xpassed` は宣言が陳腐化した xfail (実測が宣言を追い越している)、`deselected` は集計行が suite 全体を表していないことを意味し、どちらも「合格の集計が現物を覆っている」という前提を崩すからである。** **計画文書 §8 の R-26。**
3. **文書の矛盾 2 件を直す** — `r2db-api/README.md:158` を `docs/work-orders/DEPLOY_PHASE6_20260904.md` の項 9〜12 に基づく**事実のみ**で書き直し、`docs/work-orders/HANDOVER_20260908_FABLE.md` §1 に**日付付きの訂正註を追記する** (`docs/work-orders/PUBLICATION_GATE_20260906.md` §3.2 を指す。**引き継ぎ書は履歴なので書き換えない。追記である**)。**同じ陳腐化は `security/CONTROL_MAPPING.md` にも残っていた** — **SI-00〜SI-03 の受入境界 (acceptance boundary) の文が「VPS には未導入」を前提にしていたので、2026-09-05 の r2db Stage 1 の記録から書き起こす。** **`security/` を触るので、その 1 コミットは変更クラス D である** (裁定記録を添える。内容は現状記述の更新であり security-contract の変更ではない。WP-0 と同じ扱い)。**計画文書 §8 の R-28。**

**根拠**: **3 件とも「宣言・記録と現物の食い違い」であり、P-3 の面である。** **(2) は `OPERATING_CONDITIONS.md` §1.3 の 22 が合格条件として定めている値が CI では検査されていないという不整合であり、同 §1.3 の 26 (skip は未検証を許可に変える) の機械化でもある。**

**壊すとどう見えるか**: **(1)** `is not None` を `if budget:` に戻すと、両 peer の新規テストのうち MitateDB 側が赤になる。**(2)** 合成した `2807 passed, 1 skipped` の集計を食わせて緑になるなら検査が効いていない (**`xpassed` / `deselected` も同じ形で合成して赤を実測する**)。**(3)** 機械検査を持たないので**監査照合**であり、照合対象の逐語記録を残すこと自体が完了条件である。

**【実施 2026-09-08。branch `phase10-wp1c` の `5944013` (+ main `504c8b2` のマージ)。Opus のコードレビューの判定は「accept with fixes」であり、指摘の是正を反映した確定コミットは `2431e93` である】** **範囲は上記 1〜3 のとおりで、`transact` に加えてスキーマ操作 3 箇所の digest 生成と `security/CONTROL_MAPPING.md` の SI-00〜SI-03 の受入境界を含む。** **実測**: `MitateDB-api/tests` は `997 passed`、`r2db-api/tests` は `1172 passed`、`tools/tests` は `58 passed`、**CI 検査の非 vacuity は合成した集計入力で実測した** (`2807 passed, 1 skipped` / `2 xfailed` を食わせると赤)。**main へのマージは次のゲート束で監督が行う (現時点で main 未マージ)。**

---

## 4. 却下した代替案 (再提案には新しい論拠が要る)

| | 案 | 却下の根拠 |
|---|---|---|
| **A-1〜A-4** | **harness の各 peer への複製** (D-2 の代替) と、**R-18 の (b) `--max-instances=1` 固定 / (c) 共有 limiter / (d) 契約文なしの `deployment_required`** | **§5 U-4 / U-1 を正とする。** (b) は P-5 と設計原則 3 に反し「高性能が大前提」と矛盾する。(c) は P-9 に触れ新しい依存と hot path の往復を足すので**実需の記録 (R-13) を待つ** (拡張点は L10-3)。(d) は適用単位を未定義のまま残す。複製 harness は**規約 (P-6) の目的である peer 実装の独立に寄与しない。** |
| **A-5** | 相互ダイヤルによる `surfaces` の健全性検査 | **計画文書 §6 で既決の却下。本フェーズの実ダイヤルは「自分が宣言した URL に自分で到達する」ことであり、相互ダイヤルではない。** |
| **A-6** | nginx 不在時の skip | `OPERATING_CONDITIONS.md` §1.3 の 26 — **「環境が無いから確かめられなかった」を「合格」と記録しない。** |
| **A-7** | socket plug を「条件の部分集合だけ回す軽量 plug」にする | **計画文書 §5 の原文が「5・6 番目の plug」と書いており、registry の plug は required な完全 adapter である。** 部分集合 plug は追跡記録を増やすだけで証拠は減る。 |
| **A-8** | conformance に TLS を張る | **配備 smoke の領分である** (L10-5)。 |
| **A-9** | **socket adapter が本番 composition root を env だけで起動する形** (v1.0 の D-1。**監督が 2026-09-08 に撤回した**) | **現行 port (`ConformanceAdapter`) の in-process 前提と両立しない。** (1) **再起動 470 回** — `fx` は毎テスト 2 application を新規 provision するが (`conformance-tests/conftest.py:251-256`)、composition root は `R2DB_SERVE_APPS` の起動時スナップショットと per-app DSN env を要求し未知 slug は `_cell_factory` で落ちる (`r2db-api/src/r2db_api/main.py:305-320`、`:409`。MitateDB も同型 `main.py:270-289`)。(2) **r2db に limits env が無い** — 隔離 profile は `DataService(limits=_ISOLATED_APPLICATION_LIMITS, ...)` の直接構築であり (`conformance_adapter_r2db_http.py:2091-2103`)、`R2DB_MAX_*` は存在しない (同 `:2039`)。MitateDB は `config.py:173-189` に持つので**この点は peer 非対称である**。(3) **in-process の手が失われる** — `hold_in_flight` は cell の monkeypatch (`:2149` → `:721-746`)、`flush_audit_buffer` は service の直接呼び出し (`:2214-2228`)、`set_authorization_state_available` (`:1730`)、`_control_surface_absent` の route 表検査 (`:1058`)。(4) **`DROP DATABASE` の pool 順序** — `deprovision_application` は「server 側の per-app pool を先に close してから drop」を実装しており (`:2328-2343`)、別プロセスの pool は adapter から close できない。**代わりに、本番 composition root の証拠は C-26 が専用の条件として持つ** (D-1 (B))。 |

---

## 5. 裁定事項 (U-1〜U-13。**U-7〜U-13 は v1.3 の新設である**)

**本節の 6 項目は監督が確定した選択である。裁定は本節に記録し再審議しない** (計画文書 §9 の 4、`OPERATING_CONDITIONS.md` §1.7 の 51)。**両論はそのまま残す。** 根拠となる**依頼者裁定 (2026-09-07、逐語。フェーズ9 設計 §5 冒頭からの複製。言い換えない)**:

> 判断しなければならないものが出たらあなたの推奨で進めてください。後で報告してください。

**適用範囲 (監督の解釈、2026-09-08)**: **U-1〜U-6 は監督の推奨で確定し、確定内容と根拠を本書に記録して、フェーズ完了報告で依頼者に報告する** (フェーズ9 と同一の運用)。

### U-1 R-18 の形

| | **(a)+(ii) 適用単位を契約に明記し `process_ceilings` から `limit_enforcement` を導く** | (b) `--max-instances=1` に固定 | (c) 共有 limiter | (d) 契約文なしで `deployment_required` |
|---|---|---|---|---|
| **契約の変更** | **あり (1.8.0、4 片)** | なし | なし | あり (宣言値のみ) |
| **配備の自由度** | **保つ** | **失う** (水平スケール不可) | 保つ | 保つ |
| **`enforced` の意味** | **定義される** | 未定義のまま (偶然真) | 定義されないが真 | **未定義のまま** |

**(a)+(ii) は新しい依存を持たない** (既存の宣言表を 1 行広げるだけ) **のに対し (c) は hot path に往復を足す。将来の拡張点を持つのは (a)+(ii) だけである** ((c) を後から入れられる)。

**確定 (監督、2026-09-08)**: **(a)+(ii) を採る** (内容は D-5 (i)〜(v))。**契約の沈黙が共通の問題である以上、埋めるべきは契約である** — (b) は問題を配備制約で消す形で P-5 / 設計原則 3 に反し、(c) は実需の記録が無いまま依存を増やし、(d) は沈黙を半分だけ埋める。**(a)+(ii) は P-3 を配備の面に伸ばす唯一の枝であり、(c) を将来入れる道も閉じない。** **(b) / (c) / (d) は §4 A-2 / A-3 / A-4 に却下を記録する。**

### U-2 R-20 の是正を本フェーズ内で行うか

**(α) 判定規則付きで条件付き実施 (D-8 (2))** vs (β) 計測のみで次フェーズ送り。(α) は範囲が膨らみ得る (pool の thread-safety 監査) が、**判定規則を先に置くことで制御できる**。(β) は数値が悪くても放置する形になる。**確定 (監督、2026-09-08): (α)。判定規則は「K=3 の p50 が K=1 の p50 の 2 倍を超えたら実施」であり、計測の前に確定している。** **「測ったが悪かったので次フェーズ」は「先送りしない」に照らして採らない。**

### U-3 L9-15 を本フェーズで閉じるか

**(α) 閉じる (D-10)** vs (β) 範囲外。**確定 (監督、2026-09-08): (α)。** **形は差分レビュー (2026-09-08) を受けて改めた** — v1.1 の「継承した composition の control 側に audit reader DSN を渡す」は**現物では既に渡っており空振りである** (D-10 の根拠)。**閉じ方の両論**: **(α-1) data 面 capability 文書で `audit_query` を宣言する** (製品コードの変更。host しない面で宣言することになり P-3 に反する) vs **(α-2) C-25 (3) の駆動条件を control 面 discovery の宣言に付け替える** (共通 suite の駆動設計の変更)。**確定は (α-2)。製品コードにも既存 4 plug の宣言にも触らない** — **L9-15 の原文自身が「それは C-09 の駆動設計そのものに触る」と警告しており、触るべきはそちらだと判明した。** **閉止条件は §10.0 でこの形に読み替える。**

### U-4 harness の置き場

**(α) 共通 `conformance-tests/socket_harness.py`** vs (β) 各 peer に複製。規約 P-6 は peer 実装・peer テストに掛かる (`adapter.py` の先例)。(β) は**プロセス管理コードを 2 本**持つが **peer 実装の独立には寄与しない**。**確定 (監督、2026-09-08): (α)。** **同型性テストで縛れることは「複製してよい理由」にはならない** — 縛るのは、独立に到達したことに意味がある実装のためである。**peer 側に生じる同名 helper は同型性テストに載せる** (行追加は監督の pair-closing commit)。

### U-5 宣言 key 名と形

**(α) `process_ceilings` = `{"data": <int>, "control": <int>}`** vs (β) plane ごとに 2 key。(α) は `surfaces` と対称で (`CHECK` の変更も 1 key)、**検証関数・ops サブコマンド・fail-fast の形もすべて `surfaces` を写せる。確定 (監督、2026-09-08): (α)。新しい形を発明しない。**

### U-6 契約版を上げるか

**(α) 契約 1.8.0 (Class C、設計レビュー 2 回)** vs (β) 契約文なし ((d) と同じ)。(α) は契約手順一式とレビュー 1 回分の費用を伴い、**計画文書 §5 の見出しと食い違う** (訂正註 R-14)。(β) は安いが `enforced` の意味が未定義のまま残る。**確定 (監督、2026-09-08): (α)。** **計画文書の見出しは起票時の予測であって判定ではない — 予測に合わせて裁定を歪めず、正本側を R-14 の規約で直す** (§10.1)。

### U-7〜U-13 の前提 (外部レビュー 2、2026-09-08)

**U-7 以降は、依頼者が提示した 2 本目の外部レビュー (2026-09-08、基準 main `b16afdd`) を監督が現物で検証した結果の裁定である。** **依頼者裁定 (2026-09-08、逐語。言い換えない)**:

> フェーズ 10 に組み込めるのであれば組み込んでください。

**検証結果の要約と起票先は計画文書 `docs/design/ROADMAP_POST_PHASE7_V1.md` §1.0d と §8 の R-24〜R-33 である。本節はそれを再導出しない。**

### U-7 同一キー直列化の実装形

**(α) 効果と同じトランザクション・同じ接続で、照会の前に key 単位の transaction-scoped advisory lock を取る** vs (β) `ON CONFLICT DO UPDATE` の後追いに委ねたまま digest 不一致を検出する枝を足す vs (γ) 記録を別トランザクションのまま unique 制約違反を捕まえて再照会する。**(β) は実行そのものが 2 回走る事実を変えない** (再現実測で効果行が 2 件 commit された)。**(γ) は「実行 → 失敗 → 再照会」の順になり、副作用を伴う操作では成立しない。** **確定 (監督、2026-09-08): (α)。** 実装の形は **D-13** の 1〜6 である — **lock → 照会 → (replay / `CONFLICT` / 続行) → 実行 → 記録 → commit**、**key は Application ごとの DB に閉じるので Application 内一意で足りる**、**MitateDB は照会を書く側の接続の同一トランザクションへ移す (接続が 2 本ある構造は変えない)**、**in-memory cell は key 単位または cell 単位の `threading.Lock` で囲む**、**異キーの件数 bound は表単位の定数 key の advisory lock で、`LOCK TABLE ... IN SHARE MODE` は採らない** (SHARE 同士が衝突せず両者が INSERT で待ち合って deadlock する。**実装担当はフェーズ9 R-2 の前例の lock mode を現物で確認して報告する**)。**性能は完了ゲートの性能差分で計測して記録する。回避しない。**

### U-8 新条件 C-27「同一キー同時送信」を置くか

**(α) 新条件 C-27 を 1 件足す** vs (β) C-23 (再送の意味) の射程を広げる。(β) は C-23 の駆動集合と条件文を書き換えることになり、**「逐次経路で示した性質」と「同時送信で示す性質」が 1 行に混ざる。** **確定 (監督、2026-09-08): (α)。** **観測項目と hook の形は D-13 の「実装の形 (6d-ii)」である** (先着を照会の直後・実行の前に保持し、後着を送り、先着を解放する決定的な検査。**hook の名と形は `hold_in_flight` (C-05) に倣って設計担当が決める**)。**4 plug すべてで駆動し、socket adapter は継承する。** **変異注入は「lock を外すと (i) (ii) が赤になる」である。** **本フェーズの新条件は C-26 と C-27 の 2 件になる** (§6.2)。

### U-9 契約 1.8.0 に同時送信の義務を書くか

**(α) `idempotency.record` に 1 文足す** vs (β) 契約は触らず conformance 条件だけで示す。(β) は「契約が同時送信について沈黙したまま実装だけが直る」形であり、**R-18 で埋めた沈黙と同じ種類の沈黙を残す。** **確定 (監督、2026-09-08): (α)。** **趣旨は「同時に到着した同一キーの要求も直列化され、高々 1 件が実行される。他方は先着の commit の後に再送として答えられる (replay または `CONFLICT`)。先着が失敗したなら新規要求として扱われる」である。** **1.8.0 は未公開 (裁定の時点では branch `phase10-wp5` の `654e23e`。その後 main `3d7f823` にマージされたが、本フェーズの完了前であり公開はしていない) なので版は動かさない。** **packaged 複製 3 つを同一バイトに保つ。** **WP-5a の branch に足す追補コミットとして監督が実施する。**

**【実施済み 2026-09-08。branch `phase10-wp5` の `73adbda`「Phase 10 WP-5a addendum (U-9)」。WP-5a 本体は `654e23e` の時点で main `3d7f823` にマージされており、本追補はそこに含まれない — 次のゲート束で監督がマージする (現時点で main 未マージ)】** **足した義務の id は `idempotency_concurrent_same_key_sends_serialized` (capability `idempotency`) であり、`versioning.obligations` の 1.8.0 の `conditional` に 1 件として置いた。** **`structured_operations.idempotency.record` に確定文言を逐語で足し、`versioning.version_binding` の 1.8.0 段落を「無条件義務は 1 件である …… 残る 1.8.0 の義務は条件付きであり、その実装自身の `capabilities()` が `idempotency` を `unavailable` 以外と宣言している限りにおいてのみ拘束する: (1) 同じ `idempotency_key` を持つ 2 要求が同時に到着したら高々 1 件しか実行されないよう直列化され、他方は先着の commit の後に再送として答えられ (digest が一致すれば記録から、異なれば `CONFLICT`)、`idempotency_entries` の bound も同じ直列化の下で評価される」の形に差し替えた。** **随伴文書は `spec/CONTRACT_HISTORY.md` (改版註 2)、`spec/CCR_DISPOSITION.md` の従属判断 13 (新しい小項目 (c))、`spec/README.md` (marker の無い 4 値)、`conformance-tests/test_contract.py` (PIN の更新と新規テスト 1 本) である。** **`conformance-tests` は `652 passed`、契約 JSON と packaged 複製 2 本は同一バイトである。** **版は動かしていない (1.8.0 のまま)。**

### U-10 WP-8 の前提条件

**threadpool 委譲は「1 要求 1 接続 (または pool からの貸出) であり、cell が接続を跨いで共有しない」ことを先に満たす。** **MitateDB は cell ごとに `_runtime` / `_developer` の接続を 1 本ずつ保持して共有しており、そのままでは threadpool 化できない。** **確定 (監督、2026-09-08)**: **前提条件として D-8 (3) に明記する。** **WP-7 の判定が「超える」であっても、この前提を満たす変更を WP-8 に含めるか、フェーズ11 (計画文書 §8 の R-31) へ送るかは、WP-7 の結果を見て監督が裁定する。**

### U-11 小修正の束 WP-1c を独立の WP にするか

**(α) 3 件 (R-25 / R-26 / R-28) を 1 つの WP-1c (Class B) にまとめ、WP-3 より先に main へ入れる** vs (β) それぞれを既存 WP に混ぜる。(β) は WP-3 (`ci.yml`)・WP-5 (契約側) の完了条件表に無関係な行を足す形になり、**変異と完了条件の 1 対 1 が崩れる。** **確定 (監督、2026-09-08): (α)。** **`.github/workflows/ci.yml` は領域が異なる** (本 WP は集計 step と比較 job、WP-3 は conformance job の前段) **ので、WP-3 は rebase で吸収する。** **worktree は `phase10-wp1c` である。** 内容は **D-14** の 1〜3 である。**追加の確定 (監督、2026-09-08。CI 検査の拡張)**: **CI の検査は `skipped` / `xfailed` に加えて `xpassed` と `deselected` も `> 0` を赤にする** — **`xpassed` は宣言が陳腐化した xfail、`deselected` は集計行が suite 全体を表していないことを意味するからである** (`OPERATING_CONDITIONS.md` §1.3 の 22 / 26)。**実施は branch `phase10-wp1c` の `5944013` (確定コミットは `2431e93`) であり、範囲は D-14 の実施註のとおり `transact` に加えてスキーマ操作 3 箇所と `security/CONTROL_MAPPING.md` の SI-00〜SI-03 を含む。**

### U-12 WP-3 の追跡是正 (follow-up) 項目

**`sweep_orphans` に `pid <= 0` の明示 guard (pidfile のみ削除、signal しない) とテスト 1 本を足す。** **所有者検査 (prefix marker 一致) は既に在り、marker 検査が先行するので実害経路は無い** (監督裁定 2026-09-08)。**確定 (監督、2026-09-08)**: **guard は明示に置く。** **本設計の追記先は D-2 である。** **実施の形 (2026-09-08)**: **WP-3 は main `6055c69` にマージ済みだったので rework ではなく main に対する follow-up として実施した** — **branch `phase10-wp3f` の `ea237e5`、テストは `test_sweep_orphans_never_signals_a_non_positive_pid`、変異の実測あり (D-2 の実施註)。次のゲート束でマージする。**

### U-13 フェーズ11 へ送るもの

**確定 (監督、2026-09-08): 次の 5 件は本フェーズの範囲外とし、計画文書 §8 に起票する。** **(1)** 両 peer の最低共通機能プロファイルと単一シナリオ検査 (**R-29**。**R-23** / **R-16** と対)、**(2)** SI-00 の境界と 1 プロセス複数 Application DSN の裁定 (**R-30**。**版付きの security-contract 決定**)、**(3)** 配備全体の資源保護 (**R-31**。**本フェーズが扱うのは宣言の正直さまでである**)、**(4)** 検証 seam と同型性の分離 (**R-32**。**R-22** と一緒。**WP-1c のコードレビューが見つけた `create_collection` の死んだ `destructive` 引数 = R-33 も同じ行き先である**)、**(5)** 「現在地」を入口となる 1 文書に集約し完了ゲートごとに更新する規約 (**R-28** の (3)。開発プロセス衛生 v2)。**いずれも本フェーズの完了条件には入れない** — 入れると範囲が閉じない。

---

## 6. conformance への影響

### 6.1 registry — plug 6 件と `composition_roots` 節

`conformance-tests/registry.json` を **4 件 → 6 件**にし、**新しい節 `composition_roots` を足す。**

| plug | `transport_kind` | 宣言表経由の `surfaces` | `audit_query` (data 面 / 隔離 profile) |
|---|---|---|---|
| `r2db-api` / `MitateDB-api` | `in_process` | — | `unavailable` (不変) |
| `r2db-api-http` | `asgi` | 通らない (LQ4-11。不変) | `unavailable` (不変) |
| `MitateDB-api-http` | `asgi` | 通る (不変) | `unavailable` (不変) |
| **`r2db-api-socket`** (新設) | **`socket`** | 通らない (注入経路を継承。値は実 URL) | `unavailable` (継承。**control 面は `enabled`** — D-10) |
| **`MitateDB-api-socket`** (新設) | **`socket`** | 通る (継承) | `unavailable` (継承。**control 面は `enabled`** — D-10) |

**`composition_roots` 節** (新設): 各 peer の launcher (`<peer>/conformance/real_server_<peer>.py`) を 1 件ずつ登録する。**C-26 はこの節を読んで launcher ごとに観測し、registry-guards で「2 件以上ある」ことを assert する** (非 vacuity。D-1 (B) の 7)。

**既存 4 plug の宣言と挙動は変えない。ただし 3 点を除く**: **(1)** `transport_kind` は既定を持たない抽象属性なので既存 4 adapter も宣言 1 行ずつを足す (**宣言値は現状どおりで挙動は変わらない**)。**(2) `MitateDB-api-http` の fixture seed が 1 行増える** — `process_ceilings` の起動時 fail-fast (D-5 (ii)) は**実 composition root を通る同 plug を構築時に落とす**ので、`surfaces` の seed の隣に `process_ceilings` の seed を、migration 一覧に `0011` を足す (`conformance_adapter_mitatedb_http.py:292-305`、`:334-347`)。**r2db HTTP plug は宣言表を読まないので無傷である** (`:1030-1033` は r2db 側) — **この非対称は LQ4-11 が記録しているものであり本フェーズが作るものではない。** **(3) 両 http adapter に client factory と `surfaces` 値の hook を抽出する** (D-1 (A) 6)。**挙動は不変であり、その不変性は「抽出前後で 4 plug の集計行が一致すること」で固定する** (WP-3)。

**`audit_query` の data 面の列は 6 plug すべてで `unavailable` のまま変わらない** — **付け替え後の C-09 / C-25 (3) の駆動条件は control 面 discovery の宣言であり、この列ではない** (D-10)。

### 6.2 条件ごとの改訂点 (**新条件 C-26 を 1 件起票する**)

**枠 §6 は「新条件は起票しない」と定めていたが監督が 2026-09-08 に再定義した** — **本番 composition root の証拠は既存条件の射程拡張では担えない**。**C-26 を 1 件だけ新設する。** **【追記 2026-09-08 (v1.3)。上の文は v1.1 時点の原文であり、消さずに残す】** **外部レビュー 2 の検証 (§5 U-8) により新条件はもう 1 件増え、本フェーズの新設は C-26 と C-27 の 2 件である。** **C-27「同一キー同時送信」は既存条件の射程拡張では担えない** — **C-23 は逐次経路の再送の意味を固定する条件であり、同時送信の直列化を混ぜると 1 行に 2 つの性質が同居する** (D-13、§5 U-8)。

| 条件 | 本フェーズの改訂 |
|---|---|
| **C-05** | **(1)** concurrency note の「in-process only (real-socket/reverse-proxy concurrency is L7-2)」を socket plug で解消したことに改める。**(2)** honest limits に **「`enforced` の真実性のうちプロセス横断の同時性は、共通 suite が topology を観測できないので peer-local pin と配備規律と C-26 (4) の実起動観測が担う」**を足す (D-5 (iv))。**(3)** proxy が bound を隠していないこと (`client_max_body_size 0` と temp path 明示) を開示する (D-3)。 |
| **C-09** | **駆動条件は変えない** — C-09 は既に control 面の宣言 (`control_credential()` + `control_capabilities()`) を読んでおり付け替えを要さない (`test_c09_audit_evidence.py:206-217`。D-10)。**改めるのは駆動 plug の記述だけである** (全レジストリ guard は registry から導くので socket 2 plug は自動で射程に入る)。 |
| **C-19** | **honest limits (a) の「実ダイヤルには新しい port primitive が要る、監督レビュー待ち」は本フェーズで解消したことを明記する。(b) を「socket plug では実ダイヤルである (応答が名乗った URL へ新しい client で実 TCP GET し同じ文書が返る。data / control の両面)。in-process / ASGI plug では従来どおり自己整合である」に改訂する** (D-4)。**枝の判定は `transport_kind == "socket"`、非 vacuity は registry を読む形。** |
| **C-25** | (3) の監査行照合が 0 plug だった状態 (L9-15) を改め、**駆動条件を data 面の capability 文書から control 面 discovery の `audit_query` 宣言に付け替える** (D-10)。**「4 plug すべてが `unavailable` なので (3) は declared-out-of-scope」という現行の開示を実測に改める** (旧文は履歴へ逐語)。**非 vacuity は C-09 の個別 guard と同じ機構** (`observed_branch` を control 面の宣言が含意する枝と突き合わせる)。 |
| **C-26** (**新設**) | **`composition_roots` に登録された launcher ごとに D-1 (B) の 1〜6 を観測する。** SI-08 / SI-14 に紐づく。**変更クラス C** (`conformance-tests/` 配下 + `CONDITIONS.md` に 1 行追加)。 |
| **C-27** (**新設。v1.3**) | **同一 idempotency key の同時送信を、adapter hook で先着を照会の直後 (実行の前) に保持する形で決定的に駆動する** — (i) 同一 digest は実行 1 回 + 後着が同じ `request_id` の replay、(ii) 異 digest は実行 1 回 + 後着が `CONFLICT` (`violated_declaration: idempotency_key`)、(iii) 異キー 2 件を `idempotency_entries` 上限 −1 の状態で同時送信すると 1 件が `LIMIT_EXCEEDED` (D-13)。**SI-11 / SI-08 / SI-14 に紐づく (C-23 と同じ 3 つ)。****4 plug で駆動し socket 2 plug は継承する。** **変更クラス C。** **行は C-26 と同じ方式で先に `CONDITIONS.md` に置き (宣言のみ)、実行可能になるのは WP-6d-ii である。** **契約上の位置づけ: C-27 は 1.8.0 の条件付き義務 `idempotency_concurrent_same_key_sends_serialized` (`conditional` の (1)。branch `phase10-wp5` の `73adbda`。**WP-5a 本体は main `3d7f823` に入っており、この追補だけが次のゲート束でのマージ待ちである**) の実行可能な条件であり、拘束するのは 1.8.0 を宣言し、かつ `idempotency` が `unavailable` 以外である plug に限られる** — **C-25 が 1.7.0 の宣言に結び付いているのと同じ形である** (D-13)。 |

**`CONDITIONS.md` の更新規約に従う** — 訂正は現行行を書き換え、**旧文は `CONDITIONS_HISTORY.md` の当該 ID 見出しへ逐語で移す** (同 `:5-19`)。**なお本書の `C-26` 参照は、行が `CONDITIONS.md` に入るまで `check_doc_refs` が dangling として報告する** — フェーズ9 の C-20〜C-25 (設計 `95b57bf` → 条件 `ca8920c`) と同じ経過であり、**WP-5 / WP-6c の完了で解消する。****セル長**: `test_conditions_register.py:56` の **`MAX_CELL_LENGTH = 3000`** に対し**現行の Status セルは C-05 が 2,962 字、C-09 が 2,950 字、C-19 が 2,944 字である** (2026-09-08 実測)。**改訂は「足す」だけでは収まらず旧文の移送を伴うが、移送は長さ対策ではなく更新規約そのものの履行である。**

### 6.3 adapter port と `COLLECTION_FLOOR`

**`transport_kind` の追加 (D-1 の 4) に伴い `docs/design/CONFORMANCE_ADAPTER_V1.md` を v1.13 → v1.14 に上げ § を 1 つ新設する** (版数の正本は同文書 `:5-11` の文書情報行である)。
**`COLLECTION_FLOOR` の現在値は 2807** (フェーズ9 完了ゲートで 2340 → 2807)。**2 plug 増と C-26 の新設で収集数が大きく増えるが、更新は完了ゲートで監督のみが行い WP の途中では上げない** (`OPERATING_CONDITIONS.md` §1.3 の 25)。

---

## 7. Security Invariants との関係

**新しい共通 Security Invariant は足さない。** **Security Invariants は capability の許可リストではなく、守るべき安全成果の集合である** (`CLAUDE.md`)。**本フェーズは新しい安全成果を導入せず、既存の安全成果を配備の単位で検査可能にする。**

| invariant | 本フェーズの要素 | 新たに検証可能にする性質 |
|---|---|---|
| **SI-08 (Bounded Resource Consumption)** | D-5、**C-26**、D-3、D-8 | **新しい class も新しい bound も足さない** — 足すのは「その bound が何について成り立つと主張しているか」の定義である。**(i) proxy が app の bound を隠していないこと** (D-3。SI-08 は proxy による強制を明示的に許すので、拒否の主体が app であることは別に示す必要がある)。**(ii) `enforced` の宣言が宣言されたプロセス数と整合していること** — **C-26 (4) が ceiling 1 と 2 の 2 通りの実起動で「宣言値 → `limit_enforcement` の写像が成立すること」を観測する。これが 1.8.0 の義務を共通 suite で担う唯一の場である。実プロセス数そのものは観測しない** — **topology と宣言の一致は runbook 規律 + 配備後チェックが担い** (LQ4-15 と同じ射程)、**観測できない部分は C-05 と L10-2 で開示する。** |
| **SI-14 (Security-Relevant Auditability)** | D-10、**C-26** | **新しい監査イベントも新しい相関キーも足さない** — 足すのは、既に契約が定めた相関 (C-25 (3)) を共通 suite で駆動させる**判定の面の是正**である (L9-15 の閉止。D-10)。**C-26 は、その相関が「本番 composition root で組んだ control 面」でも成立することを、`tools/deploy_smoke.py` の実行 (D-1 (B) の 3) を含めて観測する。** |
| **SI-10 (Error and Information Non-Disclosure)** | `process_ceilings` の宣言表への追加 | **既存で担保される。** Q4 D-2 の規律 (**公開 capability document に現れる値のみを置き、秘密・資格情報・内部ホスト名は置かない**) を満たす — 値は 2 つの整数であり、その帰結は公開文書に現れる。 |
| **その他** | — | **application 隔離・認証・認可・破壊操作の扱いを 1 バイトも変えない。** |

**`security/CONTROL_MAPPING.md` の SI-08 行に `process_ceilings` と C-26 の統制を足す** (Class D)。**足す先は WP-0 (D-9) が現行に書き直した後の行である。** 旧文の履歴への移動は `CONTROL_MAPPING_HISTORY.md` の規約に従う。

---

## 8. WP 分割 (作業指示書で確定する)

**作業指示書は WP ごとの Change Set Manifest であり、必須 8 項目 (目的 / 読むべき正本 / 触るファイル / 触らないファイル / 完了条件↔変異の 1 対 1 表 / 検証コマンドと集計行の期待形 / テンプレート番号 / 変更クラス) はそちらで埋める** (計画文書 §9 の 9)。**本節は目的・主に触るファイル・依存順・変更クラスだけを置き、完了条件と変異は作業指示書に寄せる** (変異の出所は各 D の「壊すとどう見えるか」)。

| WP | 目的 | 主に触るファイル | 依存 / 並行 | クラス |
|---|---|---|---|---|
| **WP-0** (**完了**) | R-21 の着手前是正 (D-9) | `security/CONTROL_MAPPING.md` / `CONTROL_MAPPING_HISTORY.md`、両 peer の README | 最初。**main `bce2598` にマージ済み** (§11) | **D** + **A** (**分けて出す**) |
| **WP-1** (**空 `.md` 検査は完了**) | 空 `.md` 検査 + L10 登録 (D-7) | `tools/check_doc_refs.py` と対応テスト | 依存なし。**`f38716b` / merge `7d8bb0f` 済み。L10 登録の 2 つ目のコミットが残る** | **B** |
| **WP-1c** (**新設 v1.3**) | 外部レビュー 2 の小修正の束 (D-14。R-25 / R-26 / R-28) | `MitateDB-api/src/mitatedb_api/cell.py` (`transact` と**スキーマ操作 3 箇所** `create_collection` / `add_field` / `alter_field` の digest)、両 peer の `tests/`、`.github/workflows/ci.yml` (**集計 step と比較 job のみ**)、`r2db-api/README.md`、`docs/work-orders/HANDOVER_20260908_FABLE.md` (**追記のみ**)、**`security/CONTROL_MAPPING.md` (SI-00〜SI-03 の受入境界。この 1 コミットは D)** | **即時。実装は branch `phase10-wp1c` の `5944013` (確定は `2431e93`)、次のゲート束でマージする。** **実施の経過: WP-3 が先に main `6055c69` へ入ったので、WP-1c は main の WP-3 の上に載る形になった** (`ci.yml` は領域が異なるので競合しない)。**WP-3 以外のすべてと並行可** | **B**。**`security/CONTROL_MAPPING.md` を含むので、そのコミットは D 扱いである** (裁定記録を添える。内容は現状記述の更新であり security-contract の変更ではない) |
| **WP-2** (**完了**) | R-19 の配備面反映 (D-6) | `MitateDB-api/docker/Dockerfile`、r2db の runbook 2 本と provision script、`.github/workflows/ci.yml` (`image-pins`) | **`79958a7` / merge `c9a937a` 済み** (`ci.yml` の重なりは WP-3 が後続する形で解消済み) | **B** |
| **WP-3** (**完了**) | 実 socket の場を作る + **基底 http adapter の hook 抽出** (D-1 (A) / D-2 / D-3 / D-11 / D-12) | `conformance-tests/socket_harness.py` (新設)、`adapter.py` (`transport_kind`)、`docs/design/CONFORMANCE_ADAPTER_V1.md` (v1.14)、`registry.json`、`conftest.py`、`tools/perf_baseline.py` + README、`.github/workflows/ci.yml`、**`r2db-api/conformance/conformance_adapter_r2db_http.py` と `MitateDB-api/conformance/conformance_adapter_mitatedb_http.py`** (**hook 抽出のみ。挙動不変**) | **WP-1 / WP-2 の後、WP-4 の前。`tools/perf_baseline.py` で WP-7 と重なるので WP-3 → WP-7。** **main `6055c69` にマージ済み** (branch の実装コミットは `8d39260`。adapter port は `CONFORMANCE_ADAPTER_V1.md` v1.14、`ci.yml` は nginx の導入と残骸検査) | **C**。**v1.3 の追跡是正 1 件は main に対する follow-up として実施した** — `sweep_orphans` の `pid <= 0` guard とテスト 1 本 (branch `phase10-wp3f` の `ea237e5`。D-2 の追記、§5 U-12) |
| **WP-4a / WP-4b** | 各 peer の socket adapter (D-1 (A) / D-4 / D-10) | 各 peer の `conformance/conformance_adapter_*_socket.py` (新設) | **WP-3 の後。4a と 4b は並行可** | **C** — **宣言値 (`transport_kind` / `audit_query`) に触り、peer の `conformance/` は共通 suite の実現部だからである** (P-3。監督裁定 2026-09-08)。**同名 helper の pair-closing commit は D** |
| **WP-5** | 契約 1.8.0 + CONDITIONS 4 行の改訂 + **C-25 (3) / C-09 の駆動条件の付け替え** (D-5 (i)(v) / D-4 / D-3 / **D-10**) | 契約 JSON 3 複製、`spec/` の companion 一式 (`CONTRACT_HISTORY.md` / manifest / `CCR_DISPOSITION.md` の従属判断 13 / catalog)、`CONDITIONS.md` と履歴、C-05 / C-09 / C-19 / C-25 の各テストと契約 PIN テスト (**C-25 は `_audit_query_status` を control 面読みに改める。C-09 は駆動 plug の記述のみ**) | **WP-4 の後。単独。** **WP-5a (契約 1.8.0 の公開部分) は `654e23e` の時点で main `3d7f823` にマージ済みである** (§11.2) | **C**。**v1.3 の追補 1 件を含む** — 契約 1.8.0 の `idempotency.record` に同時送信の直列化義務を 1 文足す (§5 U-9。**版は動かさない。監督が WP-5a の branch に追補コミット `73adbda` として実施済み。main へは次のゲート束でマージする**) |
| **WP-6a / WP-6b** | `process_ceilings` (D-5 (ii)(iii)(iv)) + 版フリップ | **6a** = `r2db-api/migrations/0012_*.sql` (新設)、`platform_declarations.py` / `ops.py` / 両 composition root / `service.py` / `control_plane.py`、`tests/`、配備手順 (**宣言 step と upgrade 順序。LQ4-24 を参照**) / **6b** = `MitateDB-api/migrations/0011_process_ceilings.sql` (新設。**`_upgrade.sql` で終わらせない**)、同型の src 一式、`tests/`、`docs/cloud-run-cloud-sql.md` (Invariant 1 の一般化)、**http adapter の seed 1 行 + migration 一覧** | **WP-5 の後。6a と 6b は並行可。版フリップは pair-closing で 1 コミットずつ** | **C**。**pair-closing commit (`_ISOMORPHIC_TARGETS` の増減) は D** |
| **WP-6c** | **C-26 の新設** (D-1 (B)) | 両 peer の `conformance/real_server_<peer>.py` (新設)、`conformance-tests/test_c26_composition_root.py` (新設)、`registry.json` (`composition_roots`)、`CONDITIONS.md` (C-26 行)、`socket_harness.py` (subprocess 起動関数)、**`conformance-tests/conftest.py`** (**C-26 の item を launcher ごとの `xdist_group` に置く。D-1 (B) 8**) | **WP-6 の後** (写像と fail-fast が要る)。**`CONDITIONS.md` で WP-5 と重なるので直列。`conftest.py` で WP-3 と重なるので WP-3 → WP-6c (依存順で既に成立)。単独** | **C**。**launcher の同名 helper の pair-closing commit は D** |
| **WP-6d-i / WP-6d-ii** (**新設 v1.3**) | 同一 idempotency key の同時送信の直列化 (D-13。R-24) | **6d-i** = `r2db-api/src/r2db_api/postgres.py` と in-memory cell (`structured.py`)、`MitateDB-api/src/mitatedb_api/backend_postgres.py` と `cell.py`、両 peer の `tests/test_idempotency_*.py` / **6d-ii** = `conformance-tests/test_c27_concurrent_same_key.py` (新設)、`conformance-tests/adapter.py` と 4 adapter (hook)、`conformance-tests/CONDITIONS.md` (C-27 行) | **6d-i は WP-3 に依存しない (今すぐ着手可、worktree `phase10-wp6d`)。触るファイルが重なるもの以外すべてと並行可。** **6d-ii は WP-3 の hook 抽出の後。WP-4 と並行可。** **WP-6a / 6b (migration + 宣言) とはファイルが分離している** | **C** — **宣言と条件 (`CONDITIONS.md` / 共通 suite) に触るからである。** **同名 helper の pair-closing commit は D** |
| **WP-7** | R-20 の計測と判定 (D-8 (1)(2)) | `tools/perf_baseline.py`、`tools/PERF_BASELINE_README.md` | **WP-3 の後** (同一ファイル)、**WP-4 の後** (socket plug が要る)。WP-5 / WP-6 と並行可 | **B** |
| **WP-8a / WP-8b** | **条件付き** (判定が「超える」ときのみ) — threadpool 委譲 (D-8 (3)) | 各 peer の `http.py` / `control_http.py` (+ 必要なら pool / service) と `tests/` | **WP-7 の後。8a と 8b は並行可。** **前提条件 (v1.3、§5 U-10)**: 1 要求 1 接続 (または pool からの貸出) で cell が接続を跨いで共有しないこと — MitateDB の `_runtime` / `_developer` の cell 単位共有はそのままでは threadpool 化不可であり、前提を満たす変更を本 WP に含めるかフェーズ11 へ送るかは WP-7 の結果を見て監督が裁定する | **B**。**`_ISOMORPHIC_TARGETS` 登録 helper の本体に触れば C** |
| **WP-9** | 完了ゲート + 記録 | `COLLECTION_FLOOR`、本書 (§9〜§11)、計画文書 (§1 / §5 / §8 + 訂正註)、作業指示書、第 17 次ハンドオーバー | **最後。単独** | **C** |

### 8.1 触るファイルの重なり (実ファイル名レベルの確認)

| 組 | 重なり | 解消 |
|---|---|---|
| **WP-0 × WP-6 / §7** | `security/CONTROL_MAPPING.md` の SI-08 行 | **順序** (WP-0 は完了済みなので以降は現行行の上に足す) |
| **WP-2 × WP-3** | `.github/workflows/ci.yml` | **直列 (WP-2 → WP-3)** |
| **WP-3 × WP-7** | `tools/perf_baseline.py`、`tools/PERF_BASELINE_README.md` | **直列 (WP-3 → WP-7)** (監督裁定 2026-09-08、レビュー 2 の 14 (ii)) |
| **WP-4 × WP-6b** | MitateDB の socket adapter は http adapter を継承するので、**6b の seed 追加が 4b の挙動に効く** | **順序 (WP-4 → WP-6b)**。**6b が seed を足すまで宣言表を通る MitateDB plug は fail-fast で落ちる** — この依存を作業指示書に明記する |
| **WP-5 × WP-6a / WP-6b** | 契約 packaged 複製 | **直列 (WP-5 → WP-6)**。WP-5 が 3 複製を同一バイトに更新し、WP-6 は `contract_version` の宣言値だけを動かす |
| **WP-5 × WP-6c** | `conformance-tests/CONDITIONS.md` | **直列 (WP-5 → WP-6c)** |
| **WP-3 × WP-6b** | `MitateDB-api/conformance/conformance_adapter_mitatedb_http.py` (WP-3 は hook 抽出、6b は seed 1 行) | **順序 (WP-3 → WP-6b)**。依存順で既に成立する |
| **WP-3 × WP-6c** | `conformance-tests/conftest.py` (WP-3 は遅延起動、6c は C-26 の group) | **順序 (WP-3 → WP-6c)**。依存順で既に成立する |
| **WP-1c × WP-3** | `.github/workflows/ci.yml` | **順序 (WP-1c → WP-3)**。**領域が異なる** (WP-1c は集計 step と比較 job、WP-3 は conformance job の前段) ので **WP-3 が rebase で吸収する** |
| **WP-1c × WP-6d-i** | MitateDB の `cell.py` (WP-1c は digest の `if budget is not None:`、6d-i は idempotency の lock) | **順序 (WP-1c → WP-6d-i)**。**関数が違う** (`digest_request` と照会・記録の経路) が同一ファイルなので直列に取り込む |
| **WP-6d-i × WP-6a / WP-6b** | 両 peer の `src/` (6d-i は idempotency の lock、6a / 6b は `process_ceilings` の宣言機構と区分 (iii) の lock) | **順序 (WP-6d-i → WP-6a / WP-6b)**。**`idempotency_entries` の件数 bound は 6a / 6b の担当であり、同一キーの直列化は 6d-i の担当である** (D-5 (ii) の追記 (1))。**同じ関数に両者が入るので直列にする** |
| **WP-6d-ii × WP-5 / WP-6c** | `conformance-tests/CONDITIONS.md` (C-27 行) | **直列**。**C-27 の行は C-26 と同じ方式で先に置き (宣言のみ)、6d-ii が `executable` に改める** |
| **WP-6d-ii × WP-3 / WP-4** | `conformance-tests/adapter.py` と 4 adapter (hook 追加) | **順序 (WP-3 → WP-6d-ii)**。**WP-4 とは並行可** (socket adapter は hook を継承する) |
| **WP-6d-ii × WP-6a / WP-6b** (**追補 2026-09-08**) | 版フリップ (両 peer の `contract_version` 1.8.0) | **順序 (WP-6a / 6b → WP-6d-ii)**。C-27 は 1.8.0 の条件付き義務の実行可能条件であり、フリップ前に入れると xfail を要して CI (`xfailed == 0`、WP-1c) が赤になる (D-13) |
| **WP-1 × WP-2**、**WP-4a × WP-4b**、**WP-6a × WP-6b**、**WP-8a × WP-8b**、**WP-9 × 他** | **0** | peer 分離 / ファイル分離。同型性表への行追加は監督の pair-closing commit |

**同一 peer の `tests/` に複数 WP がファイルを足す場合は、WP ごとにファイル名の接頭辞を分ける** (`OPERATING_CONDITIONS.md` §1.2 の 17)。本フェーズでは WP-6 (`test_process_ceilings_*.py`) と WP-8 (`test_threadpool_*.py`) が該当する。

---

## 9. 完了ゲート

1. **root suite の単独実行** `./.venv/bin/python -m pytest -q -n 5 --dist loadgroup` (監督がリポジトリルートで単独実行。ローカル PG の `max_connections = 300` が前提): **`failed` = 0 / `skipped` = 0 / `xfailed` = 0**、および **`pg_database` の前後差分 0** (`OPERATING_CONDITIONS.md` §1.3 の 19〜23)。
2. **socket plug と C-26 のプロセス・port 残骸が 0** — ゲート実行の前後で uvicorn (thread / subprocess) と nginx が 1 件も残っていないこと。**照合は harness prefix 一致で行う** (D-2 (f) / D-11 の 2)。**本フェーズで新設する検査項目である。**
3. **CI の 3.11 job の集計行が 1 と一致すること** (`tally-consistency` 緑)。**`conformance` job が `timeout-minutes: 30` 内に収まり所要時間を §11 に記録すること** (L10-1)。**この 30 分予算は C-26 の所要 (launcher 2 本 × 起動 2 回 = 計 4 回の composition root 起動と、その間の宣言・nginx・`deploy_smoke`) を含めて評価する** — **launcher ごとの `xdist_group` で直列化は 2 本ぶんまでに留まる** (D-1 (B) 8)。**`image-pins` job が緑** (D-6)。**`doc-refs` job が、空 `.md` 検査と L10 登録が入った後の版で緑** (D-7)。
4. **契約 1.8.0 の記録**: 契約 JSON と packaged 複製 2 本の **sha256 が 3 本一致**することを §11 に記録する (値はフェーズ9 から必ず動く)。`spec/OPERATION_CATALOG.json` の再生成一致テストが緑。**両 peer の `contract_version` が 1.8.0** (4 箇所) と **C-19 の data 面 / control 面一致 assert が緑。**
5. **`COLLECTION_FLOOR` をゲート時の実測値へ更新する** (着手時点は 2807)。**更新は監督のみ。**
6. **性能差分を §11 に記録する** (D-12) — `tools/perf_baseline.py` を**単独実行**し、フェーズ9 §11.2 と**同形式**で記録する。**socket 2 plug は初回値。K=1 / K=3 の行を添える。閾値は無く** (P-8)、**plug 間の比較はしない** (L8-11)。
7. **6 plug すべてで全条件が緑** — registry 6 件が `required: true` であり **どの plug も skip されないこと。**
8. **非 vacuity の実測**: **(a)** C-19 の実ダイヤル枝が socket 2 plug の data / control 両面で観測されたこと、**(b)** C-25 (3) の監査行照合が **control 面 discovery の `audit_query` 宣言を駆動条件として観測されたこと** — **駆動した plug 名と件数を §11 に記録する** (見込みは既存 http 2 plug + socket 2 plug。実際の集合は実測で決まる。L9-15、D-10)、**(c)** C-05 の concurrency 枝が socket 2 plug で駆動したこと (L8-6)、**(d) C-26 の 6 項目が両 launcher で観測されたこと**、**(e) `composition_roots` が 2 件以上であること** — 集計行または `observed_branch` の実測で監督が確認し §11 に記録する。**`--dist loadgroup` では plug ごとに worker が分かれるので、registry を読む guard と実測記録を併用する。**
9. **`CONDITIONS.md` の全 Status セルが `MAX_CELL_LENGTH` (3000) 以内**、および**改訂した 4 行の旧文が `CONDITIONS_HISTORY.md` に逐語で在ること。**
10. **既存配備の upgrade 手順が文書化されていること** — **migration → `ops declare-process-ceilings` → 再起動**の順序と **LQ4-24 への参照**が両 peer の配備文書に在ること (D-5 (iii))。
11. **全 WP が常設規律 7 項目と速度規律 5 項目を満たすこと** (`OPERATING_CONDITIONS.md` §1.5 / §1.6)。**作業指示書の「完了条件番号 → 変異」対応表に対応の無い行が無いこと。** **変異を持たない完了条件は、照合対象の逐語記録を §11 に残すこと自体を完了条件とする。**
12. **設計レビュー 2 回** (本書 v1.1 がその反映版)。**§5 U-1〜U-6 の確定が §5 に記録され、契約 1.8.0 の確定文言が確定文ファイルから逐語で複製されていること** (常設規律 4)。**計画文書 §1 / §5 / §8 を更新し §10.1 の訂正註 2 件を入れ、第 17 次ハンドオーバーを置くこと** (R-14、計画文書 §9 の 6)。
13. **フェーズ完了報告で依頼者に問うこと**: **U-1〜U-6 の列挙**と、**R-22 (`CONTROL_MAPPING.md` の再編を R-21 の是正と同時に行うか) の問い** (§1.2)。

**【追記 2026-09-08 (v1.3)。外部レビュー 2 の取り込みがゲートに足す 4 項目。§5 U-7〜U-13、§3 D-13 / D-14】** **1〜13 は 1 つも撤回しない。**

14. **C-27 が条件の集計に現れること** — **WP-6d-ii が入った後の集計で C-27 が `executable` として数えられ、4 plug (socket 2 plug は継承で計 6 plug) で駆動し、どの plug でも skip されないこと。** **非 vacuity の変異は「照会の前に置いた key 単位の advisory lock を外すと C-27 の (i) (ii) と両 peer の `tests/test_idempotency_concurrency.py` が赤になる」であり、変異を実際に注入して赤を観測し、駆動した plug 名と件数を §11 に記録する** (D-13、§5 U-8。**8 の (a)〜(e) と同じ扱いで (f) として並べる**)。**本フェーズの新条件は C-26 と C-27 の 2 件であり、条件の総数は 2 件増える** (§6.2)。
15. **WP-6d の性能差分を記録すること** — **表単位の件数 lock の下で Application ごとの keyed write が直列化される影響を、6 の R-20 の計測の隣に同じ形式で置く** (`OPERATING_CONDITIONS.md` §1.3 の 27。フェーズ9 §11.2 と同形式の `PERFRUN` 行 + `PERF` 表、同じ `--warmup` / `--n`、**K=1 / K=3**)。**閾値は置かず、回避もしない** (P-8、D-13 の 6)。**6 の計測と本項は同一の実行から取り、どちらが lock 導入前後のどちらであるかを §11 に明記する。**
16. **CI の `skipped == 0` / `xfailed == 0` / `xpassed == 0` / `deselected == 0` の強制が緑で見えること** — **WP-1c が集計 step と比較 job の両方に置いた検査が、`conformance (Python 3.11)` と `conformance (Python 3.12)` の両方で緑であること** (`OPERATING_CONDITIONS.md` §1.3 の 22 / 26、D-14、§5 U-11)。**合成した集計入力 (`<N> passed, 1 skipped` / `2 xfailed`) で赤になることを WP-1c で実測済みであることを §11 に記録する。**
17. **台帳の閉止と持ち越しを記録すること** — **計画文書 §8 の R-24 / R-25 / R-26 / R-27 / R-28 (1) (2) の閉止行を書き、R-28 (3) と R-29 / R-30 / R-31 / R-32 / R-33 はフェーズ11 へ開いたまま送ることを第 17 次ハンドオーバーに書く** (§5 U-13、計画文書 §8)。**「閉じた」と書けるのは閉止条件を実測で突合した行だけである** (§10.0 と同じ規約)。

---

## 10. 台帳 (本フェーズの起票項目)

**本節は起票時 (設計 v1.1) の内容である。実施結果は §11 と各項の状態注記に書く。**

### 10.0 本フェーズで閉じる予定の既存項目

| 台帳 | 閉止条件 | 状態 |
|---|---|---|
| **L7-2** | 実 socket・reverse proxy 込みの plug が registry に required として在り全条件が緑 | **閉止予定** (D-1 (A)、WP-3 / WP-4) |
| **L8-5 / L8-6** | 性能記録に実 socket 列が在る / concurrency が実 socket 越しに駆動された実測 | **閉止予定** (D-8 (1) / D-12、§9 の 8 (c)) |
| **L9-15** | **C-25 (3) の監査行照合が共通 suite で実際に駆動する** — 駆動条件を control 面 discovery の `audit_query` 宣言に付け替え、その下で駆動した plug が実測されること (**起票時の文言「隔離 profile のいずれかの plug が `audit_query` を宣言する」は data 面での宣言を前提にしていたが、data 面は `authority: control_or_audit` の下で `unavailable` を返す面であり、そこに宣言を足す形は採らない** — 監督裁定 2026-09-08、§5 U-3 / D-10) | **閉止予定** (D-10、§9 の 8 (b)) |
| **LQ4-11** | 宣言表の読み出しが共通 conformance で検証される (両 peer) | **閉止予定** — **C-26 が本番 composition root で検証する** (D-1 (B) / D-4) |
| **L6-5 / L6-12 / LQ4-9** | 宣言 URL の実在が実ダイヤルで検証される | **socket plug と C-26 に限って閉止予定。射程の開示 (in-process / ASGI plug は自己整合のまま) は残す** (D-4) |
| **R-17 (残)** | 0 バイトの追跡 `.md` が pre-commit と CI で赤になる | **実装済み `7d8bb0f`** (D-7。L10 登録が残る) |
| **R-18** | 適用単位が契約で定義され、それを真にする機構と共通検査が在る | **閉止予定** (D-5 + C-26、WP-5 / WP-6) |
| **R-19** | 本番 image と配備手順が exact-pin であり CI が検査する | **実装済み `c9a937a`。閉止はゲートで確認** (D-6) |
| **R-20** | 実測が済み判定規則に従って方式が決まっている | **条件付き閉止予定** (D-8、WP-7 / WP-8) |
| **R-21** | 3 文書が現行から書き起こされている | **閉止 (2026-09-08、main `bce2598`)** (D-9、WP-0) |
| **L9-10 / LQ4-24** | (どちらも閉じない) | L9-10 は記録更新 (1.8.0 の無条件義務 1 件で**1.6.0 以降の累計 5 件**、総数 15 件)。LQ4-24 は **WP-6 の runbook 項で upgrade 順序とともに参照する** (§9 の 10) |

### 10.1 計画文書への訂正註 (R-14。**2 件とも監督確定 2026-09-08**。挿入そのものは WP-9 で行う)

**本節の 2 件は文案ではなく確定文である。** WP-9 は下記を**逐語で** `docs/design/ROADMAP_POST_PHASE7_V1.md` に挿入する (原文は消さない)。

**(1) §5 フェーズ10 節の見出し「契約変更なし」の訂正註。** 下記を同節の末尾に足す。

> **【訂正註 2026-09-08 (R-14)。上の見出しと本文は起票時の原文であり、消さずに残す】** **本フェーズは契約を触る。** 見出しの「契約変更なし」は起票時の見込みであり、**§8 の R-18 の裁定 (資源制限 `enforced` の適用単位) が契約文を要すると判明したことで成立しなくなった** — **契約 1.7.0 → 1.8.0** である (フェーズ10 設計 `docs/design/PHASE10_DEPLOYMENT_EVIDENCE_V1.md` §3 D-5 (i)、§5 U-6)。**帰結として設計レビューは 2 回である** (本書 §9 の 3)。**「フェーズ9 と並行可」も現況では成立しない** — フェーズ9 は 2026-09-08 に完了したので、並行の余地そのものが無い。

**(2) §5 フェーズ10 節の L6-5a 行の訂正註。** 下記を同行の末尾に足す。

> **【訂正註 2026-09-08 (R-14)。上の文は起票時の原文であり、消さずに残す】** **`surfaces` を DB 側単一真実へ載せる機構は、Q4 フェーズで既に閉じている** (`docs/design/PHASE6_CONTRACT_160_CLIENT_DISCOVERY_V1.md:796` の【閉止 2026-09-05】、設計 `docs/design/Q4_DB_SIDE_SINGLE_TRUTH_V1.md` D-2、migration r2db `0008` / MitateDB `0007`)。**フェーズ10 の残余は「本番経路での実証」である** — Q4 設計 §12 の **LQ4-11** (r2db HTTP plug は `surfaces` を明示注入して宣言表を通らないので、本機構は共通 conformance では検証されない) を、**本番 composition root を実起動する新条件 C-26 で閉じる** (フェーズ10 設計 §1.3 (1)、§3 D-1 (B)、§3 D-4)。

### 10.2 本フェーズの起票項目 (L10-N)

- **L10-1 socket plug と C-26 は CI の所要時間を増やす。** 駆動要因は 3 つ — plug が 6 件になり各 socket plug が nginx 1 本と uvicorn thread 2 本を伴うこと、**C-26 が launcher ごとに subprocess の composition root を起動し ceiling 1 と 2 で再起動 1 回を行うこと (最も所要時間の大きい単一条件になる見込み。勘定は launcher 2 本 × 起動 2 回 = 計 4 回で、`xdist_group` を分けた上で 2 本ぶんが直列化する。分けなければ `registry-guards` の 1 worker に 4 回ぶん全部が乗る — D-1 (B) 8)**、C-09 / C-25 (3) が宣言 lag ぶん待つ (`conformance-tests/test_c09_audit_evidence.py:392`、`:473`) ため D-10 の付け替えでその待ちが増えること。**`timeout-minutes: 30` に収まるかを完了ゲートで実測し、収まらなければ本フェーズ内で並列度か plug 起動の共有を再設計する — 先送りしない。実測値を本項に記録する。開いたまま (実測待ち)。**
- **L10-2 Cloud Run 側の `--max-instances` と宣言 `process_ceilings` の一致を app は検証できない** (app が読めるのは宣言表の行だけ。**LQ4-15 と同種の限界**)。**共通 suite も同じ限界を持つ** — **C-26 (4) が観測するのは「宣言値 → `limit_enforcement` の写像が実起動で成立すること」であって実プロセス数ではない** (launcher が起動するのは 1 プロセスである)。**一致を担うのは runbook 規律と配備後チェックである。****r2db 側は systemd unit が単一 uvicorn であることを配備手順が固定するので限界はより小さいが、unit ファイルが後から書き換えられた場合は同様である。** 開示は MitateDB runbook の Invariant 1 と SI-08 行に置く。**開いたまま (記録)。**
- **L10-3 共有 limiter を入れる場合、写像は「ceiling ≥ 2 でも `enforced`」を許す形へ拡張する必要がある** — 現在は 1 入力の関数であり、**宣言表に 1 key を足して 2 入力にすれば (c) 枝を後から入れられる。この拡張点が (c) を却下しても道を閉じない根拠である** (§4 A-3)。実需は計画文書 §8 の R-13 に記録する。**開いたまま (記録)。**
- **L10-4 async psycopg への書き換えは本フェーズで採らない** (DB 層の全面改修であり範囲外)。**threadpool 委譲 (D-8 (3)) は event loop の直列化を緩和するが接続あたりのブロッキングは残るので、再評価の契機は「pool サイズを超える同時要求下の tail latency が問題になったとき」である** (計画文書 §8 の R-13)。**開いたまま (記録)。**
- **L10-5 TLS 終端の証拠は配備 smoke (`tools/deploy_smoke.py`) の領分のままである** — socket plug と C-26 は loopback の平文 HTTP であり TLS 終端・証明書・ALPN を見ない (D-3、§4 A-8)。**統合しない判断は、conformance が実証明書を必要としない (公開リポジトリ規律) ことに立つ。開いたまま (記録)。**
- **L10-6 docker 不在の開発機では `image-pins` の証拠は CI にしか無い。** **nginx を「必須依存・skip 禁止」とした D-3 との非対称である** — nginx は prefix 配下に自前の instance を起動するだけで済むが、image ビルドは daemon を要求する。**開発機では skip でも fail でもなく「検査の場が CI だけである」ことを開示する形を採る** (D-6 の 5)。**開いたまま (記録)。**
- **L10-7 5・6 番目の plug は「本番 composition root」を起動しない** — socket adapter が起動するのは既存 HTTP adapter と同一の composition であり、実 socket・実 proxy・実 connection 並行性は本物だが**組み立て方そのものは conformance adapter のものである** (本番 composition root の証拠は C-26 が持つ)。**この分割を採った理由は §4 A-9 に file:line 付きで記録した。統合の再評価の契機は「port から in-process の手が無くなったとき」である。開いたまま (記録)。**

---

## 11. 実施記録

### 11.0 WP-0 (D-9、R-21) — 完了 (2026-09-08)

- **コミット**: 実装 `c3d9fc9`、main へのマージ `bce2598` (別 worktree で実施し設計起草と並行した)。
- **照合 (2026-09-08)**: `security/CONTROL_MAPPING.md` に旧文「remain unimplemented on this peer」は **0 件** (`grep -c` の実測)。SI-08 行の MitateDB 記述は現行の宣言 (`concurrency` / `requests_per_minute` = `enforced`、`execution_ms` = `reference_wall_clock`) と一致する。**旧文は `CONTROL_MAPPING_HISTORY.md` の `## SI-08` に逐語で在る。**

### 11.1 WP-1 / WP-2 — 2026-09-08 にマージ済み

- **WP-1** (D-7): 空 `.md` 検査が main `7d8bb0f` (実装 `f38716b`)。**L10 登録は未了** (`L_REF_RE` は現行のまま)。
- **WP-2** (D-6): main `c9a937a` (実装 `79958a7`)。

### 11.2 WP-3 / WP-5a — 2026-09-08 にマージ済み (**v1.3 追記**)

- **WP-3** (D-1 (A) / D-2 / D-3 / D-11 / D-12): **main `6055c69`** (branch の実装コミット `8d39260`)。**adapter port は `docs/design/CONFORMANCE_ADAPTER_V1.md` v1.14**、**`.github/workflows/ci.yml` に nginx の導入と socket 残骸検査が入った。**
- **WP-5a** (D-5 (i)(v) / D-4 / D-3 / D-10 のうち契約公開部分): **main `3d7f823`**。**マージされたのは branch `phase10-wp5` の `654e23e` の時点であり、U-9 の追補 `73adbda` は含まれない。**
- **次のゲート束でマージする 3 件 (2026-09-08 時点で main 未マージ)**: **`73adbda`** (WP-5a 追補、U-9)、**`ea237e5`** (WP-3 follow-up、U-12。branch `phase10-wp3f`)、**WP-1c の確定コミット `2431e93`** (branch `phase10-wp1c`。実装は `5944013`)。

### 11.3 以降

**未着手** (設計 v1.1 時点。完了ゲートの実測値・WP ごとの記録・性能差分は WP-9 で記入する)。
