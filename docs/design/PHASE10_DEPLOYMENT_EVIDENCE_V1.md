# フェーズ10 実施設計: 配備面の証拠 (契約 1.8.0「資源制限の適用単位」)

## 0. 版数・位置づけ

- **現行版: v1.11 (2026-09-14)。** 直後の v1.10 行およびそれ以下は当時の改版履歴として保存する。v1.11 は、計画文書 §8 の R-37 (巨大モジュールの段階的リファクタリング) の追跡 ID として L10-20 を §10.7 に追記した記録である。**L10-20 が何を義務付けるかは本書では定めず、設計 `docs/design/MODULE_REFACT_ARCHITECTURE_V1.md` (v1.1) §5 / §6 を正本とする。** 既存の行は書き換えていない。
- **現行版: v1.10 (2026-09-13)。** 直後の v1.9 行およびそれ以下は当時の改版履歴として保存する。v1.10 は、L10-9 の起票、WP-7 の性能記録、WP-8b の安全性裁定、および R-31 の現在の行き先を照合し、追記だけで L10-9 を閉止した記録である。正本は §10.6。
- **現行版: v1.9 (2026-09-13)。** 直後の v1.8 行およびそれ以下は当時の改版履歴として保存する。v1.9 は、L10-17〜L10-19 を現行実装・直近コミット・既存設計記録と照合し、追記だけで処置を確定した記録である。正本は §10.5。
- **現行版: v1.8 (2026-09-13)。** 直後の v1.7 行は当時の改版履歴として保存する。v1.8 の内容は、その後の L10-16 閉止追記が正本である。
- 版数: **v1.7 (2026-09-10)**。**改版履歴**: **v1.0 (2026-09-08)** 起草初稿 (設計レビュー 1 / 2 の対象)。**v1.1 (2026-09-08)** — **設計レビュー 1 / 2 (2026-09-08) の反映。D-1 を再定義し (A-1 socket adapter は既存 HTTP adapter の composition を継承する / A-2 本番 composition root の証拠は新条件 C-26 が担う)、C-26 を新設した。** **v1.2 (2026-09-08)** — **差分レビュー (2026-09-08) の反映: D-10 の付け替え (L9-15 の閉止は control 面 discovery を駆動条件にする形へ)、基底 http adapter の hook 抽出、C-26 の xdist group と (4) の主張の縮小、harness 全体の起動予算。** **v1.3 (2026-09-08)** — **依頼者が提示した 2 本目の外部レビュー (基準 main `b16afdd`) の監督検証の反映** (依頼者裁定 2026-09-08、逐語:「フェーズ 10 に組み込めるのであれば組み込んでください。」)。**足したのは §5 の U-7〜U-13、§3 D-13 (同一 idempotency key の同時送信の直列化 = WP-6d と新条件 C-27)、§3 D-14 (小修正の束 = WP-1c)、D-5 (ii) の区分 (iii) への追補、D-2 への WP-3 追跡是正 (follow-up) 項目、D-8 (3) への WP-8 前提条件、§6.2 の C-27 行、§8 / §8.1 の WP-1c / WP-6d-i / WP-6d-ii、§9 の完了ゲート 14〜17 である。** **既存の決定・裁定・却下は 1 つも撤回していない。** 計画文書側の起票は `docs/design/ROADMAP_POST_PHASE7_V1.md` (v1.8) §1.0d と §8 の **R-24〜R-33** である。 レビュー指摘そのものは**監督保管**である。 **v1.4 (2026-09-08)** — **実施の反映である。足したのは §3 D-13 の実施註 (WP-6d-i の peer ごとの実現の形と、両者が違う理由)、D-13 の項 3 の追記への訂正註 (WP-8b の実際の裁定)、§3 D-15 (フェーズ9 R-2 の走査 lock mode の是正 = WP-R35)、§5 U-7 の実施註、§8 / §8.1 の WP-R35 行、§11.4 (WP-6d-i)・§11.5 (R-34 の実施と監督の過程誤り)・§11.6 (WP-R35) である。** **既存の決定・裁定・却下は 1 つも撤回していない。** 計画文書側の起票は同文書 (v1.9) §1.0d と §8 の **R-34** / **R-35** である。 **v1.5 (2026-09-09)** — **WP-6d-ii (新条件 C-27 と adapter hook) の実装の形の確定である。足したのは §3 D-13 の「実装の形 (6d-ii) の確定」節 (hook `hold_after_idempotency_lookup` の契約文・plug ごとの実現点・観測 4 件・版 gate・plug ごとの変異表と開示・xdist group・取り込み順)、D-13 の訂正註 2 への追記 (`_idempotency_lock_scope` を WP-8b の外側 cell lock へ一本化する監督提案。ペアセッションと調整中)、§6.2 の C-27 行への追記、§8.1 の WP-6d-ii × WP-4 の追補行である。** **既存の決定・裁定・却下は 1 つも撤回していない** — **U-8 の確定 (α)、D-13 の hook の形の指針 (`hold_in_flight` に倣う)、観測 (i)〜(iii) はいずれもそのままであり、本版が足したのは「保持点を受理区間の末尾に置く」という精密化と、観測 (iv)、および peer ごとに違う変異の実測可能性の開示である。** **v1.6 (2026-09-10)** — **WP-9 の記録である。足したのは §5 の U-14〜U-22 (WP-4〜WP-8 の実施中の監督裁定)、§9.1 (完了ゲートの実測)、§10.3 (L10-1〜L10-7 の状態注記と §10.0 の実測結果)、§10.4 (L10-8〜L10-19 の起票)、§11.7〜§11.9 (WP ごとのコミット・集計行・レビュー巡数・変異、およびレビューが見つけた実欠陥 6 件) である。** **既存の決定・裁定・却下は 1 つも撤回していない。** **未達 2 種 — CI 集計行の未取得 (課金上限) と C-27 (WP-6d-ii) の未実施 — は §9.1 に開示として残した。** 計画文書側の起票は `docs/design/ROADMAP_POST_PHASE7_V1.md` (v1.10) §1.0e と §5 / §8 である。 **v1.7 (2026-09-10)** — **WP-6d-ii の実施の記録である。足したのは §3 D-13 の「実施註 (6d-ii)」、§5 **U-8** の実施註、§6.2 の C-27 行の実施追記、§9.1 の項目 **1** / **5** / **8 (f) / 14** への追記と「未達の扱い」への追記、§11.7 の束 **15** 行、§11.11 (WP-6d-ii の実施記録) である。** **既存の決定・裁定・却下は 1 つも撤回していない。既存の行・表・実測値は 1 文字も書き換えていない** (追記だけである)。 **v1.6 が §9.1 に開示として残した未達 2 種のうち、C-27 (WP-6d-ii) は本版で解消した** — **C-27 は `CONDITIONS.md` で `executable` になり、6 plug すべてで駆動する。** **CI 集計行の未取得 (課金上限、L10-15) は未達のまま残る。** 計画文書側の起票は `docs/design/ROADMAP_POST_PHASE7_V1.md` (v1.11) §1.0e / §5 / §8 の **R-24** である。
- **【追記 2026-09-13 (v1.8)】** **L10-16 の閉止記録である。** pair-closing `2152c94`（実装 `fe2b105`）が `_ISOMORPHIC_TARGETS` を 105 → 137 行へ拡張し、C-26 launcher、F-16 の同型な純粋 Python 部分、WP-8c の AST helper を登録したこと、登録しない候補には実在する peer 差を記録したこと、行削除・片側1文字差分の変異が赤になったことを §10.4 の L10-16 に追記した。**既存の決定・裁定・記録は書き換えていない。**
- 位置づけ: **監督が確定した枠 (2026-09-08) の実施設計**である。計画文書 `docs/design/ROADMAP_POST_PHASE7_V1.md` (v1.6) の **§5 フェーズ10 節**・**§4**・**§8**・**§9** が**正本**であり、本書 §1.1 / §2.1 はそれを**逐語で転記する** (計画文書 §9 の 1、`docs/work-orders/OPERATING_CONDITIONS.md` §1.8 の 53)。**§1.2 は逐語転記ではなく要約である。** §3 の D-1〜D-15 と §4 の A-1〜A-9 は**監督確定**、**§5 の U-1〜U-13 は依頼者委任 (2026-09-07 / 2026-09-08) に基づく監督確定**である (**D-13 / D-14 と U-7〜U-13 は v1.3、D-15 は v1.4 の新設である**)。
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

## 3. 決定 (D-1〜D-15。**D-13 / D-14 は v1.3、D-15 は v1.4 の新設である**)

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
3. **MitateDB の PostgreSQL backend**: **照会を自己 commit の別トランザクションから、書く側の接続** (`transact` は `_runtime`、DDL は `_developer`) **の同一トランザクション内へ移し、その前に lock を取る。** **接続が 2 本ある構造そのものは変えない** — 書く接続で lock と照会を行えばよい。 **【追記 2026-09-08。WP-8b との両立】** **フェーズ10 主セッションの裁定 (2026-09-08) で WP-8b は MitateDB の cell が要求ごとに `BoundedConnectionPool` から接続を借りて要求終了で返す形 (role ごとの共有接続 `_runtime` / `_developer` の廃止) を含む。本項の「書く側の接続」はその形では「その要求が借りた 1 本の接続」になり、lock → 照会 → 実行 → 記録が 1 要求 1 接続 1 トランザクションで閉じるという本項の不変条件はそのまま成り立つ。WP-6d-i と WP-8b のどちらが先に main へ入っても、後から入る側が接続の取得点を合わせる (`cell.py` / `backend_postgres.py` の同一ファイル別領域)。** **【訂正註 2026-09-08 (v1.4)。上の追記は 2026-09-08 時点の見込みであり、消さずに残す (`OPERATING_CONDITIONS.md` §1.8 の 56)】** **WP-8b の実際の裁定 (フェーズ10 主セッション、2026-09-08) は「要求ごとに pool から接続を借りる形を WP-8b には含めない」である** — **同セッションの監査が `_LimitStateHolder` / `BoundedConnectionPool` / control 面の窓は既に lock 済みであり、pass 2 は `ApplicationCell._lock` が直列化していることを実測したためである。** **要求スコープの接続 (U-10 の同時性の側面) は、同セッションが L10 族の新しい台帳項目 (9 番目。本書 §10.2 への挿入は当該 WP の記録時に行われる) で「WP-7 の計測に依存する後続 WP」として記録している。** **同セッションの Opus レビューは、threadpool の下で pass 1 の catalog 読みが `_lock` の外で `_developer` を使うことが共有接続の危険になるかを検査中である。** **本項の不変条件 — 「lock → 照会 → 実行 → 記録が 1 要求 1 接続 1 トランザクションで閉じる」— の記述はそのまま有効であり、WP-6d-i はその形で実装した (下記の実施註)。** **【訂正註 2 (2026-09-08、同日後刻)。WP-8b のレビュー結果と裁定 (フェーズ10 主セッション)】** **レビューは pass-1 (`_plan_operation` / `_select_fields` / `_bind_*` / `_idempotency_check`、catalog 読み 8 メソッド) が `_lock` の外で共有 `_developer` 接続を使い、threadpool 化で回帰することを実証した (A = schema 操作が lock 保持中に CREATE TABLE を開いたまま停止、B = 同一 app の query が lock 外で `commit()` → A の commit 前に A の DDL が別接続から見えた)。裁定 = 案 A: 全公開メソッドで `with self._lock:` を slot (`_limit_gate`) と hold_in_flight hook の内側、lookup → pass-1 → pass-2 全体を覆う位置に置く (同一 Application は完全直列化、Application 間は並行)。要求スコープ接続は WP-7 計測後の後続 WP。** **本項 (WP-6d-i) との関係: `_idempotency_lock_scope` (keyed 非 dry-run のみ `self._lock`) は案 A の外側 `with self._lock:` の中では RLock の再入で無害な冗長になる。WP-8b の rebase で残すか一本化するかは WP-8b 側の判断とし、`_idempotency_pg_scope` (session advisory lock と接続束縛) は残す。merge 順は WP-6d-i → WP-8b。** **【追記 2026-09-09 (v1.5)。監督の提案。裁定はペアセッション側で保留中】** **監督は「一本化する」側を提案する** — **案 A の外側 `with self._lock:` は全公開メソッドを覆うので、`_idempotency_lock_scope` が返す `self._lock` は keyed 非 dry-run のときだけ RLock を再入する冗長になり、「どちらの lock がこの直列化を担っているのか」が現物から 1 つに読めなくなる。** **一本化する場合の条件は 2 つである**: **(a) 外側 `with self._lock:` が `_idempotency_pg_scope` の外側 (= advisory lock の取得より先) に来ること** — 順序が逆になると、cell lock を待つスレッドが advisory lock を保持したまま待つ形が生じ得る。**(b) `_idempotency_lock_scope` を消すなら、それが担っていた「keyed 非 dry-run 以外は lock しない」性質が案 A の下で失われることを、WP-8b 自身の完了条件として明示的に受理すること** (F5 の是正が守った性質である。案 A は「同一 Application は完全直列化」を選んだので失われること自体は裁定済みだが、記録は要る)。 **本提案は WP-6d-ii には影響しない** — **C-27 の変異表 ((7)) は MitateDB について「cell lock を外す」と書いており、一本化後もその 1 つが対象のままである。** **裁定はペアセッションが行う。** **【訂正註 3 (2026-09-09)。一本化の決定】** **フェーズ10 主セッションは監督の代案を採用した: WP-8b で `_idempotency_lock_scope` と 4 入口の `with self._idempotency_lock_scope(...)` を削除し、案 A の外側 `with self._lock:` に一本化する (`_idempotency_pg_scope` は残す)。本項の MitateDB `tests/test_idempotency_concurrency.py` は変更せず、外側 lock の pin として使う。WP-8b の完了条件に変異検査「4 入口の外側 `with self._lock:` を外すと in-memory の同一キーテスト 3 本が赤」を入れ、AST 行数 pin は WP-8b 側で更新する。上の「冗長として残す」「決定は保留」の記述は当時の記録として残す。**
4. **in-memory cell** (r2db の `InMemoryCell`、MitateDB の `ApplicationCell` の dict): 単一プロセスでも uvicorn と将来の threadpool ではスレッドが並ぶので、**key 単位または cell 単位の `threading.Lock` で「照会 → 実行 → 記録」を囲む。**
5. **異キー競合 (`idempotency_entries` の件数、D-5 (ii) の区分 (iii))** は key lock では直列化されない — **表単位の定数 key の `pg_advisory_xact_lock` を件数検査の前に取る** (D-5 (ii) の追記 (2)。`LOCK TABLE ... IN SHARE MODE` は使わない)。
6. **性能**: **Application ごとの keyed write が表 lock で直列化される。** **完了ゲートの性能差分 (`OPERATING_CONDITIONS.md` §1.3 の 27) で計測して記録する。回避しない。**

**実装の形 (6d-ii) — 新条件 C-27「同一キー同時送信」**: **adapter hook で先着を照会の直後 (実行の前) に保持し、後着を送り、先着を解放する決定的な検査**である。**hook の名と形は `hold_in_flight` (C-05、port v1.12) に倣う。** 観測項目は **(i)** 同一 digest — **実行 1 回** (効果行 1、実行の監査 event 1)、後着は先着と同じ `request_id` の replay、**(ii)** 異 digest — 実行 1 回、後着は `CONFLICT` + `violated_declaration: idempotency_key`、**(iii)** **異キー 2 件を `idempotency_entries` 上限 −1 の状態で同時送信** — 1 件が `LIMIT_EXCEEDED` である。**4 plug すべてで駆動する** (http adapter は in-process の uvicorn なので monkeypatch が届く。C-05 の実例)。**socket adapter (WP-4) は継承する。** **変異注入は「lock を外すと (i) (ii) が赤になる」である。** **`CONDITIONS.md` の C-27 行は C-26 と同じ方式で先に置く** (宣言だけを置き、実行可能になるのは WP-6d-ii。§6.2)。

