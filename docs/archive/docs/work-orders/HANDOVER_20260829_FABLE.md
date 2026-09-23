# 引き継ぎ — 2026-08-29 (第3次。Fable 監督期の第2セッション終了時)

- 引き継ぎ元: Fable (監督・設計)。実装: Sonnet subagents、レビュー: Opus subagents
- 引き継ぎ先: 次セッションの Fable (同体制継続)
- 前提: `docs/work-orders/HANDOVER_20260828.md` (前々書、Opus) と `docs/work-orders/HANDOVER_20260828_FABLE.md` (前書) は歴史的記録として保持。**本書が現在地を上書きする**

## 1. 現在地 (branch `conformance-effectivation-and-r2db-service-layer`、origin へ push 済み、`main` 未マージ)

**フェーズ1 (CCR-13 storage 実装) は完了した。** 本セッションの7コミット (`b5216e7`〜`c0f7ac3`):

| コミット | 内容 |
|---|---|
| `b5216e7` | 設計 `docs/design/R2DB_CCR13_STORAGE_V1.md` v1.1 (WP-0 独立レビュー反映済み) |
| `1979385` | WP-1: conformance port v1.2、C-17/C-18 登録、共通 fixture の `id` 退避、C-12 upsert 対照の精密化 |
| `63e3ab3` | WP-2: in-memory 参照実装 (`ApplicationCell`) への CCR-13 full 意味論 + `DataService` 暫定ゲート + Q-1 (案B) 契約追補 |
| `b16652e` | Q-2 裁定反映: `contains` リテラル定義 + `matches` 演算子追加 |
| `7e7b6ad` | WP-3: PostgreSQL 実実装 (id identity・`_r2db_revision`・upsert 2文構成・DOMAIN 型・contains/matches) + 両 cell parity |
| `3170d14` | WP-4: order_by / cursor pagination の HTTP 公開 |
| `8d1691e` | WP-5: 申告更新 + ゲート撤去 (単一コミット)、C-17/C-18 の3 adapter 実行可能化、**逆向き C-12**、port v1.3/v1.4 |
| `c0f7ac3` | WP-6: CONTROL_MAPPING (SI-09 drop_index)・deploy (PostgreSQL 13+ 前提・0003 DOMAIN catch-up)・README・実装記録 |