**契約 (U-9)**: **契約 1.8.0 の `idempotency.record` に「同時に到着した同一キーの要求も直列化され、高々 1 件が実行される。他方は先着の commit の後に再送として答えられる (replay または `CONFLICT`)。先着が失敗したなら新規要求として扱われる」の趣旨の 1 文を足す。** **1.8.0 は未公開 (branch `phase10-wp5` のみ) なので版は動かさない。** **packaged 複製 3 つを同一バイトに保つ。** **WP-5a の branch に足す追補コミットとして監督が実施する。** **【実施済み 2026-09-08。branch `phase10-wp5` の `73adbda`。WP-5a 本体は `654e23e` の時点で main `3d7f823` にマージ済みであり、追補 `73adbda` はそれに含まれないので、次のゲート束で監督がマージする】** **義務の id は `idempotency_concurrent_same_key_sends_serialized` (capability `idempotency`) であり、1.8.0 の `conditional` の 1 件目 (1) である。** 詳細は §5 U-9 の実施註である。

**C-27 とこの義務の関係**: **C-27 は、この条件付き義務 (1.8.0 の `conditional` (1)) の実行可能な条件である。** **したがって C-27 が拘束するのは「`contract_version` が 1.8.0 以上であり、かつその実装自身の `idempotency` が `unavailable` 以外である」plug に限られる** — **C-25 が 1.7.0 の宣言に結び付いているのと同じ形である** (§6.2 の C-25 行、`conformance-tests/CONDITIONS.md` の C-25 行の版 gate)。**両 peer は WP-6a / 6b の版フリップで 1.8.0 を宣言し、`idempotency` は両 peer とも `unavailable` 以外なので、フリップ後は 4 plug すべてで駆動する。** **版 gate の xfail は採らない (監督裁定 2026-09-08、U-8 追補): WP-1c 以後は CI が `xfailed == 0` を強制するので、フリップ前に C-27 を `xfail(strict=True)` で置く中間状態は CI を赤にする。したがって WP-6d-ii は WP-6a / 6b の版フリップの後に着手し、C-27 は最初から 4 plug で駆動する形で入る。順序は §8.1 の「WP-6a / 6b → WP-6d-ii」行が正本である。**

**壊すとどう見えるか**: **key lock を外すと C-27 の (i) (ii) と両 peer の peer-local 同時テストが赤になる。** **MitateDB で照会を書く側の接続の外 (自己 commit の別トランザクション) に戻すと、後着が先着の commit を待たずに読むので同じものが赤になる。** **表単位 lock を外すと C-27 の (iii) が赤になる。**

**【実施 2026-09-08 (v1.4)。WP-6d-i。6d-ii は未着手である】** **branch `phase10-wp6d`。実装コミット `21cc8fb`、Opus のコードレビュー 1 巡目の判定は「accept with fixes」であり是正コミットは `6a3453d`、R-34 の branch `phase10-r34` との統合が `685ebfa` である (**再レビュー accept**)。** **main へのマージは `4e1020a` (WP-6d-i + R-34 + R-35 の束) + 直後の pin 修正 `ee80c97` (`test_limit_class_vocabulary.py` の `ResourceLimitError` 呼び出し数 33 → 35。F2 の 2 箇所分。ゲート 3 が検出し、ゲート 4 で再確認) である。** **実現の形は peer ごとに違う。同じ安全結果 (lock → 照会 → 実行 → 記録 → commit) を、それぞれの現物の構造の下で成り立たせるための違いであり、`CLAUDE.md` の「Platform-specific controls may differ between `r2db-api` and `MitateDB-api` when they provide the same required safety outcome」に当たる。**

1. **r2db (`r2db-api/src/r2db_api/postgres.py`)**: **本項 2 のとおりの形である** — **効果の外側トランザクション内で `pg_advisory_xact_lock(20261007, hashtext(<key>))` を `_idempotency_lookup` の直前に取る** (`transact` と `apply_schema` の両方)。**件数検査は `pg_advisory_xact_lock(1414142)` を `_idempotency_reserve` の COUNT の前に取る。** **どちらも入れ子の savepoint block の外である** (savepoint の解放で lock が落ちないため)。**`ON CONFLICT DO UPDATE` は期限切れの未回収行のためだけに残した** (本項 1)。**in-memory の `structured.ApplicationCell` は `transact` / `apply_schema` を per-cell の `threading.Lock` で囲む** (`_transact_locked` / `_apply_schema_locked`)。
2. **MitateDB (`MitateDB-api/src/mitatedb_api/backend_postgres.py` / `cell.py`)**: **transaction-scoped lock は使えない** — **catalog 読みが同じ接続の途中で自己 commit するので、xact lock はそこで解放されてしまう。** **したがって SESSION advisory lock を書く側の接続で取る** — **`pg_advisory_lock(76176100, hashtext(<key>))` と `pg_advisory_lock(761761762)`** を新設の backend method **`idempotency_begin`** (lock → 回収 → 照会 → commit) と **`idempotency_reserve`** (lock → 件数 → commit) が取り、**`idempotency_unlock`** (rollback → unlock) が `ApplicationCell._idempotency_pg_scope` の **`finally`** で解放する。**lock を取った接続を scope に束ねる** (解放時に接続を取り直さない)。**`lock_timeout` / `statement_timeout` は要求 deadline から lock の前に設定し、lock 待ちのタイムアウトは `LIMIT_EXCEEDED` (`execution_ms`) に写す。** **cell 全体の `self._lock` (`_idempotency_lock_scope`) が照会→pass 1→pass 2 を覆うのは keyed かつ非 dry-run の要求だけであり、pass 2 の既存 lock は変えていない。** **`backend.py` / `backend_sqlite.py` は同じ interface を no-op lock で持つ。**
3. **テスト** (両 peer `tests/test_idempotency_concurrency.py`。**実 PG と in-memory の双方**): **同一 digest → 実行 1 回 + 元の `request_id` での replay**、**異 digest → 実行 1 回 + `CONFLICT`**、**上限直下の異キー 2 件 → 1 件が `LIMIT_EXCEEDED`**、**先着が失敗 → 後着は新規要求として実行**。**MitateDB は加えて回収の永続化・lock 待ちタイムアウト・pass 1 失敗時の unlock を持つ。**
4. **変異の実測**: **key lock を外す → 両 peer 赤 (`2 failed`)**、**件数 lock を外す → 両 peer 赤 (`1 failed`)**、**in-memory lock を外す → 両 peer 赤 (`3 failed`)**、**unlock を `finally` の外へ出す → 赤 (`still holds 2 advisory lock(s)`)**、**MitateDB の 2 つの commit を両方外す → 回収の回帰が赤**。**監督の raw-SQL 競合スクリプトを新しい SQL で再実行し、25 反復で二重実行は 0 件である。** **是正前の peer suite は r2db `1175 passed`、MitateDB `998 passed` である。**
5. **レビュー指摘 (1 巡目、F1〜F8。いずれも是正済み)**: **F1 (blocker)** 回収の DELETE が `begin()` の rollback で捨てられていた。**F2** session lock の前に `lock_timeout` を置いていなかった。**F3** `finally` での unlock が未検証だった (テストを追加)。**F4** 「先着が失敗 → 後着が新規要求として実行」が未検証だった (テストを追加)。**F5** cell lock を無条件に広げていた (keyed かつ非 dry-run に限定した)。**F6** unlock が接続を取り直していた (scope に束ねた)。**F7 / F8** advisory 名前空間のコメント根拠と陳腐化したコメントの是正。

**本実施が見つけた既存の欠陥は D-15 (WP-R35) である** — **本項 5 と §5 U-7 が実装担当に課したフェーズ9 R-2 の前例確認が、両 peer の走査 lock mode の欠陥を露出させた。**

#### 実装の形 (6d-ii) の確定 (**監督確定 2026-09-09 (v1.5)**)

**位置づけ**: **§5 U-8 の確定 (α) と、上の「実装の形 (6d-ii)」が定めた形は 1 つも撤回しない。** **本節が足すのは、実装担当が再導出せずに着手できる水準の確定である** — **hook の署名と契約文、plug ごとの実現点、観測 4 件、版 gate、plug ごとに実測できる変異、xdist group、取り込み順。** **上の指針が「`hold_in_flight` に倣う」とだけ述べていた点を、現物 (`conformance-tests/adapter.py:1713` の `hold_in_flight` と 4 adapter の実現、両 peer の `tests/test_idempotency_concurrency.py`) に照らして確定する。**

**(1) hook の名と署名**

```python
def hold_after_idempotency_lookup(self, session, idempotency_key: str) -> AbstractContextManager["IdempotencyHold"]
```

**契約文 (逐語。常設規律 4 に従い、port docstring へ言い換えずに複製する)**:

> `session` 上で次に到着する、`idempotency_key` に一致する key を持つ要求を 1 件だけ、その要求自身の **idempotency 受理区間の末尾**で停止させたまま保持する。受理区間の末尾とは、照会が「記録なし」を返し、`idempotency_entries` の予約を取り終え、その区間が取った lock をすべて保持したまま、効果をまだ 1 件も実行していない地点である。保持中に同じ key を持つ 2 件目の要求を出すと、2 件目はその同じ lock の上で実際に待ち、先着が解放されて commit した後にはじめて答えを返す。`with` を抜けると先着は解放され、実行・記録・commit まで進む。保持するのは 1 件だけであり、`idempotency_key` に一致しない要求は素通しする。

**【追記 2026-10-03 (port v1.22、設計 `docs/design/EXPIRED_REQUEST_SEMANTICS_V0_1.md` §6.4)】** 上の契約文のうち「保持中に同じ key を持つ 2 件目の要求を出すと、2 件目はその同じ lock の上で実際に待ち、先着が解放されて commit した後にはじめて答えを返す。`with` を抜けると先着は解放され、実行・記録・commit まで進む。」の 2 文は、port v1.22 で次の 3 文に改められた (`conformance-tests/adapter.py` の docstring が同じ文を持つ)。他の文は変わらない。また、下の (2) の「メソッドは 1 つだけである」は、port v1.22 で `statements_after_release()` (放した後に発行された文の数。in-process の 2 plug は `None`) が加わり 2 つになった。

> 保持中に同じ key を持つ 2 件目の要求を出すと、2 件目はその同じ lock の上で実際に待ち、先着が解放されて commit した後、または先着が `execution_ms` の予算切れで拒否されて何も残さなかった後にはじめて答えを返す。`with` を抜けると先着は解放され、その時点で先着の `execution_ms` の予算が残っていれば、実行・記録・commit まで進む。使い切っていれば、解放の後の最初の検査で `LIMIT_EXCEEDED` (`limit_class: execution_ms`) により次の文を発行せずに終わり、効果も idempotency の記録も残さない。

**(2) yield する handle** — **`IdempotencyHold`** (**非 normative**。`adapter.py` に置く。`IsolatedControlHandle` (port §21.4) と同じ「非 normative な handle を yield する」先例)。**メソッドは 1 つだけである**:

- `wait_until_held(self, timeout_s: float = 30.0) -> int` — **保持点へ実際に到達するまで blocking し、実測した保持件数を返す** (正しい実現では常に 1)。**到達しないまま `timeout_s` を過ぎたら `AssertionError` を上げる — skip も xfail もしない** (`OPERATING_CONDITIONS.md` §1.3 の 26)。**既定値 30.0 は 4 adapter が既に持つ `_HOLD_IN_FLIGHT_ENTRY_TIMEOUT_S` と同値である。** **戻り値は引数の折り返しではなく実測値である** — `hold_in_flight` が `entered_count` を yield する理由と同じである (port v1.12、裁定 5)。

**呼び出し側の形**: **保持される先着 (A) も、待たされる後着 (B) も、テスト自身が別々の OS スレッドから出す** — hook は要求を出さない (**`hold_in_flight` との唯一の構造上の違いである**。あちらは自分で `n` 件を出す)。**保持中に B が完了していないことを、有限の待ち窓で実測する** (両 peer の peer-local テストの `_assert_second_call_is_blocked` と同じ形)。**この「B はまだ完了していない」の assert が、変異を入れたときに最初に赤くなる観測である。**

**(3) 保持点を「照会が absent を返した直後」ではなく「受理区間の末尾」に置く理由**

**監督の枠の文言 (「照会の直後・実行の前」) はそのまま満たす** — 受理区間の末尾は照会の後であり、効果の実行の前である。**精密化が要るのは観測 (iii) のためである**: **照会の戻り際で止めると、その時点では `idempotency_entries` の件数 lock をまだ取っていない** (r2db は `_idempotency_reserve_lock` が照会の後に来る。`postgres.py:1594`)。**その状態で異キーの B を出すと B は何にも待たずに走り切るので、2 件の予約はテスト自身の停止によって逐次化されてしまい、件数 lock を外しても (iii) は緑のままになる** — **既存の逐次経路の bound 検査 (C-23) と同じものを二度書くだけの、変異で赤くならない観測になる。** **受理区間の末尾で止めれば、B は実際に件数 lock (または cell lock) の上で待ち、その lock を外すと (iii) が赤くなる。** **(i) (ii) はどちらの保持点でも成立するので、末尾に置くことによる損失は無い。**

**(4) plug ごとの実現点** (**monkeypatch。`hold_in_flight` と同じく product code に test 専用 hook を足さない**。**両 peer の `tests/test_idempotency_concurrency.py` が既に同じ地点を同じ方法で止めており、本 hook はその形を port へ持ち上げるだけである**)

| plug | 包む対象 | 保持点が受理区間の末尾になる理由 | 後着が実際に待つ先 |
|---|---|---|---|
| **`r2db-api`** (in-process、`structured.ApplicationCell`) | 同一 cell の **`_idempotency_lookup`** (key 一致かつ戻り値が `None` のとき当該スレッドを arm する) と **`_idempotency_reserve`** (arm 済みスレッドなら戻り際に保持する) の 2 つの bound method | `transact` / `apply_schema` が cell 全体の `self._idempotency_lock` を取ってから `_transact_locked` / `_apply_schema_locked` に入り、その中で `_idempotency_lookup` (`r2db-api/src/r2db_api/structured.py:2269`) → `_idempotency_reserve` (`:2294`) → 実行 の順に進む。**`_idempotency_reserve` は照会が absent だった経路でしか走らない**ので、その戻り際が受理区間の末尾である | cell の `threading.Lock` (`transact` / `apply_schema` の入口) |
| **`r2db-api-http`** (`PostgresCell`、実 PG) | 同名の 2 つ (`r2db-api/src/r2db_api/postgres.py:1283` / `:1296`) | 効果の外側トランザクション内で `_idempotency_key_lock` (`:1566`) → `_idempotency_lookup` (`:1567`) → `_idempotency_reserve_lock` (`:1594`) → `_idempotency_reserve` (`:1595`) → 実行 の順である。**`_idempotency_reserve` の戻り際では key lock と件数 lock の両方を保持している** | key: `pg_advisory_xact_lock(20261007, hashtext(<key>))` / 異キー: `pg_advisory_xact_lock(1414142)`。**`PostgresCell` はプロセス内の cell lock を持たない** (`postgres.py` の `threading.Lock` は `_RolePool` / `SharedPoolManager` のもので、要求経路を直列化しない) |
| **`MitateDB-api`** (in-process、`SQLiteBackend`) | **`ApplicationCell._idempotency_check`** (`MitateDB-api/src/mitatedb_api/cell.py:1074`) の **1 つだけ** | **この 1 メソッドが照会 (`idempotency_begin`) と予約 (`idempotency_reserve`) の両方を行い、`(None, digest, now_ms)` を返した時点が受理である** (`cell.py:1163` / `:1187`)。呼び出し側は `with self._idempotency_lock_scope(...), self._idempotency_pg_scope(...)` の内側でこれを呼ぶので、**戻り際は cell lock を (PG では加えて session advisory lock を) 保持したままである**。**key 一致と「戻り値の 1 要素目が `None`」の両方で判定する** — CONFLICT / LIMIT_EXCEEDED で抜けた敗者を保持しない | cell の `RLock` (`_idempotency_lock_scope`。keyed かつ非 dry-run のときだけ効く。**C-27 の要求は 2 件ともこれに当たる**) |
| **`MitateDB-api-http`** (`PostgresBackend`、実 PG) | 同上 1 つ | 同上 | **同一プロセス・同一 cell なので cell の `RLock` が先に効く。** `pg_advisory_lock(76176100, hashtext(<key>))` / `pg_advisory_lock(761761762)` が待ち先になるのは **cell を跨ぐ場合**であり、共通 suite の 1 plug = 1 cell の構成では現れない (下の (7) の開示) |

**socket plug (WP-4) は 2 本とも http adapter の subclass なので、この 2 つ (r2db) / 1 つ (MitateDB) の実現をそのまま継承する** — **socket 固有のコードは書かない** (D-1 (A) 6 の composition、port §24.3)。**http plug の uvicorn は同一プロセスなので monkeypatch が届く** (C-05 の先例)。

**(5) C-27 の観測 (実行可能な 4 件)**

**すべて `isolated_application_surface()` の新しい instance に対して駆動する** (C-05 の V2 driver と同じ規約)。**証拠は adapter が既に持つ読みだけで取る — 新しい port 読み出しを足さない。**

| 観測 | 出す要求 | assert する証拠 |
|---|---|---|
| **(i) 同一 digest** | A と B が同一 key・同一要求 (`attempt_mutation_with_result(..., idempotency_key=K)`) | **効果行はちょうど 1 件** (`select_eq`)、**B の `request_id` が A のそれと一致する** (replay)、**保持中に B が完了していない**。`audit_query` を `enabled` / `partial` と宣言する plug では**実行の監査 event が 1 件**であることも見る (**宣言を読んで分岐する。宣言しない plug でこの枝を要求しない**) |
| **(ii) 異 digest** | 同一 key・異なる `operations` | **効果行 1 件**、**B は `ConformanceDenial(CONFLICT)` かつ `details.violated_declaration == "idempotency_key"`**、**保持中に B が完了していない** |
| **(iii) 異キー・上限直下** | 隔離面が宣言する `idempotency_entries` = **E** を capability document から読み (**定数を書かない**)、**E−1 件を逐次で埋めてから**、A (key `K1`、保持) と B (key `K2`) を同時に出す | **ちょうど 1 件が `LIMIT_EXCEEDED` かつ `details.limit_class == "idempotency_entries"`**、もう 1 件は成功、**効果行の数がその内訳と一致する**、**保持中に B が完了していない**。**E の読み方は `test_c23_idempotency_semantics.py:382` の既存の形に倣う** |
| **(iv) 先着が失敗** (**v1.5 で足した**) | A は**受理の後に必ず失敗する要求** (宣言済みの制約に違反する行の挿入。**plug 固有の失敗注入を使わない — 契約が定める拒否である**)、B は同一 key の正当な要求 | **A は失敗し記録を残さない** → **B は replay でも CONFLICT でもなく新規要求として実行される** (**独自の `request_id`**、効果行 1 件)。**D-13 の項 1 の「先着が失敗 (rollback) したなら新規要求として実行する」と、契約 1.8.0 の条件付き義務の最終文に 1 対 1 で対応する観測である** (§5 U-9) |

**(6) 版 gate**

**C-27 が拘束するのは「`contract_version` が 1.8.0 以上であり、かつその plug 自身の `idempotency` が `unavailable` 以外である」plug だけである** (上の「C-27 とこの義務の関係」)。**判定は 2 つとも現物の宣言から読む** — 版は `adapter.contract_version_at_least(<plug の宣言する contract_version>, "1.8.0")` (`conformance-tests/adapter.py:563`)、capability は capability document の `idempotency` である。**plug 名で分岐しない** (`OPERATING_CONDITIONS.md` §1.7 の 52)。

- **両 peer は WP-6a / 6b で 1.8.0 を宣言済みである** (local main `a3a35af`)。**したがって 4 plug すべてが駆動し、xfail も skip も要らない。**
- **それでも gate は書く**: **1.8.0 未満を宣言しながら `idempotency` を `unavailable` 以外と宣言する plug が現れたら `pytest.fail` で赤にする。** **`pytest.skip` も `xfail` も使わない** — skip は未検証を許可に変え (`OPERATING_CONDITIONS.md` §1.3 の 26)、xfail は CI の `xfailed == 0` / `xpassed == 0` 検査 (WP-1c) と衝突するからである。
- **`idempotency` を `unavailable` と宣言する plug は駆動対象外である。** **その内訳は駆動 plug 数の guard が assert する** (下の完了条件。**現時点の期待は「駆動 4 / 対象外 0」である**)。

**(7) 変異 (plug ごとに実測できる形。上の「壊すとどう見えるか」の精密化であり、撤回ではない)**

| plug | (i) (ii) を赤にする変異 | (iii) を赤にする変異 |
|---|---|---|
| **`r2db-api`** | `structured.ApplicationCell.transact` / `apply_schema` の `with self._idempotency_lock:` を外す | **同左** (この plug の直列化はこの 1 つだけである) |
| **`r2db-api-http`** | `PostgresCell` の `_idempotency_key_lock` 呼び出し (`postgres.py:1566` / `:2264`) を外す | `_idempotency_reserve_lock` 呼び出し (`:1594` / `:2292`) を外す |
| **`MitateDB-api`** | `_idempotency_lock_scope` が `self._lock` の代わりに `nullcontext()` を返すようにする | **同左** |
| **`MitateDB-api-http`** | **同上 (cell lock)** | **同上 (cell lock)** |

**開示 (C-27 行に書く。C-05 の honest limits と同じ扱い)**: **`MitateDB-api-http` では、`idempotency_begin` / `idempotency_reserve` が取る PostgreSQL の session advisory lock を外しても C-27 は赤にならない** — **共通 suite の 1 plug は 1 application につき 1 つの `ApplicationCell` しか持たず、その cell の `RLock` が同一プロセス内の 2 要求を先に直列化するからである。** **advisory lock が load-bearing になるのは cell (= プロセス) を跨ぐ場合であり、その非 vacuity は peer-local テストが担う** — `MitateDB-api/tests/test_idempotency_concurrency.py` は**同一 DB に対して `cell_a` / `cell_b` の 2 cell を張って**駆動しており (WP-6d-i 完了条件 1 / 2 / 6)、そこでは cell lock は効かない。**共通 suite でこれを直接駆動するには 1 配備を 2 プロセスで serve する必要があり、socket plug も uvicorn 1 本なので本フェーズの範囲では作れない** (`process_ceilings` が宣言で扱う面と同じ境界である。D-5 (iv)、C-26 (4))。**この開示は「観測できない部分を開示する」規律であって、C-27 の弱化ではない** — **r2db 側では同じ観測が実 advisory lock を直接 pin している** (`r2db-api-http` の行)。

**(8) xdist group**

**C-27 の per-plug テストに明示の `xdist_group` marker は置かない。** **`conformance-tests/conftest.py:96` が adapter param を持つ item をその param 名の group へ自動で入れる**ので、C-05 と同じ扱いになる (**C-05 自身も明示 marker を持たない**)。**registry 全体を見る非 vacuity guard (駆動 plug 数) だけが param を持たないので `registry-guards` group に入る。** **C-26 のような launcher ごとの専用 group は要らない** — あれは実プロセスを起動するという別の理由による例外である (D-1 (B) 8)。

**(9) 取り込み順と、ペアセッションへの通知**

- **§8.1 の既存の順序 (WP-3 → WP-6d-ii、WP-6a / 6b → WP-6d-ii) はそのままである。**
- **追補 (v1.5)**: **WP-6d-ii は、WP-4 の統合 branch (socket plug 2 本を足して 6 plug になる版) が local main に入った後に着手する。** **論理的な依存ではなく (socket adapter は hook を継承するだけである)、`conformance-tests/adapter.py` と 4 adapter が WP-4 統合 branch の territory だからである** — 同じファイルに 2 つの WP が同時に入ると、共有 checkout の規律 (`OPERATING_CONDITIONS.md` §1.2) の下では衝突が避けられない。**着手前にペアセッションへ通知する。** **この順序は §8.1 の追補行に写す。**

**(10) 触るファイル (作業指示書 WP-6d-ii の manifest が正本。ここは設計側の確認)**

`conformance-tests/test_c27_concurrent_same_key.py` (新設)、`conformance-tests/adapter.py` (**abstract method 1 個 + `IdempotencyHold` + 契約文の docstring**)、4 adapter (**実現**)、`conformance-tests/CONDITIONS.md` (**C-27 行を executable に**) と `CONDITIONS_HISTORY.md`、`docs/design/CONFORMANCE_ADAPTER_V1.md` (**新 § 1 つ、port v1.14 → v1.15**)。**socket adapter 2 本には触らない。** **両 peer の `src/` にも触らない** (**6d-i の成果物をそのまま駆動する**)。

#### 実施註 (6d-ii) (**2026-09-10 (v1.7)。上の確定節 (1)〜(10) と、その上の「実装の形 (6d-ii)」「実施 2026-09-08 (v1.4)」は 1 文字も書き換えていない**)

**【実施 2026-09-10】** **branch `phase10-wp6dii`。実装コミット `d97de35`、Opus のコードレビュー 1 巡目の判定は「accept with fixes」であり是正コミットは `8425ef4`、その後の main 取り込みが `05bc548` である。main へのマージは `2455f96` (`[skip ci]`)。** **着手条件 2 つ (確定節 (9) と作業指示書 WP-6d-ii) はどちらも先に満たされていた** — **版フリップは local main `a3a35af`、WP-4 の統合 branch は local main `9361f1b` である。** **確定節が定めた形はすべてそのまま実装された。以下は実施の記録であり、確定の変更ではない。**

1. **port v1.15**: **`conformance-tests/adapter.py` に abstract method `hold_after_idempotency_lookup(self, session, idempotency_key)` を 1 つと、非 normative な handle `IdempotencyHold` (`wait_until_held(timeout_s=30.0) -> int` の 1 メソッド) を足した。** **docstring には確定節 (1) の契約文を逐語で複製した** (常設規律 4)。**port 文書は `docs/design/CONFORMANCE_ADAPTER_V1.md` v1.14 → **v1.15**、新節は §25 である。**
2. **plug ごとの実現は確定節 (4) の表のとおりである** — **`r2db-api` は in-process の `structured.ApplicationCell._idempotency_lookup` / `_idempotency_reserve` の 2 つを monkeypatch し、予約の後 (戻り際) で保持する。** **`r2db-api-http` は `PostgresCell` の同名 2 つを同じ形で monkeypatch する** — **保持点では key の advisory xact lock と件数の advisory xact lock の両方を保持したままである。** **MitateDB の 2 plug は `ApplicationCell._idempotency_check` 1 つを monkeypatch し、そのメソッド自身の予約を終えた「新規受理」の戻り際で保持する。** **socket 2 plug は http adapter の subclass として、これらを 1 行も書かずに継承した** (確定節 (4) 末尾)。**両 peer の `src/` と socket adapter 2 本には触っていない** (作業指示書 WP-6d-ii の「触らないファイル」)。
3. **確定節に無かった実現上の追加が 1 件ある (レビューで形を絞った)** — **両 HTTP adapter の `_run` に「`self._loop` が使用中で、かつ呼び出し元が別スレッドである」ときだけ使い捨ての event loop へ落ちる fallback を足した。** **C-27 は先着 (A) と後着 (B) を別々の OS スレッドから出すので、A が保持されている間 `self._loop` は塞がっているためである。** **同一スレッドからの再入は従来どおり `RuntimeError` で大きく落ちる** (静かに別の loop へ逃がすと、既存の in-flight 保持系の欠陥が見えなくなる)。**安全なのは `ASGITransport` が状態を持たず、socket subclass が呼び出しごとに使い捨ての transport を開くからである。**
4. **テスト** (`conformance-tests/test_c27_concurrent_same_key.py`、新設): **plug ごとに 5 本** — 確定節 (5) の観測 **(i)〜(iv)** と **hold-timeout の 1 本** — に、**plug を持たない guard 2 本** (**駆動 plug 数**と、**合成した宣言を食わせる版 gate の単体検査**) を加えた形である。**版 gate は 1.8.0 未満を宣言しながら `idempotency` を `unavailable` 以外と宣言する plug を `pytest.fail` にする** (skip / xfail を使わない。確定節 (6))。**証拠は adapter が既に持つ読みだけで取る** — 効果行は `select_eq` の件数、実行の監査 event は `audit_query` を plug の宣言する `max_limit` で頁送りして数える (確定節 (5))。**(iii) の上限 E は capability document から読み、定数を書かない** — **6 plug すべてが隔離面で `idempotency_entries` = 20 を宣言する。** **E が実際には尽くせない値だった場合は `pytest.fail` する** (返して緑にしない。レビュー是正 F4)。
5. **`CONDITIONS.md` の C-27 行を `executable` に改め、旧文 (宣言のみの版) を `CONDITIONS_HISTORY.md` の `## C-27` へ逐語で移した。** **開示 (確定節 (7) の MitateDB の行) は行の中に書いた。**

**変異の実測 (逐語。確定節 (7) の表に 1 対 1 で対応する)**:

| # | 変異 | 集計行 (逐語) | 赤になった観測 |
|---|---|---|---|
| **M1** | r2db の key advisory lock を外す | **`8 failed, 7 passed`** | **(i) (ii) が `r2db-api` / `r2db-api-http` / `r2db-api-socket` の 3 plug で赤** |
| **M2** | r2db の件数 advisory lock を外す | **`2 failed, 8 passed`** | **(iii) が `r2db-api-http` / `r2db-api-socket` でちょうど赤** |
| **M3** | MitateDB の `idempotency_begin` の session advisory lock を外す | **`10 passed`** | **赤にならない** — **確定節 (7) が予告した開示のとおりであり、cell の `RLock` が共通 suite (1 plug = 1 cell) では先に直列化する。C-27 行に開示として書き、この lock の非 vacuity は peer-local テスト (2 cell 構成) が担う** |
| **M4** | MitateDB の外側 cell lock を外す | **`9 failed, 6 passed`** | **(i) (ii) (iii) が MitateDB の 3 plug すべてで赤** |
| **M5** | hook を no-op にする | **`4 failed, 1 passed`** | **`wait_until_held` が全件で時間切れになり大きく落ちる** (確定節 (2) の「skip も xfail もしない」) |
| **M6** | (レビュー) 保持点を件数の予約より前へ動かす | **`2 failed, 30 passed`** | **(iii) が `r2db-api-http` / `r2db-api-socket` でちょうど赤** — **確定節 (3) の「受理区間の末尾に置く理由」を実測で裏づけた** |

**レビュー (Opus、1 巡。判定「accept with fixes」。是正は `8425ef4`)**: **F1** `_run` の fallback が同一スレッドの再入まで飲み込む形だった (**別スレッドに限り、コメントに socket subclass の使い捨て transport の根拠を書いた**)。**F2** `wait_until_held` の戻り値を捨てていた (**`== 1` を assert する**)。**F3** replay の `request_id` 一致を条件付きでしか見ていなかった (**無条件の assert にした**)。**F4** 尽くせない `idempotency_entries` の値で静かに返っていた (**`pytest.fail`**)。**F5** 使われない定数が残っていた。**F6** port 文書の契約文の引用が折り返しで 1 バイトずれていた (**byte 一致に戻した**)。**F7 (情報)** テストが `attempt_mutation_with_result` ではなく `attempt_batch_with_result` + `BatchOperation(idempotency_key=...)` を使っている — **等価であり、(iv) が要求する「2 項目の batch」のためにこちらが必要である。**

**作業指示書 WP-6d-ii の完了条件の充足**: **確定節の表の 3' / 4' / 7' / 11 / 12 / 13 と、v1.1 の表の 1 / 2 / 5 / 6 / 8 / 9 / 10 はいずれも満たした。** **例外を 1 件開示する** — **完了条件 12 が挙げた 2 つの変異のうち「`wait_until_held` の戻り値を定数 1 にする」は反証不能である。** **保持されるのは常に 1 件なので、実測値と定数 1 が一致するからである。** **監督裁定 2026-09-10: これを受理する** — **測っている性質 (「保持点へ実際に到達した」こと) は M5 (hook の no-op 化で全件が時間切れになる) が pin しており、同条件のもう一方の変異 (上限超過を握り潰す) は赤になる。** **「戻り値は実測値であって引数の折り返しではない」という port の規約 (確定節 (2)) は、保持件数が 1 に固定されている限り共通 suite では観測できない。**

**集計行 (逐語)**: **C-27 のファイル単独は `32 passed` (実装担当が 3 回、是正後に 2 回、レビュー担当が 1 回)。** **`conformance-tests` 全体は `991 passed` を 2 回** (**WP-7 / WP-5b のマージ前の版である**)。**両 peer の suite は不変、C-05 / C-19 / C-25 の再確認は `163 passed`。** **監督の完了ゲート (main `2455f96` での単独 root suite) は §9.1 の項目 1 の追記である。**

### D-14 外部レビュー 2 の小修正の束 (**WP-1c**。新設 v1.3)