- テスト: `./.venv/bin/python -m pytest` で **544 passed** (r2db in-process / r2db HTTP+実PostgreSQL / MitateDB の3 adapter 込み)。`r2db-api/tests/test_postgres.py` 単独 180 (root testpaths 外なので個別実行が要る)
- 実装記録と**将来課題台帳** (レビュー minor 繰越8件 + 契約 additive 候補4件) は設計文書 §11/§12
- 依頼者裁定 (本セッション、`spec/CCR_DISPOSITION.md` 従属判断 4・5 に記録):
  1. **Q-1: 多キー upsert は案B** — `Mutation`/`ScopedMutation` に `unique_key` (catalog キー名参照)。1キーなら省略可、多キーで省略 `VALIDATION_FAILED`、未宣言名 `NOT_FOUND`、非 upsert 付与 `VALIDATION_FAILED`。`unique_keys[].name` は required 化
  2. **Q-2: `contains` は案i+補足** — リテラル部分一致 + `matches` (`%`/`_`/`\` エスケープ) を最初から追加。「一般的に期待されることは最初から普通に行える」(依頼者言明)。両演算子とも大文字小文字区別。末尾裸 `\` は `VALIDATION_FAILED` (文言確定)
  - いずれも契約 1.1.0 の**公開前追補** (main 未マージのため版数据え置き。公開後なら 1.2.0 相当だった)

## 2. 残る実装フェーズ (順序は `spec/CCR_DISPOSITION.md`「実装順序」)

1. **CCR-14 control plane HTTP 面** (r2db-api): `/control/v1` の11 endpoint (案B 裁定済み: issue は role=runtime/developer のみ、role=control は `CAPABILITY_UNSUPPORTED`)。bootstrap/reset の儀式。実装後に C-14/C-15 を executable 化し、暫定 CLI (`python -m r2db_api.ops`) の位置づけを再定義
2. **MitateDB の HTTP 層と永続化** (二実装要件の HTTP 越し実証。現在 in-process + `:memory:`)
3. **耐久 audit sink** (両 peer 共通ギャップ)
4. 配備の実機適用 (段階1) は運用者作業。**注意: migration 0003 に DOMAIN 追加が入ったため、もし旧 0003 で provision 済みの DB があれば catch-up が要る** (`POSTGRES_PROVISIONING_RUNBOOK.md` に手順注記済み。現時点で実機 provision は未実施なので通常は無関係)
- 未解決の契約判断: **破壊的確認の有効性定義** (C-06 共通化、MitateDB の確認トークン不検証)。CCR-14 の失効確認条項はこれに依存 (採用済みだが実効化待ち)
- `main` へのマージ時期は依頼者判断 (contract 1.1.0 の「公開」= マージと解釈してきた。マージ後の契約変更は版数を上げる)

## 3. 判断の軸と約束事 (前書 §3 を継承、本セッションの追加)

- 堅牢で安全が第一、次に最大限の自由。ゲートでなくガードレール。機構でなく結果。結果は検証可能な性質に分解
- 採否・裁定は依頼者。契約の文言確定レベルの細部は監督が決めてよいが、必ず依頼者に報告して覆せる形にする (末尾裸 `\` はこの形で確定した)
- 利用設計者は AI エージェント (宣言は読まれる前提)
- コミットは push とセット。push 前に `git log --format='%an <%ae>'` で r2fish noreply のみ確認
- adapter は peer の不足を埋めない。skip は fail。復元は scratchpad 経由 (`git checkout` 禁止)
- **申告と実挙動は単一コミットでしか同時に動かさない** (本セッションで確立): 実装が先行する間は `DataService` 暫定ゲートで公開面を封鎖し、申告更新とゲート撤去と conformance green を同一コミットに載せる
- **逆向き C-12** (申告に無い操作・演算子が実行できたら赤) が executable。「申告より広い実挙動」の類型は以後 conformance が機械的に捕まえる
- **変異注入を標準の完了条件にする**: テストを足したら、そのテストが守る性質を壊す変異で赤くなることまで確認する (本セッションで延べ40本超、生存変異はすべて実在のテスト欠落を露出した)
- **実装者の完了報告も実測で裏取る**: 報告と実装が食い違った実例が1件あった (§4-5)

## 4. 本セッションで犯し、レビューが捕捉した誤り (再発防止)

1. **設計初版の見落とし群** (WP-0 レビューで blocker 3件): `id` 予約が既存 conformance fixture を破壊し既存 JSONB `id` 列を偽アドレス宣言にする点、C-12 upsert 対照が壊れる点、そして**多キー upsert の拒否を実装が独自に決めていた点** (契約が定めない領域を実装が閉じる = CCR-13 が是正した欠陥の形の再発)。3点目は依頼者裁定 (Q-1) に上げて解決した
2. **WP-2 実装が設計の「外部挙動不変」を破った** (B-1): 拒否が http 層でなく共有 bind 層に住んでいたため、語彙受理と同時に公開面へ自動開放された。設計側の WP 分割が拒否の所在を見誤っていたのが根因。暫定ゲートで是正
3. **同型の再発が WP-3 でもう一度起きた** (`matches` — ゲート列挙が Q-2 裁定より古いまま)。2度目で恒久対策 (逆向き C-12) に切り替えた。教訓: **同じ形を2度踏んだら、3度目を防ぐのは注意ではなく仕組み**
4. **契約追補自身の穴** (`unique_keys[].name` optional のままでは選択規則が原理的に満たせない) をレビューが捕捉。契約を書いたら「その文言を満たせない合法状態が構成できるか」を敵対的に探すこと
5. **実装者の報告と実装の乖離**: 「float 表現の修正は型付き列にのみ適用」と報告されたが、型を渡す経路が実装されておらず乖離が untyped 側へ移動していた (確認レビューが実測で捕捉)。PostgreSQL 側の観察自体は正確だった — 観察の正しさと実装の正しさは別々に検証する
6. **レビュア側の誤りも2件** (記録する慣例): must_ignore vector が「静かに空虚化する」という実装者の記述を「赤くなるはず」と誤指摘 → 実装者が変異実測で反証し、原記述が維持された。既反映の N-4 を未反映と誤指摘。**実測を伴う反証は役割に関係なく通る** — この対等性が機能している

レビュー往復の実績: 設計1回 + 実装8往復 (WP-1×2、WP-2×3、WP-3×4 相当、WP-4×1、WP-5×2)。1巡で済んだ WP は無い。実在の peer 不適合3件 (MitateDB の precondition 黙殺 / contains・is_null の拒否コード / r2db の matches 未申告実行) はすべてレビューか逆向き条件が発見した。

## 5. 細部の申し送り

- `DataService` は旧 facade (`query`→list / `mutate`→int) と新 facade (`query_page`→QueryPage / `mutate_result`→MutationResult) を並存させている。旧は既存呼び出し元の互換用。conformance plug と http は新 facade を使う
- `r2db-api/config/capabilities.json` (静的成果物) は実 `capabilities()` 応答との一致テストで縛られている — 申告を変えたらこのファイルも動く
- outcome 型 (`QueryOutcome`/`MutationOutcome`) は frozen dataclass。`revisions`/`assigned_addresses` の `None` は「未維持」、`[]` は「空」で意味が違う
- `_r2db` prefix は entity 名・フィールド名・index 名すべてで予約。`id` はフィールド名として予約 (サーバ採番アドレス)
- untyped (JSONB) 列への JSON null は SQL NULL としてバインドする (両 cell の `is_null`/順序一致の要)。`contains`/`matches` の text 表現は PostgreSQL 出力規則 (`#>> '{}'`、jsonb 数値のリテラル保存、キー順 = バイト長→バイト順) に in-memory 側を合わせてある — ここを触るときは `test_parity_*` が守る
- 型付き列は `add_field` + `field_type` のみで作れる (`create_entity` の fields は JSONB)。object/array は DOMAIN 型 (`_r2db_json_object`/`_r2db_json_array`)
- 勤務表移行の残り前提は **NOT NULL / DEFAULT の契約語彙** (設計 §12 の申し送り。契約 additive 変更として依頼者裁定が要る)
- `docs/design/R2DB_CCR13_STORAGE_V1.md` は設計 + 3回分の訂正記録 (§8/§9/§10) + 実装記録 (§11) + 将来課題台帳 (§12) を1文書に持つ。フェーズ2の設計文書は CCR-14 用に新規に起こすこと