**決定 (監督確定 2026-09-08。§5 U-11)**: **外部レビュー 2 が挙げた 3 件の小修正を 1 つの WP (Class B) にまとめ、WP-3 より先に main へ入れる。** **`.github/workflows/ci.yml` は WP-3 と領域が異なる** (WP-3 が触るのは conformance job の前段、本 WP が触るのは集計 step と比較 job) **ので、WP-3 は rebase で吸収する。**

1. **MitateDB の digest から `budget: {}` が落ちる不具合** (`MitateDB-api/src/mitatedb_api/cell.py:2702` の `if budget:`) を **`if budget is not None:`** に是正する (r2db は `r2db-api/src/r2db_api/service.py:1237` で既にこの形)。**是正範囲は `transact` だけではない** — **`cell.py` のスキーマ操作 3 箇所 (`create_collection` / `add_field` / `alter_field`) の digest 生成も同じ穴を持つ。** **HTTP 層は既に `digest_extra` で `budget` を渡していたが、in-process の cell 経路は渡していなかった** ので、同じ要求が経路によって別の digest になり得た。**両 peer に「budget の省略と `budget: {}` は異なる要求である」ことを示すテストを置く** — 同一キーの再送が `CONFLICT` になること、および plan digest が異なることの両方である (`digest_request` は plan digest も作るので同じ影響がある)。**計画文書 §8 の R-25。**
2. **CI に `skipped == 0` / `xfailed == 0` を強制する** — **集計 step と比較 job の両方**、**3.11 / 3.12 とも**である。**監督裁定 2026-09-08 (検査の拡張)**: **`xpassed` と `deselected` も `> 0` を赤にする** — **`xpassed` は宣言が陳腐化した xfail (実測が宣言を追い越している)、`deselected` は集計行が suite 全体を表していないことを意味し、どちらも「合格の集計が現物を覆っている」という前提を崩すからである。** **計画文書 §8 の R-26。**
3. **文書の矛盾 2 件を直す** — `r2db-api/README.md:158` を `docs/work-orders/DEPLOY_PHASE6_20260904.md` の項 9〜12 に基づく**事実のみ**で書き直し、`docs/work-orders/HANDOVER_20260908_FABLE.md` §1 に**日付付きの訂正註を追記する** (`docs/work-orders/PUBLICATION_GATE_20260906.md` §3.2 を指す。**引き継ぎ書は履歴なので書き換えない。追記である**)。**同じ陳腐化は `security/CONTROL_MAPPING.md` にも残っていた** — **SI-00〜SI-03 の受入境界 (acceptance boundary) の文が「VPS には未導入」を前提にしていたので、2026-09-05 の r2db Stage 1 の記録から書き起こす。** **`security/` を触るので、その 1 コミットは変更クラス D である** (裁定記録を添える。内容は現状記述の更新であり security-contract の変更ではない。WP-0 と同じ扱い)。**計画文書 §8 の R-28。**

**根拠**: **3 件とも「宣言・記録と現物の食い違い」であり、P-3 の面である。** **(2) は `OPERATING_CONDITIONS.md` §1.3 の 22 が合格条件として定めている値が CI では検査されていないという不整合であり、同 §1.3 の 26 (skip は未検証を許可に変える) の機械化でもある。**

**壊すとどう見えるか**: **(1)** `is not None` を `if budget:` に戻すと、両 peer の新規テストのうち MitateDB 側が赤になる。**(2)** 合成した `2807 passed, 1 skipped` の集計を食わせて緑になるなら検査が効いていない (**`xpassed` / `deselected` も同じ形で合成して赤を実測する**)。**(3)** 機械検査を持たないので**監査照合**であり、照合対象の逐語記録を残すこと自体が完了条件である。

**【実施 2026-09-08。branch `phase10-wp1c` の `5944013` (+ main `504c8b2` のマージ)。Opus のコードレビューの判定は「accept with fixes」であり、指摘の是正を反映した確定コミットは `2431e93` である】** **範囲は上記 1〜3 のとおりで、`transact` に加えてスキーマ操作 3 箇所の digest 生成と `security/CONTROL_MAPPING.md` の SI-00〜SI-03 の受入境界を含む。** **実測**: `MitateDB-api/tests` は `997 passed`、`r2db-api/tests` は `1172 passed`、`tools/tests` は `58 passed`、**CI 検査の非 vacuity は合成した集計入力で実測した** (`2807 passed, 1 skipped` / `2 xfailed` を食わせると赤)。**main へのマージは次のゲート束で監督が行う (現時点で main 未マージ)。**

### D-15 フェーズ9 R-2 の走査 lock mode を `SHARE ROW EXCLUSIVE` に改める (**WP-R35**。新設 v1.4)

**決定 (監督確定 2026-09-08。WP-6d-i のコードレビューが見つけた既存の欠陥であり、両 peer に在る)**: **nullable 違反走査の `LOCK TABLE ... IN SHARE MODE` を `LOCK TABLE ... IN SHARE ROW EXCLUSIVE MODE` に改める。** **両 peer、小さな Class B の WP「WP-R35」(worktree `phase10-r35`) で行い、決定的な 2 スレッドのテストを添える。** **実施済みであり、コミットは `46b081a` + レビュー是正 `7ead163` である (Opus レビュー accept。両 peer の既存 `tests/test_constraints_declaration.py` に 2 スレッドテストを追加)。** **計画文書 §8 の R-35。**

**根拠**: **フェーズ9 R-2 が置いた走査は、同一トランザクション内で SHARE を取った後に `ALTER TABLE` (ACCESS EXCLUSIVE) を発行する** — r2db は `r2db-api/src/r2db_api/postgres.py` の `add_field` / `alter_field` (**本書の基準 main では `:2292` / `:2373`。WP-6d-i の是正後は概ね `:2310` / `:2410`**)、MitateDB は `MitateDB-api/src/mitatedb_api/backend_postgres.py` の同じ 2 経路 (**基準 main では `:914` / `:1215`。WP-6d-i の是正後は概ね `:930` / `:1248`**) である。**SHARE は SHARE と衝突しないので、同じ表に対する idempotency key を持たないスキーマ変更 2 件が両方とも SHARE を取れてしまい、その後それぞれの `ALTER TABLE` が相手の SHARE を待つ** — **相互待ちであり、解けるのは PostgreSQL の deadlock detector が一方を中断したときだけである。** **`SHARE ROW EXCLUSIVE` は自己衝突するので、後着は `LOCK TABLE` の時点で待ち、先着の commit の後に進む。** **行の書き手を排除する性質 (R-2 の走査が依拠する性質) はそのまま保たれる** — したがって R-2 の完了条件は弱まらない。

**D-13 との関係**: **D-13 の項 5 と §5 U-7 は「異キーの件数 bound に `LOCK TABLE ... IN SHARE MODE` は採らない」と定め、実装担当にフェーズ9 R-2 の前例の lock mode を現物で確認させた** (作業指示書 WP-6d-i の完了条件 8)。**その確認が本欠陥を露出させた。** **本決定は D-13 を変えない** — **同一キーの同時送信の直列化 (D-13) と、キーを持たない同時スキーマ変更の相互待ち (本項) は別の経路である。**

**壊すとどう見えるか**: **mode を `SHARE` に戻すと、両 peer の 2 スレッドテストが deadlock (`deadlock detected`) または待ちで赤になる。**

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

**【実施済み 2026-09-08 (v1.4)。WP-6d-i】** **branch `phase10-wp6d` の `21cc8fb` (実装) + `6a3453d` (レビュー是正) + `685ebfa` (`phase10-r34` との統合)。main へのマージは `4e1020a` (WP-6d-i + R-34 + R-35 の束) + 直後の pin 修正 `ee80c97` (`test_limit_class_vocabulary.py` の `ResourceLimitError` 呼び出し数 33 → 35。F2 の 2 箇所分。ゲート 3 が検出し、ゲート 4 で再確認)。** **(α) の形は保たれているが、lock の種類は peer で違う** — **r2db は裁定どおり transaction-scoped (`pg_advisory_xact_lock`) であり、MitateDB は catalog 読みが同じ接続の途中で自己 commit する構造のため transaction-scoped では早期に解放されてしまうので SESSION advisory lock を書く側の接続で取り、`finally` で明示的に解放する** (詳細と変異の実測は D-13 の実施註)。**この差は「同じ必須の安全結果を、platform ごとの統制で満たす」形であり (`CLAUDE.md`)、裁定 (α) の変更ではない。** **本実施の過程で、フェーズ9 R-2 の前例確認 (本裁定が課した報告義務) が両 peer の走査 lock mode の欠陥を露出させた — 起票は D-15 / 計画文書 §8 の R-35 である。**

### U-8 新条件 C-27「同一キー同時送信」を置くか

**(α) 新条件 C-27 を 1 件足す** vs (β) C-23 (再送の意味) の射程を広げる。(β) は C-23 の駆動集合と条件文を書き換えることになり、**「逐次経路で示した性質」と「同時送信で示す性質」が 1 行に混ざる。** **確定 (監督、2026-09-08): (α)。** **観測項目と hook の形は D-13 の「実装の形 (6d-ii)」である** (先着を照会の直後・実行の前に保持し、後着を送り、先着を解放する決定的な検査。**hook の名と形は `hold_in_flight` (C-05) に倣って設計担当が決める**)。**4 plug すべてで駆動し、socket adapter は継承する。** **変異注入は「lock を外すと (i) (ii) が赤になる」である。** **本フェーズの新条件は C-26 と C-27 の 2 件になる** (§6.2)。

**【実施済み 2026-09-10 (v1.7)。WP-6d-ii】** **branch `phase10-wp6dii` の `d97de35` (実装) + `8425ef4` (レビュー是正) + `05bc548` (main 取り込み)。main へのマージは `2455f96` である。** **確定 (α) の形はそのまま実装された** — **新条件 C-27 を 1 件だけ足し、C-23 の条件文と駆動集合には触れていない。** **hook は D-13 の確定節が定めた `hold_after_idempotency_lookup(session, idempotency_key)` (保持点は受理区間の末尾) であり、port は v1.15 になった。** **駆動は 4 plug ではなく 6 plug である** — **裁定当時は 4 plug だったが、WP-4 が socket 2 plug を足し、その 2 本は hook を 1 行も書かずに継承した (「socket adapter は継承する」の実現形)。** **変異は peer で違い、MitateDB の PG session advisory lock が共通 suite では load-bearing にならないことを C-27 行に開示した** (D-13 の実施註 (6d-ii) の M3)。**「lock を外すと (i) (ii) が赤になる」は M1 / M4 で実測した。**

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


### U-14〜U-22 の前提 (実施中の裁定、2026-09-08〜2026-09-10。**v1.6 の新設**)

**U-14 以降は、WP-4〜WP-8 の実施中に実装担当の報告と Opus のレビューが出した論点への監督の確定である。** **依頼者裁定の根拠は §5 冒頭と同一 (2026-09-07 の委任) であり再掲しない。** **拠り所とした報告・レビュー・裁定文は監督保管であり、本節はファイル名だけを記す。** **U-1〜U-13 は 1 つも撤回していない。**

### U-14 WP-4b が報告した 4 件の blocker (2026-09-08。`wp4b-report.md` / `wp4b-rulings.md`)

**(1) C-05 の代理指標を撤廃する** — `"http" in adapter.name` は代理指標であり (`OPERATING_CONDITIONS.md` §1.7 の 52)、**`adapter.transport_kind in ("asgi", "socket")` に直す。** **(2) `conftest.py` の `_install_residue_tracking` を冪等にする** (継承クラスを二重 wrap していた)。**(3) 単一 event loop で in-flight が 1 に留まる件は、計測を待たずに WP-8a / WP-8b を発動する** — **これは R-20 の直接証拠 (実配備で in-flight = 1、宣言 `concurrency` が到達不能) であり、D-8 (2) の判定規則を待たない。** **WP-7 は WP-8 の後に K=1 / K=3 を取り、「前」は本件の定性的観測を記録する。起票は L10-8。** **(4) socket plug の wire 拒否は運搬位置で分ける** — **header / path / method で運ばれる不正値は「wire 拒否」(契約エラー形なし) として受理し、body (JSON) の不正値は従来どおり契約エラーを要求する。** 開示は C-03 / C-15 の honest limits (WP-5b)。 **【追補 2026-09-10】受理枝は `httpx.LocalProtocolError` に限定した** — `httpx.HTTPError` 全体では上流ダウン時に検査が空振りする (統合レビュー M-2)。

### U-15 件数 bound を守る lock の形 (2026-09-08。`wp6a-review.md` F1 / `wp6-rulings.md`)

**(α) 表単位の定数 key の `pg_advisory_xact_lock` に両 peer を統一** vs (β) `LOCK TABLE ... IN SHARE MODE` (r2db の実装形) vs (γ) `... IN SHARE ROW EXCLUSIVE MODE` (MitateDB の実装形)。**(β) は実 PG で deadlock する** — レビューが同一 idiom (SHARE → count → INSERT、barrier 同期 2 writer) を実測し **`{1: 'DeadlockDetected', 2: 'OK'}`**。(γ) は動くが設計と不一致で非対称。**確定: (α)。key は両 peer とも `hashtext('<schema>.<table>')`、同名 helper `_take_bound_advisory_lock` に揃える。同型性は r2db 形に収束させる。** **併せて監督の誤りを記録する** — **本件の発注文はフェーズ9 R-2 の `SHARE MODE` を「件数 bound の前例」として引いたが、あれは既存行の走査用であって前例ではない。誤った前例引用が両 peer に deadlock する lock を書かせた。**

### U-16 WP-8b の直列化の範囲 (2026-09-08 / 09。`wp8b-review.md`)

**(α) 案 A = 全公開メソッドの lookup → pass-1 → pass-2 を `_lock` の内側に入れる** vs (β) 案 B = cell に developer pool を入れて pass-1 が独自接続を借りる。**根拠はレビューの実証である** — **`_lock` が守るのは各メソッド最後の backend 呼び出しだけで、pass-1 の catalog 読み 8 メソッドと `_idempotency_check` は lock 外で cell 共有の単一 `_developer` 接続を使い、各々が自分で commit / rollback する。** **委譲を入れた branch の probe は `probe_race_visible_before_A_commit: 1` (委譲前の main は 0) — 要求 B の commit が要求 A の未完了 DDL トランザクションを commit した。U-10 の前提条件は満たされていなかった。** **確定: (α)。案 B は不採用、要求スコープ接続は L10-9 に起票。`_lock` は `_limit_gate` の hold hook より後・slot より内側に置く** (レビュー §3 の `{'active': 3, 'in_backend': 1}`。この性質を壊すと C-05 の `hold_in_flight(n=3)` が駆動できない)。**追加の確定 (2026-09-09): WP-6d-i の `_idempotency_lock_scope` は外側 cell lock に一本化する** (並行セッションの代案を採用。D-13 訂正註 3)。

### U-17 WP-8a の role pool 容量 (2026-09-08。`wp8a-review.md` F-1)

**確定: `role_pool_size(limits) = limits.concurrency` を置き、served app の `PostgresCell` に渡す。** **委譲前は固定 4 で、宣言 `concurrency` (既定 32) に届く前に pool が涸れて 503 を返した — threadpool 委譲で初めて実並行になり露出した。** **platform pool 側 (F-2) は WP-8c へ送る。**

### U-18 WP-8c 認証前の concurrency slot (2026-09-09。`wp8c-review.md`)

**確定: data 面は認証の前に concurrency slot を取る (両 peer)。裁定 4 (2026-09-06) の HTTP 面の更新であり、concurrency が先・`requests_per_minute` は認証後である。** **MitateDB の `HttpService` は `limit_holder` / `max_concurrency` を必須にして fail-closed にする** (no-op 分岐を残すと「宣言はあるが効かない」配線が黙って通る)。**閉止先は L10-10。**

### U-19 WP-4e / WP-4f の資源の導出 (2026-09-09〜10。`wp4e-report.md` / `wp4f-report-2.md` / `wp4g-report.md` / `wp4-integration-review.md`)

**(1) platform / credential-store pool を宣言 concurrency から導出する** (両 peer 同名 `role_pool_size`)。**(2) role の `CONNECTION LIMIT` を実 pool 構成 + 4 に揃える新 migration を置く** (r2db `0013` / MitateDB `0012`)。**根拠は実測** — **`FATAL:  too many connections for role "…_controlplane"` が、まだ 1 本も接続していない新規 pool の初回接続で起きた。pool の maxconn を上げても解けない hard な拒否である。** **(3) F-16 を置く** — `ops verify-declarations` に加え、**4 つの composition root すべてが起動時に自プロセスの role だけを見て fail-fast し、C-26 がそれを観測する。** **(4) migration の走査は「登録のみ」の application 行 (role 名が NULL) を除外する** — 除外しないと migration 全体が rollback し、`register_application` を使った配備では一切適用できない (統合レビュー H-1)。**(5) F-16 の floor は role ごとに `max` を採り、schema 所有者 role を 3 クラスすべてから明示的に除外する** — 上書き代入は「最後に書いた class 勝ち」であり、実際に不足している role を検査が黙って通す (統合レビュー M-1。**「所有者は意図的に除外している」という既存コメントは事実ではなく、暗黙 ACL で 3 クラスすべてに一致していた**)。

### U-20 WP-6c (C-26) の射程 (2026-09-09。`wp6c-review.md` / `wp6c-review-2.md`)

**(1) socket adapter は本番 composition root を使わず HTTP composition を継承する** (v1.1 の D-1 で既決。本裁定は再確認であり、本番 composition root の証拠は C-26 だけが持つ)。**(2) C-26 のダイヤル先は「serve された `capabilities.surfaces`」である** — 宣言表から読み戻した値との一致も併せて確かめる (宣言表だけを読む形では「serve している文書が宣言と違う」場合を見逃す。レビュー F1)。**(3) 孤児 sweep は所有者限定にする** (`fcntl.flock` の cross-process advisory lock を取れた prefix だけを掃く)。**起動失敗時は全 teardown を行い、残骸検査は DB / role / temp dir を含める。** **(4) launcher は `R2DB_*` / `MITATEDB_*` を継承 env から落として起動する。**

### U-21 運用上の確定 (2026-09-09)

**(1) push を停止する** — **GitHub の課金上限に達したことを依頼者が確認したため、本リポジトリでの push を行わない。ローカルの commit と main へのマージは続ける。** **帰結として本フェーズの CI 集計行は未取得である (L10-15)。文書だけのコミットには `[skip ci]` を付ける。** **(2) L10 番号の分担** — 本セッションが L10-8〜L10-19 を使い、並行セッションは 20 番以降を使う。

### U-22 発注の形に関する確定 (2026-09-08〜2026-09-10)

**(1) WP-5 を WP-5a / WP-5b に分ける** (作業指示書 §5 訂正註 1。「主張は実測の後」)。**(2) WP-1b (L10 族の `check_doc_refs` 登録) は単独コミットで先に入れる** (`1cd2c39`)。**(3) WP-4a の「prefix 別系統化」(疑義 2 拡張) は採らない** — `_is_isolated_copy` / `is_bound` / `data-concurrent` の分岐を撤去し、`self._app` / `self._control_app` と一致すれば既存 surface を `rebind_app` する 2 分岐に統一する (629 行 → 583 行)。**(4) WP-6c の変異は「到達不能 URL の宣言」で代替する** (`urllib.error.URLError: <urlopen error [Errno 61] Connection refused>`)。
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
| **C-27** (**新設。v1.3**) | **同一 idempotency key の同時送信を、adapter hook で先着を照会の直後 (実行の前) に保持する形で決定的に駆動する** — (i) 同一 digest は実行 1 回 + 後着が同じ `request_id` の replay、(ii) 異 digest は実行 1 回 + 後着が `CONFLICT` (`violated_declaration: idempotency_key`)、(iii) 異キー 2 件を `idempotency_entries` 上限 −1 の状態で同時送信すると 1 件が `LIMIT_EXCEEDED` (D-13)。**SI-11 / SI-08 / SI-14 に紐づく (C-23 と同じ 3 つ)。****4 plug で駆動し socket 2 plug は継承する。** **変更クラス C。** **行は C-26 と同じ方式で先に `CONDITIONS.md` に置き (宣言のみ)、実行可能になるのは WP-6d-ii である。** **契約上の位置づけ: C-27 は 1.8.0 の条件付き義務 `idempotency_concurrent_same_key_sends_serialized` (`conditional` の (1)。branch `phase10-wp5` の `73adbda`。**WP-5a 本体は main `3d7f823` に入っており、この追補だけが次のゲート束でのマージ待ちである**) の実行可能な条件であり、拘束するのは 1.8.0 を宣言し、かつ `idempotency` が `unavailable` 以外である plug に限られる** — **C-25 が 1.7.0 の宣言に結び付いているのと同じ形である** (D-13)。 **【追記 2026-09-09 (v1.5)。上の文は v1.3 時点の原文であり、消さずに残す】** **観測は 4 件である — (iv)「先着が受理後に失敗したら、後着は新規要求として実行される」を足した** (D-13 の「実装の形 (6d-ii) の確定」(5))。**hook の名は `hold_after_idempotency_lookup(session, idempotency_key)`、保持点は受理区間の末尾 (照会が absent → `idempotency_entries` の予約 → **効果の実行前**) である** (同 (1) (3))。**変異は peer で違う** — **r2db は plug ごとに key advisory lock / 件数 advisory lock / cell lock、MitateDB は 2 plug とも cell lock であり、MitateDB の PG session advisory lock は共通 suite (1 plug = 1 cell) では load-bearing にならないことを開示する** (同 (7))。**版 gate は `pytest.fail` であり skip / xfail を使わない** (同 (6))。 **【実施 2026-09-10 (v1.7)。上の 2 つの原文は消さずに残す】** **C-27 行は `executable` になった** (`CONDITIONS.md`。旧文は `CONDITIONS_HISTORY.md` の `## C-27` へ逐語)。**駆動は「4 plug + socket 2 plug の継承」ではなく **6 plug 全数**である** — WP-4 が socket 2 plug を registry に足したので、継承の結果として 6 件が同じ観測を駆動する。**実施の記録は D-13 の実施註 (6d-ii) と §11.11、閉止は §9.1 の「8 (f) / 14 (再)」である。** |

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
| **WP-6d-i / WP-6d-ii** (**新設 v1.3**) | 同一 idempotency key の同時送信の直列化 (D-13。R-24) | **6d-i** = `r2db-api/src/r2db_api/postgres.py` と in-memory cell (`structured.py`)、`MitateDB-api/src/mitatedb_api/backend_postgres.py` と `cell.py`、両 peer の `tests/test_idempotency_*.py` / **6d-ii** = `conformance-tests/test_c27_concurrent_same_key.py` (新設)、`conformance-tests/adapter.py` と 4 adapter (hook)、`conformance-tests/CONDITIONS.md` (C-27 行) | **6d-i は WP-3 に依存しない (今すぐ着手可、worktree `phase10-wp6d`)。触るファイルが重なるもの以外すべてと並行可。** **6d-ii は WP-3 の hook 抽出の後。WP-4 と並行可。** **WP-6a / 6b (migration + 宣言) とはファイルが分離している。** **【状態 2026-09-08 (v1.4)】6d-i は実装済みである** — branch `phase10-wp6d` の `21cc8fb` / `6a3453d` / `685ebfa`、main へのマージは `4e1020a` (WP-6d-i + R-34 + R-35 の束) + 直後の pin 修正 `ee80c97` (`test_limit_class_vocabulary.py` の `ResourceLimitError` 呼び出し数 33 → 35。F2 の 2 箇所分。ゲート 3 が検出し、ゲート 4 で再確認) (§11.4)。**6d-ii は未着手である** | **C** — **宣言と条件 (`CONDITIONS.md` / 共通 suite) に触るからである。** **同名 helper の pair-closing commit は D** |
| **WP-R35** (**新設 v1.4**) | フェーズ9 R-2 の走査 lock mode の是正 (D-15。計画文書 §8 の **R-35**) | `r2db-api/src/r2db_api/postgres.py` と `MitateDB-api/src/mitatedb_api/backend_postgres.py` の `add_field` / `alter_field` の走査 lock 1 行ずつ、両 peer の `tests/` (**決定的な 2 スレッドテスト**) | **WP-6d-i の後** (同じ 2 ファイルを触る)。**それ以外とは並行可。** **実施中 (worktree `phase10-r35`)。コミットは `46b081a` + `7ead163`** | **B** |
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
| **WP-6d-ii × WP-4 の統合 branch** (**追補 2026-09-09 (v1.5)。上の行の「WP-4 とは並行可」は消さずに残す**) | `conformance-tests/adapter.py` と 4 adapter の**ファイル単位の territory** | **順序 (WP-4 の統合 branch が local main に入る → WP-6d-ii)**。**論理的な依存ではない** (socket adapter は hook を継承するだけであり、WP-6d-ii は socket adapter 2 本に触らない) — **同じ 5 ファイルを 2 つの WP が同時に開くことを避けるための運用順である** (共有 checkout の規律、`OPERATING_CONDITIONS.md` §1.2)。**着手前にペアセッションへ通知する** (D-13 の「実装の形 (6d-ii) の確定」(9)) |
| **WP-6d-ii × WP-6a / WP-6b** (**追補 2026-09-08**) | 版フリップ (両 peer の `contract_version` 1.8.0) | **順序 (WP-6a / 6b → WP-6d-ii)**。C-27 は 1.8.0 の条件付き義務の実行可能条件であり、フリップ前に入れると xfail を要して CI (`xfailed == 0`、WP-1c) が赤になる (D-13) |
| **WP-R35 × WP-6d-i** (**追補 v1.4**) | 両 peer の backend (`r2db-api/src/r2db_api/postgres.py` / `MitateDB-api/src/mitatedb_api/backend_postgres.py`) | **順序 (WP-6d-i → WP-R35)**。**関数が違う** (6d-i は idempotency の照会・記録、WP-R35 は `add_field` / `alter_field` の走査 lock) **が同一ファイルなので直列に取り込む。** **WP-6a / 6b とも同じ規約に従い、後から入る側が先に入った現物の上に載せる** |
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

### 9.1 完了ゲートの実測 (**v1.6 の新設**。WP-9、2026-09-10。**項目 1〜17 は 1 つも書き換えていない**)

**数値はすべて監督がリポジトリルートで単独実行した集計行の逐語である** (`OPERATING_CONDITIONS.md` §1.3 の 19〜21)。

| 項目 | 実測 | 状態 |
|---|---|---|
| **1** | ``3294 passed in 379.82s (0:06:19)` (単独 root suite、main `2152c94` + 本記録の作業ツリー、failed 0 / skipped 0 / xfailed 0、`pg_database` 差分 0 (19 → 19)、nginx 残骸 0、収集 3294 = `COLLECTION_FLOOR` 3294)` (監督が WP-9 のマージ後に記入する)。直前の main `9361f1b` の束ゲートは **`3294 passed in 266.04s (0:04:26)`** で `failed` / `skipped` / `xfailed` / `error` はいずれも集計行に無い。`pg_database` 前後差分 0。 **【追記 2026-09-10 (v1.7)。WP-6d-ii のマージ後の再測。上の行は書き換えていない】** **main `2455f96` (WP-6d-ii を含む) で監督が単独実行した root suite は `3326 passed` であり、`failed` / `skipped` / `xfailed` / `error` はいずれも集計行に無い。`pg_database` 前後差分 0、nginx / uvicorn の harness prefix 一致の残骸 0** | **記入待ち** |
| **2** | harness prefix 一致の uvicorn / nginx 0 件、`ports.json` の listener 0 件 (常駐の無関係 uvicorn 2 件は 2026-09-04 起動の既存 dev サーバで prefix 一致しない) | **合格** |
| **3** | **未取得** — 課金上限で push を停止しており本フェーズの run が無い (U-21)。`conformance` job の所要も未取得で、L10-1 はローカル値で記録した | **未達 (開示、L10-15)** |
| **4** | 3 複製の sha256 = **`ff97ddce2a209a69e819c3d36ae7870f85238afe1181cfc7db688616f54faa35`**。両 peer の `contract_version` は 4 箇所とも `1.8.0` (`0d3d941`)。C-19 の両面一致 assert 緑 | **合格** |
| **5** | 着手時 2807。更新はゲート実測の後に監督が単独コミットで行う | **監督の作業** |
| **5 (再)** (**v1.7**) | **WP-9 の時点で 2807 → 3294 に更新済みである。WP-6d-ii が C-27 の 32 件を足したので、監督が `3294` → `3326` に再更新する** (単独コミット。`OPERATING_CONDITIONS.md` §1.3 の 25) | **記入待ち** |
| **6 / 15** | `§11.10 の PERF 行 (逐語)` — **WP-7 (`tools/perf_baseline.py` の `--concurrency K`、socket transport 列、K=1 / K=3 の実測) は main `ff8d232` に入った。** **PERF 行そのものは監督が単独実行の値で記入する** (K=1 / K=3、WP-6d の lock 導入前後の別を明記する) | **記入待ち** |
| **7** | `registry.json` の `adapters` **6 件**すべて `required: true`、6 plug の集計行は **`959 passed in 160.91s (0:02:40)`** | **合格** |
| **8 (a)** | C-19 の実ダイヤル枝が socket 2 plug の data / control 両面で駆動 (認証付き GET で `200` かつ文書一致) | **合格** |
| **8 (b)** | C-25 (3) が control 面 discovery の `audit_query` 宣言を駆動条件として **6 plug 全数**で駆動、非 vacuity guard 実装済み | **合格 (L9-15 の閉止条件)** |
| **8 (c)** | C-05 の concurrency 枝が socket 2 plug で駆動 (`-k "c05 or c14"` で **`119 passed in 19.32s`**)。**WP-8a / WP-8b が入るまでは両 socket plug とも赤だった** | **合格** |
| **8 (d)** | C-26 の 6 項目を両 launcher で観測 (`-k c26` で **`15 passed in 7.52s`**) | **合格** |
| **8 (e)** | `composition_roots` **2 件** (`r2db-api` / `MitateDB-api`) | **合格** |
| **8 (f) / 14** | **未達。C-27 は `CONDITIONS.md` に「declared」のままで executable になっていない** — **WP-6d-ii (hook `hold_after_idempotency_lookup` と `test_c27_concurrent_same_key.py`) は未実施である。** 1.8.0 の条件付き義務を支える実装 (WP-6d-i) と peer-local テストは在り、**共通条件としての観測だけが残っている** | **未達 (開示)** |
| **8 (f) / 14 (再)** (**v1.7**) | **上の未達は解消した。** **WP-6d-ii を実施し (branch `phase10-wp6dii`、`d97de35` + `8425ef4` + `05bc548`、main へのマージ `2455f96`)、C-27 は `CONDITIONS.md` で `executable` になった。** **駆動は 6 plug 全数であり (in-process 2 + ASGI 2 + socket 2。socket 2 plug は hook を継承する)、どの plug でも skip / xfail されない** — C-27 のファイル単独の集計行は **`32 passed`** (plug ごと 5 本 × 6 + registry guard 2 本)。**非 vacuity の変異は実測した** — **key advisory lock を外すと (i) (ii) が r2db の 3 plug で赤 (`8 failed, 7 passed`)、外側 cell lock を外すと (i) (ii) (iii) が MitateDB の 3 plug で赤 (`9 failed, 6 passed`)、件数 lock を外すと (iii) が r2db の http / socket でちょうど赤 (`2 failed, 8 passed`)、hook を no-op にすると保持待ちが全件で時間切れになる (`4 failed, 1 passed`)。** **開示 1 件**: **MitateDB の PG session advisory lock を外しても赤にならない** (1 plug = 1 cell、cell の `RLock` が先に効く。`10 passed`) — **C-27 行に開示し、非 vacuity は peer-local テスト (2 cell 構成) が担う。** **本フェーズの新条件は C-26 と C-27 の 2 件で確定した。** 詳細は §3 D-13 の実施註 (6d-ii) と §11.11 | **合格 (1 件開示)** |
| **9** | 改訂 6 行はすべて 3000 以内 — C-03 = 1535 / C-05 = 2942 / C-09 = 2978 / C-15 = 2460 / C-19 = 2980 / C-25 = 2232。旧文 6 件 (と C-26 行の旧文) は `CONDITIONS_HISTORY.md` へ逐語で移送済み | **合格 (改訂は 4 行ではなく 6 行になった)** |
| **10** | migration → `ops declare-process-ceilings` → 再起動の順序と LQ4-24 参照が両 peer の配備文書に在る | **合格** |
| **11** | 全 WP で満たした。**例外 1 件を開示する** — **WP-5b の完了条件 11 (旧文の逐語移送) の変異は赤にならなかった。`test_conditions_register.py` は履歴の逐語性を機械照合しない (見出し集合・非空・セル長・リンク解決のみ)。移送自体は逐語だが、それを守る検査は無い** | **合格 (1 件開示)** |
| **12** | 設計レビュー 1 / 2 (v1.1) と差分レビュー (v1.2) の計 3 回。U-1〜U-6 と U-14〜U-22 は §5。計画文書の更新・§10.1 の訂正註 2 件・第 17 次ハンドオーバーは本 WP | **合格** |
| **13** | U-1〜U-6 と U-14〜U-22 の列挙、R-22 の問いを完了報告に置く | **本 WP の成果物** |
| **16** | **実装は WP-1c (`5944013` / `2431e93`) で入り、合成した集計入力で赤になることを実測済みである。両 matrix での緑は CI 未取得のため確認できていない** | **部分達成 (開示、L10-15)** |
| **17** | §10.3〜§10.5 の状態注記、計画文書 §8 の行、第 17 次ハンドオーバーに書いた | **合格** |

**未達の扱い (監督、2026-09-10)**: **項目 3 / 16 は環境要因であり、GitHub 復旧後に 1 回 run を取るだけで閉じる (L10-15)。** **項目 8 (f) / 14 は作業の残であり、フェーズを閉じる前に WP-6d-ii を実施するかフェーズ11 へ送るかを依頼者に報告して決める。** **測っていないものを合格と書かないため、いずれも未達として残す。**

**【追記 2026-09-10 (v1.7)。上の段落は書き換えていない】** **項目 8 (f) / 14 の未達は、依頼者への報告を待たずに WP-6d-ii を実施することで解消した** (上の「8 (f) / 14 (再)」行)。**残る未達は項目 3 / 16 の 1 種だけである** — **CI の集計行が課金上限で未取得であること (L10-15)。これは GitHub 復旧後に main の先頭で 1 回 run を取るだけで閉じる。** **項目 6 / 15 (PERF 行) は §11.10 に入り、記入待ちではなくなった。** **項目 11 の開示 1 件 (WP-5b の完了条件 11) と、本版が足した開示 1 件 (WP-6d-ii の完了条件 12 のうち「戻り値を定数 1 にする」変異が反証不能であること。監督裁定 2026-09-10) はそのまま残す** (§3 D-13 の実施註 (6d-ii))。

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

### 10.3 L10-1〜L10-7 の状態注記と §10.0 の実測結果 (**v1.6**。**上の起票文・表は 1 文字も書き換えていない**)

- **L10-1 閉止 (ローカル値で記録)。** **CI の所要は未取得である (U-21、L10-15)。ローカルの束ゲートは `2807` → `2842` → `2887` → `2964` → `2975` → `2990` → `3294` と伸びたが所要は 3〜6 分台に留まり、`timeout-minutes: 30` を脅かす兆候はローカルには無い。並列度や plug 起動の共有の再設計は要らなかった。** 逐語の集計行は §11.7。
- **L10-2 開いたまま (記録)。** C-26 (4) が観測するのは写像であって実プロセス数ではない、という射程は実装後も変わらない。開示は MitateDB runbook の Invariant 1 (WP-6b で「M は本 deployment の `process_ceilings.data` 宣言値であり、独立に選んだ scaler 最大値ではない」に改訂) と SI-08 行。
- **L10-3 / L10-4 / L10-5 開いたまま (記録)。形は変えていない。** ただし **L10-4 の再評価の契機は前進した** — threadpool 委譲が入ったので「接続あたりのブロッキングが残る」ことを WP-7 の K=1 / K=3 で測れる形になった。
- **L10-6 開いたまま (記録)。** 本フェーズは CI を回していないので、`image-pins` の最後の観測は `c9a937a` の時点である。
- **L10-7 閉止 (2026-09-10)。** **分割は実施の形として成立した** — socket 2 plug は HTTP composition を継承して transport だけを本物にし、本番 composition root の証拠は C-26 が単独で持つ。**統合の再評価の契機はそのまま残す** — 本フェーズはむしろ in-process の手を増やした (C-27 のための `hold_after_idempotency_lookup` を宣言した)。
- **§10.0 の既存項目**: **閉じた** = **L7-2** (6 plug が `required: true` で `959 passed`)、**L8-6** (C-05 の concurrency が socket 越しに駆動)、**L9-15** (§9.1 の 8 (b))、**LQ4-11** (C-26 が本番 composition root を実起動)、**R-18** (契約 1.8.0 + 写像 + C-26 (4))、**R-21** (`bce2598`)、**R-17 残** (`7d8bb0f` + L10 族登録 `1cd2c39`)。**部分閉止** = **L6-5 / L6-12 / LQ4-9** (socket plug と C-26 に限る。in-process / ASGI plug が自己整合のままである射程は C-19 行に開示)、**R-19** (`c9a937a`。CI 上の再確認は L10-15 の run)。**記入待ち** = **L8-5** (`§11.10 の PERF 行 (逐語)`)、**R-20** (**方式は (i) threadpool 委譲に確定した** — 判定規則の計測を待たず WP-4b の定性的観測 (in-flight 1) を根拠に発動した。**数値は `§11.10 の PERF 行 (逐語)`**)。**記録更新のみ** = **L9-10** (1.8.0 で無条件 1 件 + 条件付き 1 件。1.6.0 以降の累計 5 件、総数 15 件)、**LQ4-24** (両 peer の runbook が upgrade 順序とともに参照)。

### 10.4 本フェーズの起票項目 L10-8〜L10-19 (**v1.6 の新設**。番号の分担は §5 **U-21**)

- **L10-8 単一 event loop の上では in-flight が 1 に留まる。** WP-4b が socket plug で観測した (`only 1 of 3 held HTTP requests reached the concurrency-gate stall point`)。**宣言 `concurrency` が実配備で到達不能であることの直接証拠であり、R-20 の判定規則を待たずに WP-8a / WP-8b を発動した根拠である (U-14 (3))。** **閉止 (2026-09-10)** — 両 peer が同期区間を `run_in_threadpool` へ委譲し、C-05 の concurrency 枝が socket 2 plug で緑になった。
- **L10-9 要求スコープ接続 (U-10 の並行面)。** MitateDB の cell は `_runtime` / `_developer` を 1 本ずつ保持して全要求で共有する。**WP-8b は案 A で安全側に倒したので、同一 Application 内の実並行度は 1 である。** **開いたまま** — **判断材料は WP-7 の K=3 / K=1 の比であり、結果次第で「フェーズ11 (計画文書 §8 の R-31)」か「閉止」かを監督が裁定する。**
- **L10-10 data 面の認証前 in-flight bound。** WP-8a の F-2 として記録し、**WP-8c で閉じた** — 両 peer とも concurrency slot を認証の前に取り、`requests_per_minute` は認証後に課金する。MitateDB の `HttpService` は fail-closed になった (U-18)。**閉止 (2026-09-09)。**
- **L10-11 role の `CONNECTION LIMIT` と pool 合計の不整合。** WP-4e が実測で露出させ (新規 pool の初回接続が hard に拒否される)、**WP-4f が新 migration と F-16 で閉じた (U-19)。** **計画文書 §8 の R-31 のうち connection の部分はここで閉じ、残り (プロセス数・応答サイズ・DB 容量・監査保存量) はフェーズ11 である。閉止 (2026-09-10、部分)。**
- **L10-12 readiness probe が control 面の認証前 window を消費する。** r2db の socket adapter が起動時に 2 回 probe しており、`get_control_capabilities` が Bearer 抽出より前に `check_rate()` を呼ぶため、使い捨て control app の rate window が probe だけで 1 消費されていた (200 枠中 199 回で早期 `LIMIT_EXCEEDED`)。MitateDB の同等クラスは初めから 1 回 probe だった。**adapter 側を 1 回に揃えて閉じた (製品コードは不変)。閉止 (2026-09-09)。**
- **L10-13 `.venv` の `.pth` が main checkout を指す。** worktree から起動した subprocess (C-26 の composition root、`ops` CLI) が main checkout の src を import する。**環境は変えず、`PYTHONPATH` を明示する運用条件として記録した** (`OPERATING_CONDITIONS.md` §2)。**開いたまま (記録)。**
- **L10-14 待機ループの相互デッドロック。** `ps ... | grep pytest` 形は自分自身に一致して永久待機する — 本フェーズでも 1 本が丸 1 日超残った。**併せて、`ps -eo comm=,args=` 形はこの開発機では `comm` がパス切り詰めのため一致せず即抜けする** (WP-4f / WP-4g の逸脱報告)。**両方を運用条件に記録した。開いたまま (記録)。**
- **L10-15 CI の集計行が課金上限で未取得。** 本フェーズの版ではどの job も走っていない。**GitHub 復旧後に main の先頭で 1 回 run を取り、集計行と `conformance` job の所要を記録する (L10-1 と対)。開いたまま (実測待ち)。**
- **L10-16 `_ISOMORPHIC_TARGETS` に未登録の同名 helper がある。** pair-closing `0d3d941` で登録したのは 8 行 (97 → 105)。**未登録は launcher (`real_server_<peer>.py`) の同名 helper 群、F-16 の `check_role_connection_limits` 系、WP-8c の `_parse_handler` / `_authenticate_call_nodes` 系である。登録は Class D の pair-closing commit で行う。開いたまま (作業待ち)。** **【閉止 2026-09-10、記録 2026-09-13 (v1.8)】** pair-closing `2152c94`（実装 `fe2b105`）が 105 → **137** 行へ拡張した。登録したのは C-26 launcher の同名 helper 23 件、F-16 の同型な純粋 Python 部分 7 件（`_table_owner`、`_roles_with_table_privilege`、3 定数、`_f16_message`）、WP-8c の `_parse_handler` / `_authenticate_call_nodes` 2 件である。`check_role_connection_limits` 本体、残りの launcher method、WP-8c の同名 `test_*`、`role_pool_size`、WP-6d-i lock helper は、application identity・SQL column・fixture／実装形などの**実在する peer 差**があるため登録しない、と table 自身のコメントで明示した。両 peer の table 全内容を pin するテストは 137 行を assert し、行を1件落とす変異と片側の1文字差分がいずれも赤になることを実測した。`r2db-api/tests` 1251、`MitateDB-api/tests` 1084、C-26 17、F-16 2 passed。**閉止。**
- **L10-17 WP-6c の軽微な残 4 件** (再レビューが「差し戻し不要」と判定した N1〜N4 — lock dir の置き場、F3 テストの検査範囲、`os.environ` の扱い、`_control_env` の並び)。**挙動に影響しない。開いたまま (記録)。**
- **L10-18 WP-8c の F-6 — slot の持ち回りの実現差。** 両 peer とも認証前に slot を取るが、r2db は `DataService` 内部の `acquire_concurrency_slot`、MitateDB は `HttpService` への明示注入である。**同じ必須の安全結果を platform ごとの統制で満たす形であり (`CLAUDE.md`)、実現差そのものは共通条件では観測できない。開いたまま (記録)。**
- **L10-19 conformance HTTP adapter の `_SURFACES` 定数化。** `_surfaces_value` を同型登録するために MitateDB 側の inline dict を r2db と同じ module 定数に揃えた (値は不変)。**「同型登録のために片側を寄せる」判断は計画文書 §8 の R-32 (検証 seam と同型性の分離) の材料である。開いたまま (記録)。**

### 10.5 L10-17〜L10-19 の照合と処置 (**v1.9、2026-09-13 の追記**)

**上の §10.4 の起票行は当時の記録として書き換えない。** 現行 main `2947dfc` で、実装コミット、レビュー是正、現行ソース、および計画文書 §8 を再照合した処置は次のとおりである。

- **L10-17 — 閉止。** WP-6c は `5477bb1` の後、レビュー是正 `7cc7b07` で重大指摘 F1〜F9 を反映し、再レビューは「新規の重大指摘なし」であった (§11.8)。残った N1〜N4 は、(1) peer 別の `tempfile.gettempdir()` 配下 lock directory、(2) F3 の障害注入テストが代表的な途中失敗を検査する範囲、(3) subprocess 生成時だけ peer 接頭辞を `os.environ` から除き `finally` で戻す実装、(4) `_control_env` の dict 挿入順、の実装メモである。現行実装では lock 名が peer 接頭辞で分離され、途中失敗は `start()` 全体の `try` / `stop()` と DB・role・process・port・temp directory の残骸検査で覆われ、環境操作は subprocess の env copy 時に限定され、dict 順は env の意味に影響しない。**公開契約・製品実装の欠陥、または将来 WP の着手条件を示すものではないため、追加作業なしで閉止する。** 後日、具体的な再現不具合が得られた場合は新しい台帳項目として起票する。
- **L10-18 — 閉止。** WP-8c `72c8193` と統合 `9361f1b` の現行実装は、両 peer で byte bound → concurrency slot → authentication の順を固定し、slot を要求全体で保持する。r2db が `DataService.acquire_concurrency_slot` を所有し、MitateDB が同じ limit holder と bound を `HttpService` へ必須注入する差は、いずれも認証前の同じ必須安全結果を fail-closed で実現する platform 固有の統制である。その安全結果は peer-local の pre-auth concurrency テストと socket plug の C-05 で観測済みであり、**所有位置まで共通化することは Security Invariants の要求ではない。F-6 は欠陥ではなく受容済みの実現差として、追加作業なしで閉止する。**
- **L10-19 — フェーズ11へ持越し。** pair-closing `0d3d941` が MitateDB HTTP adapter の inline dict を module 定数 `_SURFACES` へ移した変更は値と対外挙動を変えておらず、`_surfaces_value` は両 peer で `_ISOMORPHIC_TARGETS` に登録され、137 行 pin と差分検査が維持されている。したがって当該変更の追加修正は要らない。一方、「同型性 table に登録するために片 peer の本文の形を寄せた」という開発プロセス上の論点は残る。**これを L10 の局所修正としては閉じ、計画文書 §8 の R-32「検証 seam と同型性の分離」の具体的な入力としてフェーズ11 (開発プロセス衛生 v2) へ持ち越す。**

### 10.6 L10-9 の照合と処置 (**v1.10、2026-09-13 の追記**)

**上の §10.4 の起票行は当時の記録として書き換えない。** 現行 main `bf38964` で、U-10 / U-16、WP-7 の §11.10、WP-8b の安全性裁定、および計画文書 §8 の R-31 を再照合した。

- **L10-9 — 追加実装なしで閉止。** WP-7 の所定の判定材料 `K=3 p50 / K=1 p50` は、MitateDB-api-socket の query / mutate / batch / cross_entity でそれぞれ **1.71 / 1.68 / 1.96 / 1.72** であり、全操作で起票時の判定線 `> 2` を超えない。したがって、同一 Application 内の並行度を上げるために cell 保持の `_runtime` / `_developer` を要求スコープの pool 貸出しへ置き換える実需は、本計測からは実証されていない。
- **安全性の未達は残っていない。** WP-8b は、threadpool 委譲下で共有接続を lock 外で使う回帰を実測した上で案 A を採用し、`_limit_gate` の slot 内で `ApplicationCell._lock` が lookup → pass-1 → pass-2 全体を覆う。これにより同一 Application は直列化され、1 要求内の lock → 照会 → 実行 → 記録が同じ接続・同じトランザクションで閉じる。要求スコープ接続は、この安全結果に必要な未実施統制ではない。
- **R-31 に重複して持ち越さない。** R-31 の connection 部分は L10-11 の role `CONNECTION LIMIT`、pool 合計、F-16 の fail-fast ですでに閉止されている。R-31 でフェーズ11へ残すのは、同行に明記済みの **プロセス数・rate・応答サイズ・DB 容量・監査保存量** である。将来、同一 Application 内の並行性が具体的なボトルネックとして実測された場合は、L10-9 を再開せず、当時の要求・負荷・安全条件を持つ新しい台帳項目として起票する。

**この閉止は、性能判定と既存の安全結果の記録確定であり、コード、契約、Security Invariants、conformance 条件、配備を変更しない。**

### 10.7 L10-20 の起票 (**v1.11、2026-09-14 の追記**)

**上の §10.4〜§10.6 の行は当時の記録として書き換えない。**

- **L10-20 (計画文書 §8 の R-37、巨大モジュールの段階的リファクタリングの追跡 ID)**: **本項は追跡 ID であり、何を義務付けるかを本書では定めない。** WP ごとの必須証拠・変異・完了ゲートは設計 `docs/design/MODULE_REFACT_ARCHITECTURE_V1.md` §5、実施・レビュー・記録の規律は同 §6、着手・停止条件は同 §7 を正本とする (観測対象は同 §0)。**【追記 2026-09-14】** 同設計 WP-1 相当の片側 leaf 抽出 6 件 (`f8d71a0`〜`2a20d33`) が同日 main に入り、その逸脱 (着手条件の未充足、peer suite の未実行による L1 details AST scan の赤、走査の穴、経緯コメントの喪失) を branch `r37-wp1-fix` で是正し、同日の監督 root suite ゲート (`3336 passed`) を通して main へ統合した。記録の正本は同設計 v1.2 §8。**開いたまま (R-37 の WP-2 以降が残る)。**

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

**未着手** (設計 v1.1 時点。完了ゲートの実測値・WP ごとの記録・性能差分は WP-9 で記入する)。 **【訂正註 2026-09-08 (v1.4)。上の 1 文は設計 v1.1 時点の記述であり、消さずに残す】** **以降の実施は §11.4 以下に記録する。**

### 11.4 WP-6d-i (D-13、計画文書 §8 の R-24) — 実装済み (2026-09-08。**main 未マージ**)

- **コミット**: branch `phase10-wp6d` の実装 `21cc8fb`、**Opus のコードレビュー 1 巡目の判定は「accept with fixes」**であり是正コミットは `6a3453d`、**R-34 の branch `phase10-r34` との統合が `685ebfa`** である。**再レビュー実施中。** **main へのマージは `4e1020a` (WP-6d-i + R-34 + R-35 の束) + 直後の pin 修正 `ee80c97` (`test_limit_class_vocabulary.py` の `ResourceLimitError` 呼び出し数 33 → 35。F2 の 2 箇所分。ゲート 3 が検出し、ゲート 4 で再確認) である。**
- **実現の形 (peer ごとに違う理由を含む)・テスト・変異の実測・レビュー指摘 F1〜F8 は §3 D-13 の実施註に置いた。本節では再掲しない。**
- **実測の要点**: 変異 5 種で赤 — **key lock 除去で両 peer `2 failed`**、**件数 lock 除去で両 peer `1 failed`**、**in-memory lock 除去で両 peer `3 failed`**、**unlock を `finally` の外へ出すと `still holds 2 advisory lock(s)`**、**MitateDB の 2 つの commit 除去で回収の回帰が赤**。**監督の raw-SQL 競合スクリプトを新しい SQL で再実行し、25 反復で二重実行 0 件。** **是正前の peer suite は r2db `1175 passed`、MitateDB `998 passed`。**
- **性能差分は完了ゲート (WP-9) で記録する** (§9 の 15)。**6d-ii (C-27) は未着手である。**

### 11.5 R-34 の実施と、その過程で監督が犯した誤り (2026-09-08)

- **R-34 の実施**: branch `phase10-r34` の **`12a7bd7`** — **両 peer の `tests/test_audit_query.py` の `_run_delayed_tx_vector` を Event 同期に改めた** (writer が INSERT の後に signal し、probe は **INSERT 時刻から `lag_s + 0.2`** 待ってから走り、**tx が open であることを assert** し、**`finally` で writer を解放する**)。**変異 (INSERT の直後に即時 commit) で両 peer `2 failed`。** **ファイルごとに 3 回連続緑** — **r2db `75 passed`、MitateDB `62 passed`。**
- **監督の過程誤り (記録。R-14 に従い消さない)**: **`12a7bd7` は、実装担当がまだ作業中の worktree で監督が `git add -A` を使ったため、変異検査用の scratch 複製 `r2db-api/tests/test_zzr34mutationscratch_audit_query.py` を巻き込んで commit した。** **`5a59002` で当該ファイルを削除して是正した。** **再発防止として `docs/work-orders/OPERATING_CONDITIONS.md` §1.1 に条項 12a を足した** — **「監督は `git add -A` を使わず、`git status --short` を見て報告に列挙されたパスだけを add する。実装担当が結合された worktree で作業中は commit しない」**。
- **R-34 は WP-6d-i のゲート束で main へ入る** (`685ebfa` が `phase10-wp6d` と統合済み)。**閉止行は計画文書 §8 に書いた。**

### 11.6 WP-R35 (D-15、計画文書 §8 の R-35) — 実施中 (2026-09-08)

- **worktree / branch `phase10-r35`。コミットは `46b081a` + `7ead163` である。**
- **内容**: 両 peer の nullable 違反走査の `LOCK TABLE ... IN SHARE MODE` を **`SHARE ROW EXCLUSIVE`** に改め、**決定的な 2 スレッドテスト**を添える。**根拠と壊し方は §3 D-15 である。**
- **出所**: **WP-6d-i のコードレビュー** (§11.4)。**フェーズ9 R-2 の前例確認 (§5 U-7 が課した報告義務) が露出させた既存の欠陥であり、本フェーズの新規変更が作った欠陥ではない。**

### 11.7 全 WP のコミットと束ゲート (**v1.6**。WP-9、2026-09-10)

**集計行はすべて監督がリポジトリルートで単独実行した `./.venv/bin/python -m pytest -q -n 5 --dist loadgroup` の逐語である。`failed` / `skipped` / `xfailed` / `error` はいずれの束ゲートでも集計行に現れていない。**

| 束 | main へのマージ | 含む WP (branch の実装コミット) | root suite の集計行 (逐語) |
|---|---|---|---|
| 1 | `bce2598` | WP-0 (`c3d9fc9`) | 文書と README のみ |
| 2 | `7d8bb0f` / `c9a937a` | WP-1a (`f38716b`)、WP-2 (`79958a7`) | `2807 passed in 184.77s (0:03:04)` |
| 3 | `1cd2c39` / `91b3f0f` / `7c53652` / `b16afdd` | WP-1b (L10 族の登録)、CI `tools-tests` job、設計 v1.2、作業指示書 v1.0 | `2807 passed in 197.72s (0:03:17)` |
| 4 | `6055c69` / `3d7f823` | WP-3 (`8d39260`)、WP-5a (`654e23e`) | `2842 passed in 231.02s (0:03:51)` |
| 5 | `0cec2b3` / `25312f4` / `ec15c74` / `4f2fb56` | WP-5a 追補 (`73adbda`、U-9)、WP-3 follow-up (`ea237e5`、U-12)、WP-1c (`5944013` → `2431e93`)、外部レビュー 2 の記録 (`86269c0` / `fd45f19`) | ゲート 1 は `1 failed, 2852 passed` (赤は R-34 の timing テスト 1 件。§11.5) |
| 6 | `4e1020a` + `ee80c97` / `c1ce2b4` | WP-6d-i (`21cc8fb` → `6a3453d` → `d3308c7` → `968884f`)、R-34 (`12a7bd7` + `5a59002`)、R-35 (`46b081a` + `7ead163`)、記録 (`10dd54c` / `ca5d982` / `68f31a8` / `3c951d2`) | §11.4〜§11.6 |
| 7 | `8bf21a2` (+ `318fd3e`) | WP-8a (`ae9998f`)、CI の 3.12 / `tally-consistency` を main 限定に | `2887 passed in 355.87s (0:05:55)` |
| 8 | `a3a35af` | WP-6a (`ff229c7` + `ab32853`)、WP-6b (`d872e03` + `748bca3`)、**pair-closing** (`b24e15f` / `26535a8` / `0d3d941` / `9dad681`) | `2964 passed in 250.73s (0:04:10)` |
| 9 | `b1d9001` / `453e711` | 設計 v1.5 + 作業指示書 v1.3 (`eaa9cc8`、`[skip ci]`)、WP-8b (`5f263ce` → `bfea09d`、main 統合 `ab1f784` / `a587ca4`) | `2975 passed in 376.68s (0:06:16)` |
| 10 | `c387b32` | WP-6c (`5477bb1` → `7cc7b07`) | `2990 passed in 237.57s (0:03:57)` |
| 11 | `9361f1b` | WP-4a (`6b20c88`)、WP-4b (`c473575`)、統合 (`4184516` / `16df7ad`)、WP-4c (`0cc7db0`)、WP-4d (`93fb9ca`)、WP-4e (`3057a98`)、WP-4f (`5e1eeac` + `2d90eca`)、WP-8c (`72c8193`、統合 `0f7951f`)、WP-4g (`91af283`)、統合レビュー是正 (`8ea0ff1`)、main 取り込み (`a571853` / `2c37fdc` / `e3211f6`) | `3294 passed in 266.04s (0:04:26)` |
| 12 | `4a90cf4` | WP-5b (`CONDITIONS.md` の C-03 / C-05 / C-09 / C-15 / C-19 / C-25 を 6 plug の現実に改訂) | `959 passed in 146.91s (0:02:26)` (`conformance-tests`) |
| 13 | `ff8d232` | WP-7 (`tools/perf_baseline.py` の `--concurrency K`、socket transport 列、K=1 / K=3 の実測) | `§11.10 の PERF 行 (逐語)` |
| 14 | (本記録のマージ。ハッシュは第 17 次ハンドオーバー §1) | WP-9 (記録・閉止・ハンドオーバー) | ``3294 passed in 379.82s (0:06:19)` (単独 root suite、main `2152c94` + 本記録の作業ツリー、failed 0 / skipped 0 / xfailed 0、`pg_database` 差分 0 (19 → 19)、nginx 残骸 0、収集 3294 = `COLLECTION_FLOOR` 3294)` |

| **15** (**追記 2026-09-10 (v1.7)。上の 14 行は書き換えていない**) | `2455f96` (`[skip ci]`) | **WP-6d-ii** (`d97de35` → レビュー是正 `8425ef4` → main 取り込み `05bc548`) | `3326 passed` (**単独 root suite。§9.1 の項目 1 の追記が正本**) |

**契約 3 複製の sha256 は束 4 (WP-5a) 以降動いていない** — 束 5 の追補 `73adbda` は 1.8.0 の条件付き義務を足したが版は動かさず、束 8 の pair-closing は peer 側の宣言だけを動かした。

### 11.8 WP ごとの記録 (実装 = Sonnet、レビュー = Opus、コミット = 監督。**報告・レビュー・裁定文は監督保管**)

- **WP-3 (`6055c69`) — レビュー 2 巡、指摘 10 件 (F-1〜F-10)。** 主要: 隔離 surface が `_surfaces_value()` を通ることの pin、**port を先に予約して起動だけ遅延する形** (これが無いと `_surfaces_value()` が composition 時点で実 URL を返せない)、`_reset_surface_state` hook、残骸検査の `ports.json` listener 突合、`_hold_in_flight_via_http_requests` の `_build_client` 経由化。**変異**: `wait_until_ready` の `status < 500` → `< 600` で `Failed: DID NOT RAISE HarnessStartupError`。
- **WP-4a / WP-4b (`6b20c88` / `c473575`) — 報告 2 巡。** WP-4a は疑義 2 拡張を撤去 (**U-22** (3)。629 → 583 行、`grep -n "_is_isolated_copy\|is_bound\|data-concurrent"` 0 件)。集計行 `29 passed in 11.22s` / `57 passed in 260.24s (0:04:20)` / `1169 passed in 95.28s (0:01:35)`。**WP-4b の 4 blocker が本フェーズの進路を変えた** — (3) が WP-8 を計測前に発動させ、(4) が C-03 / C-15 の honest limits を書き換えた (**U-14**)。
- **WP-4c / WP-4d (`0cc7db0` / `93fb9ca`) — 各 1 巡。** **WP-4c の変異 4 本 (逐語)**: 代理指標へ戻すと `expected exactly 50 successful inserts before LIMIT_EXCEEDED (bound=50, already_consumed=0), got 49`;二重 wrap を戻すと `RuntimeError: WP-5 application-residue-guard teardown failed to deprovision ...`;wire 拒否枝を body vector へ広げると `WIRE_CARRIED_IDENTIFIER_POSITIONS must not overlap the body-carried positions ...`;`_AppDispatch` を除くと `15 failed, 876 passed, 49 errors in 188.82s`。**WP-4d は C-06 / C-16 の 6 plug pin を更新し、L10-12 を特定して adapter 側で閉じた。変異**: `strict-branch adapter set drifted ... Extra items in the left set: 'r2db-api-socket'`。
- **WP-4e / WP-4f / WP-4g (`3057a98` / `5e1eeac` + `2d90eca` / `91af283`) — 各 1 巡。** **WP-4e は pool を宣言 concurrency から導出し、同時に「control 面の pool を上げても直らない」ことを計測で示して上げる側を revert した** (隠さず範囲外として報告)。変異は `expected 0 AUTH_STATE_UNAVAILABLE denials at in-flight == declared concurrency, got: [...]`。**WP-4f の変異は 4 箇所とも `Failed: DID NOT RAISE RuntimeError`**、集計行 `1235 passed in 78.50s (0:01:18)` / `1067 passed in 80.31s (0:01:20)` / `940 passed in 167.17s (0:02:47)`。**WP-4g は MitateDB の adapter を fail-closed 契約へ配線し、両 launcher が role-limit migration を適用していない欠落も直した** (修正前は C-26 の `lifecycle` を使う既存テストが素の状態で F-16 に落ちていた)。**変異**: 起動時 F-16 を外すと両 peer とも `subprocess.TimeoutExpired: ... timed out after 30 seconds`。集計行 `957 passed in 167.31s (0:02:47)` / `1248 passed in 38.96s` / `1081 passed in 45.11s`。
- **WP-4 統合レビュー (`8ea0ff1`) — 1 巡、指摘 9 件 (H-1 / M-1 / M-2 / L-1〜L-6)。** H-1 と M-1 は実欠陥 (§11.9)。**変異**: `WHERE` 節を外すと `ERROR:  null values cannot be formatted as an SQL identifier`;`max` を上書き代入へ戻すと `Failed: DID NOT RAISE PlatformDeclarationError`;`httpx.HTTPError` へ戻すと `an unreachable peer (ConnectError) must never be classified as a wire rejection ...`。**是正後**: `1251 passed in 101.20s (0:01:41)` / `1084 passed in 91.52s (0:01:31)` / `959 passed in 160.91s (0:02:40)`。
- **WP-5b (2026-09-10) — 1 巡。** **改訂は 4 行の見込みが 6 行になった** (C-03 / C-05 / C-09 / C-15 / C-19 / C-25)。**変異 (完了条件 12)**: `cell(s) in .../conformance-tests/CONDITIONS.md exceed the 3000-character cap (id, column, length): [('C-19', 'Status', 3332)]`。**完了条件 11 の変異は赤にならなかった** — §9.1 の 11 に開示。集計行 `959 passed in 146.91s (0:02:26)`。
- **WP-7 (`ff8d232`) — 1 巡。** **`tools/perf_baseline.py` に `--concurrency K` を足した** — **K 本の要求を adapter 自身の loop 上の 1 回の `asyncio.gather` で同時発行し、K=1 も同じ経路を通る** (設計 §5 の裁定 9)。**既定は `--n 100 --warmup 10`、K ∈ {1, 3}。** **変異 5 件**: `gather` を逐次 `await` に戻す (K=3 / K=1 の両経路)、既定を 200/20 に戻す、`backend_calls` 列名を `calls` に変える、`_classify_plug` の fallback を広げる。**PERF 行は 21 行 × 2 (K=1 / K=3) であり、socket transport 列が初めて入った (L8-5)。** **§9.1 の 6 / 15 への記入は監督が単独実行の値で行う。**
- **WP-6a / WP-6b + pair-closing (`ff229c7` / `d872e03` / `0d3d941`) — 各 2 巡。** **1 巡目の F1 が deadlock を実 PG で実証し、U-15 を導いた** (§11.9)。**F2 / F3 は「テストの空振り」** — 完了条件 4 のテストは tx A が lock を保持し tx B が素の INSERT を撃つ形で決して deadlock せず、control 面の写像は明示注入で `.control` → `.data` の取り違え変異がどのテストでも赤にならなかった。**是正は `threading.Barrier(2)` の同時実行と `build_control_app` を通す実 HTTP テストである。** **変異 (逐語)**: `_take_bound_advisory_lock` の no-op 化で r2db `4 failed in 1.12s`、MitateDB `assert 2 == 1` (2 本);plane 取り違えで両 peer とも `assert 'enforced' == 'deployment_required'`。**pair-closing は 4 箇所の版フリップ、peer 側 pin 14 箇所、`_ISOMORPHIC_TARGETS` 97 → 105 行 (`ProcessCeilings` / `validate_process_ceilings_value` / `_f15_shape_message` / `_f15_value_message` / `_take_bound_advisory_lock` / `_build_client` / `_surfaces_value` / `_reset_surface_state`。後ろ 3 行は同機構が `conformance/` 配下も対象にできることを示した)。** **`cmd_declare_process_ceilings` は登録しなかった** — 正規化後も statement 順・例外処理の形・再起動メッセージが実際に違い、正規化の穴ではなく本物の差だった。**変異**: 表から 1 行落とすと `..._pinned_to_its_current_105_rows` が赤;data 面だけ 1.7.0 に戻すと `data-plane declares contract_version '1.7.0' but the control-plane document declares '1.8.0'`。
- **WP-6c (`5477bb1` → `7cc7b07`) — レビュー 2 巡 (1 巡目「差し戻し (F1 必須)」、2 巡目「反映済 / 新規の重大指摘なし」)。** 軽微 4 件は L10-17。**変異**: 到達不能 URL の宣言で `urllib.error.URLError: <urlopen error [Errno 61] Connection refused>`;`restart()` の実再起動を省くと `ceiling=2 data requests_per_minute was 'enforced', expected 'deployment_required'`。集計行 `15 passed in 7.52s` (`-k c26`) / `698 passed in 136.62s (0:02:16)`。
- **WP-8a (`ae9998f`) — 1 巡 + 是正 (F-1〜F-7)。** F-1 は実欠陥 (§11.9)。**F-4 は race 依存の pin を決定的な AST pin へ置き換えさせ、3 種の変異がすべて赤になった** (`the concurrency check ... is not lexically inside` 等)。**F-5 は被覆の穴** — 変異前は `post_query` / `post_mutate` / `post_cross_entity_mutate` の委譲を外しても新テスト 5 本が全緑だった (D-8 (2) の判定が対象にした経路が無防備だった)。集計行 `1186 passed in 36.86s` / `683 passed in 126.98s`。
- **WP-8b (`5f263ce` + `bfea09d`) — レビュー 2 巡。** 1 巡目が致命 (共有 `_developer` 接続の交錯) を probe で実証し U-16 を導いた (§11.9)。**変異**: lock 一本化を戻すと `the second, concurrent request completed WHILE the first was still holding the idempotency lock` (`3 failed, 8 deselected in 1.05s`)。集計行 `1021 passed in 83.53s (0:01:23)` / `683 passed in 104.69s (0:01:44)`。
- **WP-8c (`72c8193`) — 1 巡 + 是正 (中 3 / 低 4)。変異 5 本**: 解放漏れで r2db `assert 429 == 401` / `assert 429 == 400`、MitateDB `assert 413 == 400`;fail-closed で `RuntimeError: HttpService requires both limit_holder and max_concurrency...`;拒否順序で両 peer `assert 'requests_per_minute' == 'concurrency'`;AST 検査で `does not contain a real _authenticate call... assert []`。**fail-closed 化が conformance adapter の構築を壊した状態を隠さずに報告し、統合 branch の WP-4g で配線して解いた。**

**変異を持たない完了条件の逐語記録** (§9 の 11): **契約 3 複製の sha256 (§11.7)、`composition_roots` の件数と `adapters` 6 件 (§9.1 の 7 / 8 (e))、`_ISOMORPHIC_TARGETS` の 105 行 (本節の pair-closing)。**

### 11.9 レビューが見つけた実欠陥 6 件 (**いずれも「指摘 → 是正 → 変異で赤」を実測した**)

**本節は「実装は正しいがテストが無い」ではなく、実装そのものが誤っていた件だけを並べる。**

1. **件数 bound の lock が deadlock する** (WP-6a、F1)。`LOCK TABLE ... IN SHARE MODE` → count → INSERT は SHARE 同士が衝突しないので 2 writer が互いの INSERT を待つ。**実測は `{1: 'DeadlockDetected', 2: 'OK'}`。是正は同名 helper の `pg_advisory_xact_lock`。出所は監督の発注文の前例誤引用である (U-15)。**
2. **pass-1 が cell 共有の単一接続を lock の外で使い、他要求の commit / rollback がトランザクションを奪う** (WP-8b)。**probe は `probe_race_visible_before_A_commit: 1` (委譲前の main は 0) — 本 WP が入れた回帰である。** 壊れ方は (i) 監査 pre-commit 行なしに DDL が確定する fail-closed の破れ、(ii) 他要求の rollback が確定済みと返した変更を捨てる、(iii) 無関係な要求に `VALIDATION_FAILED` が返る、(iv) 1 要求内の 2 回の catalog 読みが別スナップショットになる。**是正は案 A (U-16)。**
3. **role pool の容量が固定 4 で、宣言 `concurrency` (既定 32) に届く前に涸れる** (WP-8a、F-1)。**threadpool 委譲で初めて実並行になり露出した。** 変異で `AssertionError: ... [200,200,200,200,503,503]`。
4. **role の `CONNECTION LIMIT` が実 pool 構成に対して不足していた** (WP-4e / WP-4f)。新規 pool の初回接続が hard に拒否される。**是正は新 migration + F-16 の起動時 fail-fast (U-19)。**
5. **readiness probe が control 面の認証前 rate window を消費していた** (WP-4d)。r2db の socket adapter が 2 回 probe し、`check_rate()` が Bearer 抽出より前に走るため window が 1 消費された状態で始まっていた。**是正は adapter 側の 1 回 probe への統一 (製品コードは不変)。**
6. **migration 0013 が「登録のみ」の application 行 (role 名 NULL) で必ず失敗し、migration 全体が rollback する** (統合レビュー H-1)。**`register_application` を使った配備では 0013 が一切適用できず、その状態で F-16 が入ると両プロセスが起動不能になる。MitateDB 側の同型 migration は正しく除外していた — 4 箇所のうち 1 箇所の取りこぼしであり、peer 対称性がそこで崩れていた。**

**共通する形**: **6 件のうち 3 件 (1・3・5) は「宣言した bound が実配備で到達不能」であり、実 socket と実並行が入って初めて見えた。** **2 件 (2・6) は「同じ変更の中で peer の片側だけが正しかった」形である。** **1 件 (1) は監督の発注文の誤りが直接の原因である。**

### 11.10 PERF 行 (WP-7、main `ff8d232`。逐語。K=1 の第 1 run と K=3 の第 1 run。2 run の p50 差はすべて 30% 未満)

```
PERFRUN host=Darwin/arm64 python=3.11.15 commit=9361f1b-dirty date=2026-09-10
PERF peer=r2db-api plug=r2db-api transport=in-process op=query n=100 p50_ms=0.126 p95_ms=0.132 backend_calls=1.00 concurrency=1
PERF peer=r2db-api plug=r2db-api transport=in-process op=mutate n=100 p50_ms=0.174 p95_ms=0.211 backend_calls=1.00 concurrency=1
PERF peer=r2db-api plug=r2db-api transport=in-process op=batch n=100 p50_ms=0.491 p95_ms=0.682 backend_calls=1.00 concurrency=1
PERF peer=MitateDB-api plug=MitateDB-api transport=in-process op=query n=100 p50_ms=0.121 p95_ms=0.125 backend_calls=11.00 concurrency=1
PERF peer=MitateDB-api plug=MitateDB-api transport=in-process op=mutate n=100 p50_ms=0.100 p95_ms=0.104 backend_calls=7.00 concurrency=1
PERF peer=MitateDB-api plug=MitateDB-api transport=in-process op=batch n=100 p50_ms=0.164 p95_ms=0.176 backend_calls=37.00 concurrency=1
PERF peer=MitateDB-api plug=MitateDB-api transport=in-process op=cross_entity n=100 p50_ms=0.127 p95_ms=0.133 backend_calls=16.00 concurrency=1
PERF peer=r2db-api plug=r2db-api-http transport=asgi-inprocess op=query n=100 p50_ms=4.650 p95_ms=5.515 backend_calls=14.00 concurrency=1
PERF peer=r2db-api plug=r2db-api-http transport=asgi-inprocess op=mutate n=100 p50_ms=3.871 p95_ms=5.435 backend_calls=15.00 concurrency=1
PERF peer=r2db-api plug=r2db-api-http transport=asgi-inprocess op=batch n=100 p50_ms=4.686 p95_ms=5.233 backend_calls=19.00 concurrency=1
PERF peer=MitateDB-api plug=MitateDB-api-http transport=asgi-inprocess op=query n=100 p50_ms=5.385 p95_ms=9.157 backend_calls=13.00 concurrency=1
PERF peer=MitateDB-api plug=MitateDB-api-http transport=asgi-inprocess op=mutate n=100 p50_ms=5.523 p95_ms=6.367 backend_calls=9.00 concurrency=1
PERF peer=MitateDB-api plug=MitateDB-api-http transport=asgi-inprocess op=batch n=100 p50_ms=5.381 p95_ms=7.995 backend_calls=29.00 concurrency=1
PERF peer=MitateDB-api plug=MitateDB-api-http transport=asgi-inprocess op=cross_entity n=100 p50_ms=5.823 p95_ms=7.614 backend_calls=14.00 concurrency=1
PERF peer=r2db-api plug=r2db-api-socket transport=socket op=query n=100 p50_ms=8.523 p95_ms=9.142 backend_calls=14.00 concurrency=1
PERF peer=r2db-api plug=r2db-api-socket transport=socket op=mutate n=100 p50_ms=8.805 p95_ms=10.054 backend_calls=15.00 concurrency=1
PERF peer=r2db-api plug=r2db-api-socket transport=socket op=batch n=100 p50_ms=8.377 p95_ms=11.890 backend_calls=19.00 concurrency=1
PERF peer=MitateDB-api plug=MitateDB-api-socket transport=socket op=query n=100 p50_ms=10.870 p95_ms=17.404 backend_calls=13.00 concurrency=1
PERF peer=MitateDB-api plug=MitateDB-api-socket transport=socket op=mutate n=100 p50_ms=10.978 p95_ms=16.096 backend_calls=9.00 concurrency=1
PERF peer=MitateDB-api plug=MitateDB-api-socket transport=socket op=batch n=100 p50_ms=9.934 p95_ms=14.345 backend_calls=29.00 concurrency=1
PERF peer=MitateDB-api plug=MitateDB-api-socket transport=socket op=cross_entity n=100 p50_ms=10.139 p95_ms=13.654 backend_calls=14.00 concurrency=1
```

socket 2 plug の K=3 (第 1 run):

```
PERFRUN host=Darwin/arm64 python=3.11.15 commit=9361f1b-dirty date=2026-09-10
PERF peer=r2db-api plug=r2db-api-socket transport=socket op=query n=100 p50_ms=18.162 p95_ms=19.866 backend_calls=14.00 concurrency=3
PERF peer=r2db-api plug=r2db-api-socket transport=socket op=mutate n=100 p50_ms=17.864 p95_ms=19.404 backend_calls=15.00 concurrency=3
PERF peer=r2db-api plug=r2db-api-socket transport=socket op=batch n=100 p50_ms=18.536 p95_ms=25.200 backend_calls=19.01 concurrency=3
PERF peer=MitateDB-api plug=MitateDB-api-socket transport=socket op=query n=100 p50_ms=18.632 p95_ms=32.198 backend_calls=13.00 concurrency=3
PERF peer=MitateDB-api plug=MitateDB-api-socket transport=socket op=mutate n=100 p50_ms=18.458 p95_ms=23.489 backend_calls=9.00 concurrency=3
PERF peer=MitateDB-api plug=MitateDB-api-socket transport=socket op=batch n=100 p50_ms=19.460 p95_ms=22.324 backend_calls=29.00 concurrency=3
PERF peer=MitateDB-api plug=MitateDB-api-socket transport=socket op=cross_entity n=100 p50_ms=17.455 p95_ms=20.472 backend_calls=14.00 concurrency=3
```

判定規則 (K=3 p50 / K=1 p50 > 2):

| plug | op | K=1 p50 ms | K=3 p50 ms | 比 |
|---|---|---|---|---|
| r2db-api-socket | query | 8.523 | 18.162 | 2.13 |
| r2db-api-socket | mutate | 8.805 | 17.864 | 2.03 |
| r2db-api-socket | batch | 8.377 | 18.536 | 2.21 |
| MitateDB-api-socket | query | 10.870 | 18.632 | 1.71 |
| MitateDB-api-socket | mutate | 10.978 | 18.458 | 1.68 |
| MitateDB-api-socket | batch | 9.934 | 19.460 | 1.96 |
| MitateDB-api-socket | cross_entity | 10.139 | 17.455 | 1.72 |

(r2db-api-socket は 2 倍超、MitateDB-api-socket は 2 倍未満。WP-8 は実施済みのため、残る直列化要因は L10-9 に記録 — フェーズ11 の判断材料。)

### 11.11 WP-6d-ii (D-13、§5 U-8、計画文書 §8 の R-24) — 完了 (**v1.7**。2026-09-10)

**実装 = Sonnet、レビュー = Opus、コミットとマージ = 監督。報告・レビュー・裁定文は監督保管。** **確定形と変異の逐語は §3 D-13 の「実施註 (6d-ii)」が正本であり、本節はそれを再導出しない。**

- **branch `phase10-wp6dii`。`d97de35` (実装) → `8425ef4` (レビュー是正、指摘 F1〜F7) → `05bc548` (main 取り込み)。main へのマージは `2455f96` (`[skip ci]`)。レビューは 1 巡、判定は「accept with fixes」。**
- **成果物**: **port v1.15 の hook `hold_after_idempotency_lookup(session, idempotency_key)`** (`conformance-tests/adapter.py` の abstract method 1 個と非 normative handle `IdempotencyHold`。**契約文は D-13 (1) から逐語複製**)、**4 adapter の実現** (socket 2 plug は継承。**両 peer の `src/` と socket adapter 2 本には触っていない**)、**`conformance-tests/test_c27_concurrent_same_key.py`** (**plug ごと 5 本 + registry guard 2 本**)、**`CONDITIONS.md` の C-27 行を `executable` に** (旧文は `CONDITIONS_HISTORY.md` へ逐語)、**`docs/design/CONFORMANCE_ADAPTER_V1.md` v1.14 → v1.15 (§25)**。
- **集計行 (逐語)**: **C-27 単独 `32 passed`** (実装担当 3 回 / 是正後 2 回 / レビュー担当 1 回)、**`conformance-tests` 全体 `991 passed` を 2 回** (WP-7 / WP-5b のマージ前の版)、**C-05 / C-19 / C-25 の再確認 `163 passed`**、**両 peer の suite は不変**。**監督ゲート (main `2455f96` の単独 root suite) は §9.1 の項目 1 の追記である。**
- **変異 6 種の逐語は D-13 の実施註の表 (M1〜M6)** — **`8 failed, 7 passed` / `2 failed, 8 passed` / `10 passed` (赤にならない。開示) / `9 failed, 6 passed` / `4 failed, 1 passed` / `2 failed, 30 passed`。**
- **本 WP が確定節に足した実現は 1 件だけである** — **両 HTTP adapter の `_run` の「別スレッドからの再入に限る」使い捨て event loop fallback** (同一スレッドの再入は従来どおり大きく落ちる)。**C-27 が先着と後着を別々の OS スレッドから出す形 (D-13 (2)) の直接の帰結であり、安全なのは `ASGITransport` が状態を持たず socket subclass が呼び出しごとに使い捨ての transport を開くからである。**
- **本 WP が見つけた実欠陥は 0 件である** (§11.9 の 6 件に足すものは無い)。**WP-6d-i が入れた lock はそのまま駆動し、共通 suite が初めてそれを観測した。** **レビューの 6 件の是正はいずれも「テストが空振りしていないか」の側の指摘であり (条件付きの assert、静かに返る枝、捨てられていた戻り値、byte 一致でない逐語引用)、§5 の教訓の形をそのままなぞっている。**
- **反証不能な完了条件が 1 件ある** — **作業指示書 WP-6d-ii の完了条件 12 のうち「`wait_until_held` の戻り値を定数 1 にする」変異は、保持件数が常に 1 なので赤にならない。** **監督裁定 2026-09-10 は受理である** — **測っている性質は M5 が pin しており、同条件のもう一方の変異 (上限超過を握り潰す) は赤になる。** **「戻り値は実測値である」という port の規約は、保持件数が 1 に固定されている限り共通 suite では観測できない。** §9.1 の「未達の扱い」の追記に開示した。
