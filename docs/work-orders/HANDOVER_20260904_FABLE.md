# 引き継ぎ — 2026-09-04 (第12次。フェーズ5 契約 1.5.0 — 監査語彙の宣言化 + 無条件義務 (b) の適用範囲)

- 引き継ぎ元: Fable (監督)。実装: Sonnet subagent、レビュー/起草/受け入れ監査: Opus subagent (各 WP で独立レビュー + 変異注入を継続)
- 引き継ぎ先: 次セッションの Fable (同体制継続)
- 前提: **第11次 `HANDOVER_20260903_FABLE2.md` の約束事は全て継続**する (§2 到達した状態、§3 クライアント連携、§4 の次の一手と運用規律、§5 教訓)。そのさらに前の引き継ぎ (`HANDOVER_20260903_FABLE.md`、`HANDOVER_20260829_FABLE.md` §3/§4/§5、FABLE3 §4、FABLE4 §4、`HANDOVER_20260830_FABLE.md` §4、`HANDOVER_20260831_FABLE.md` §4、`HANDOVER_20260901_FABLE.md` §3-4/§4) も**全て継続**。現在地のみ本書が上書きする
- 本書は第11次の**直後**のセッション記録である。第11次 §4-2 が「依頼者判断待ち」として並べた **Q1・Q2・Q3 の依頼者裁定 (2026-09-03) を受けて、契約 1.5.0 を公開し両 peer へ出荷した**。第11次 §4-1 の **実機適用は依然として未実施**であり、**クライアント一報も送っていない** (方針不変)

## 1. 現在地 (main)

**契約は `1.4.0` → `1.5.0` へ上がり、両 peer とも `contract_version: 1.5.0` を宣言済みである。** 契約公開 (WP-1) と各 peer の flip (WP-2 / WP-3) は `versioning.version_binding` の規律どおり別コミットに分かれ、flip はいずれも挙動出荷と同一コミットに落ちている。**Q3 (WP-4) と記録整理 (WP-5) は未了**であり、本フェーズは**まだ閉じていない**。

| コミット (merge) | WP | 内容 | root suite (単独実行) |
|---|---|---|---|
| `e26e794` | WP-0 | 設計 v1.3 + 作業指示書 v1.1 (依頼者裁定 Q1+Q2 → 契約 1.5.0、Q3 = 案 A) | 文書のみ (基準 **1545**) |
| `d7a5ffd` | WP-1 | **契約 1.5.0 公開** + 従属判断 10 + port v1.9 + 共通 vector 4 本 + 全体 vacuity guard (`xfail(strict)`) | **1562 passed / 0 failed / 0 skipped / 1 xfailed** |
| `3fd72ad` | WP-2 | **r2db の 1.5.0 出荷** (走査器一般化 + 宣言 2 キー + flip) | **1586 / 0 / 0 / 2 xfailed** |
| `98d2010` | WP-3 | **MitateDB の 1.5.0 出荷** (同型 + flip + guard の `xfail` 撤去) | **1612 / 0 / 0 / 0** |
| `d11c86f` | WP-4 | **Q3 (D-3)** MitateDB の request-count limit 上限撤廃 (契約不変) | `**1611 passed / 0 failed / 0 skipped / 0 xfailed** (WP-4 後の最終値。WP-3 時点 1612 から 201 拒否ケース 3 件の削除と 2 件の追加)` |
| `b0b558a` | WP-5 | 記録整理 (設計 §10、PHASE4 §11 結審、CONDITIONS、CONTROL_MAPPING、runbook、本引き継ぎ) | 文書のみ (`**1611 passed / 0 failed / 0 skipped / 0 xfailed** (WP-4 後の最終値。WP-3 時点 1612 から 201 拒否ケース 3 件の削除と 2 件の追加)` のまま) |

**集計行の出所**: 各 WP のコミットメッセージ末尾の `Root suite alone:` 行 (`git log` で確認できる)。いずれも**監督が完了ゲートで単独実行して得た実測値**である。`conformance` は WP-1 で **404 → 421 passed / 1 xfailed**、WP-3 で **422 passed / 0 xfailed** となった (WP-2 では不変)。

正本の所在 (第11次から更新された箇所のみ):

- **本フェーズの実施設計** = `docs/design/PHASE5_CONTRACT_150_AND_LIMIT_RANGE_V1.md` (**v1.4**)。§3 D-1〜D-4 が確定事項、**§10 が実施記録** (WP-1 / WP-2 は確定、WP-3 以降は `Q3 は案 A で実施済み (WP-4 `d11c86f`): MitateDB の request-count limit 4 クラスの上限 `[1, 200]` を撤廃し正の整数のみ (r2db と対称、エラー文言 `must be a positive integer`)。201 拒否ケース 3 件を削除し大値受理テスト (100_000 を含む 4 クラス) を追加。adapter 構成は 200 据え置き。変異 1〜5 は赤、6/7 (adapter 構成値 / `_MAX_EXERCISABLE_LIMIT`) は C-14 vector 5 の駆動コストが構成値に比例し 1 時間超で打ち切り (台帳 L5-7、完了条件 7/8 は zero-diff で担保)。契約不変。root suite 1611 passed / 0 / 0 / 0` のプレースホルダが残っている)、§11 が将来課題
- **発注と WP 分割** = `docs/work-orders/WORK_ORDER_PHASE5_CONTRACT_150_V1.md` (**v1.7**)。**§0.1 の常設規律 7 項目**は本フェーズで新設された全 WP 共通の規律である (§2.3)
- **契約の裁定記録** = `spec/CCR_DISPOSITION.md` の **従属判断 10** (項目 1 = Q1 / 項目 2 = Q2、(a)〜(d) + 義務の条件付き性の独立段落)
- **フェーズ4 台帳の各項目の状態** = `docs/design/PHASE4_DURABLE_AUDIT_SINK_V1.md` **§11.1** 冒頭表。**L4-1 / L4-2 は CLOSED**、L4-4 / L4-7(iii) は WP-4 待ち
- **依頼者判断待ちの残り** = 同 §11.2。**Q1・Q2・Q5 は結審済み**、**Q3 は裁定済み (案 A) だが実施が WP-4 で未了**、**Q4 は本フェーズに入らず未着手のまま**

## 2. 到達した状態

### 2.1 契約 1.5.0 — 監査語彙が宣言になった

**従属判断 10 の 2 項目**:

- **項目 1 (Q1、D-1、条件付き義務)** — `capabilities().audit_query` に **`operations`** と **`target_kinds`** の 2 宣言キーを追加した。契約に enum は置かない (declare-the-hazard、`event_class` の従属判断 9 項目 4 と同じ姿勢)。義務は「`audit_query` を `unavailable` 以外で宣言する 1.5.0 以上の実装は、`audit_query` が返しうるすべての event の `operation` / `target_kind` をそれぞれの宣言に含めなければならない」という **⊇ 関係**であり、契約が特定のメンバを要求することはない。`audit_query` が `unavailable` の配備は 1.5.0 を宣言したまま本義務を負わない
- **項目 2 (Q2、D-2、無条件)** — 1.4.0 無条件義務 (b) の適用範囲を、**「Since 1.5.0」の新義務ではなく 1.4.0 の義務 (b) 本文への同ラベル補筆**として一意にした (契約自身の "added by a later revision of this document still under that same label" 条項に依る)。受理対象を **control surface の `audit_query` control endpoint (正典パスと control ホスト上の alias)** に scoping し、control-credential store を持たないホストは提示された control/audit credential を未知の credential として `AUTH_INVALID` で拒否**してよい**とする。**許容形であり義務形ではない**、**`forwarded` の禁止も作っていない** — どちらも `versioning.control_discovery` の co-hosting 容認を狭め、転送で条件付き義務 (5) を満たす分離配備を遡って非適合にしてしまうためである

**宣言キーの曖昧解消**: 契約は既に `capability_status.defined.atomic_mutation.operations` を「その capability の batch 実行面が実行する mutation 語彙」の意味で使っている。キー名は親 `audit_query` でスコープされるので `operations` / `target_kinds` を維持したうえで、**契約文に明示的な曖昧解消文を置いた** (これは `audit.fields` の `operation` 列が取りうる値の語彙であって実行語彙ではない)。`target_kinds` に同種の衝突は無い。

**additive 性の機械確認 (WP-1)**: 1.4.0 との再帰 diff で **削除キー 0 / 型変更 0 / enum・required・additionalProperties の狭化 0**、追加キー 2 (`audit.query_operation_vocabulary` / `.query_target_kind_vocabulary`)、変更スカラー 2 (`contract_version` と `versioning.version_binding`)。r2db パッケージ内コピーは `cmp` exit 0 の byte 同一。項目 2 の additive 根拠として要求した「両 peer とも control ホストで alias を同一ハンドラへ載せている」実測 (`r2db-api/src/r2db_api/control_http.py:398-399` / `MitateDB-api/src/mitatedb_api/control_http.py:391-392`) は**行番号ぴったりで一致**した。

**port v1.9**: 抽象メソッドが **2 本**増えた — `audit_query_on_data_plane_host` と `control_surface_cohosted_with_data_plane`。後者はレビュー F-2 / F-3 の裁定で追加されたもので、同居の有無を「返却内容の突き合わせ」で推定する形をやめ、**adapter の宣言トポロジで判定する形**へ置き換えた。4 plug すべてが両メソッドを実装し、**同居宣言は 4 plug とも `False`** である (`docs/design/CONFORMANCE_ADAPTER_V1.md` §19)。

**共通 vector 4 本 + guard 1 本**:

- `test_c09_declaration_agreement_event_class` (1.4.0 条件付き = WP-1 から load-bearing)
- `test_c09_declaration_agreement_operation` / `..._target_kind` (1.5.0 条件付き = WP-2 で r2db 2 plug、WP-3 で 4 plug 全数が通る)
- `test_c09_data_plane_host_audit_query_alias_rejects_control_credential_unless_cohosted` (**無条件登録**)
- `test_c09_every_control_surface_adapter_declares_1_5_0` (全体 vacuity guard。WP-1 で `xfail(strict=True)` 登録 → **WP-3 の flip と同一コミットで撤去**)

宣言整合 3 本はいずれも `_require_nonvacuous_provided` を通る — **既知の耐久イベントを 1 件起こし、宣言 lag 内でポーリングし、非空を precondition として assert する** (§5 の空振りの教訓)。C-09 vector 1 の手書き候補集合は廃止した (`grep -rn "_LIKELY_DESTRUCTIVE" conformance-tests` = 0 行)。加えて依頼者確定文言の**文字列ピン** `test_contract_pins_the_requester_finalized_1_4_0_and_1_5_0_prose` を置いた。

**両 peer の flip と D/N の実測値**:

| peer | flip 箇所 | `operations` | `target_kinds` | `event_class` |
|---|---|---|---|---|
| r2db | `service.py` (data) / `control_plane.py` (control) | **D = 27 語**、U 31、**N 4 語** (`delete_audit` / `set_authorization_state_available` / `set_credential_state` / `control_capabilities`) | **D = 5 語**、N = `application_or_credential` の 1 語 | D 11、N 3 (フェーズ4 のまま) |
| MitateDB | `cell.py` (data) / `control_plane.py` (control) | **D = 29 語** (control 半分 + application 半分の**和**)、U 30、**N 1 語** (`control_capabilities`) | **D = U = 5 語、N = ∅** | D 12、N = ∅ |

N の各要素には「耐久表へ届かない根拠」をコメントで付し、**根拠の文型は 2 種類**ある — 「legacy in-memory sink にのみ届く」と、`control_capabilities` の「**deny 分岐に到達する経路が構造的に存在しない**」である。後者には専用テスト `test_control_capabilities_operation_has_no_reachable_deny_branch` を両 peer に置いた。

**走査器 (両 peer 同型の別実装、コードは共有しない)**: P4-D16 v3 の (a)〜(e) を `_FIELDS = ("event_class", "operation", "target_kind")` の **1 実装へ一般化**し、走査対象フィールド集合そのものを pin するテスト `test_scanner_is_parameterized_over_exactly_these_three_fields` を置いた。一般化に伴い 3 規則を追加した:

- **(b′)** `IfExp` の再帰許容 (三項演算の両枝が literal 寄与になる)
- **(b″)** 同名変数への `Constant` 代入の許容 (**closure 越しを含む**)
- **(b‴)** 読み出し passthrough を **dict literal / 添字代入 / 属性代入の値位置に限定**し、**keyword 引数値位置では禁止**する (リクエスト由来値の逃げ道を構文で閉じる)。**(b‴) は製品変更を 1 行も生んでいない**

**除外リスト** `_NON_AUDIT_<FIELD>_PARAMETERS` は「(c) の keyword-only 要求を名指しで緩める」機構である — **免ずるのは (c) だけ**であり、(b) 側の literal 収集と (ii′) の転送禁止は掛かり続ける。現況は **r2db 8 定義 / MitateDB 1 定義** (`cell.ApplicationCell._plan_operation`)。検証は (i) 実在性と **(ii′) 自関数の仮引数を `<field>=<Name>` で emit 面へ転送しないこと**の 2 本。`event_class` / `target_kind` の除外リストが**空であること自体**も直接 pin してある。

**製品変更 (挙動不変)**: r2db は 5 定義 (`_authorize_role` / `_gate_must_rotate` / `_control_event` / `_event` / `deny_unsupported`) の keyword-only 化 (呼び出し 45 件をキーワード化)、MitateDB は 2 定義 (`_authorize_role` / `_gate_must_rotate`、呼び出し 20 件) の keyword-only 化と `http.py` のローカル変数 `operation` → `schema_operation` のリネーム。**MitateDB の emit ヘルパ 5 定義は無傷**であり `audit_dispatch.py` は 1 行も変わっていない。r2db では「2 フィールドだけを `*` の後ろへ移すと残る位置引数の順序が変わる」ため、**同じ定義の残余引数も keyword-only 化**した (監督裁定、実装が正)。

**同型性テスト**: 両 peer 同名の `test_peer_local_helpers_are_isomorphic_to_the_sibling_peer` が **11 個のヘルパ対**を突き合わせる。**兄弟 peer のテストファイルをパス指定で読む**形 (`importlib` は使わない) で、`"MitateDB-api" in parts` / `"r2db-api" not in parts` を assert して**自己比較で緑になる形を構文で禁止**している。正規化は **行頭インデントを保存**する — トークン列が同じでインデントだけが違う意味差 (走査規則の到達不能化) を検出するためであり、この性質は変異 2 例で実測済みである。

### 2.2 Q3 (WP-4) — 未了

`Q3 は案 A で実施済み (WP-4 `d11c86f`): MitateDB の request-count limit 4 クラスの上限 `[1, 200]` を撤廃し正の整数のみ (r2db と対称、エラー文言 `must be a positive integer`)。201 拒否ケース 3 件を削除し大値受理テスト (100_000 を含む 4 クラス) を追加。adapter 構成は 200 据え置き。変異 1〜5 は赤、6/7 (adapter 構成値 / `_MAX_EXERCISABLE_LIMIT`) は C-14 vector 5 の駆動コストが構成値に比例し 1 時間超で打ち切り (台帳 L5-7、完了条件 7/8 は zero-diff で担保)。契約不変。root suite 1611 passed / 0 / 0 / 0`

### 2.3 常設規律 7 項目 (作業指示書 §0.1、全 WP に適用)

**導入経緯**: **依頼者指示 2026-09-03「差し戻し削減」**を受けて監督が明文化したものである。WP-1 で受け入れ監査 2 回・差し戻し 3 回を要したことが直接の契機であり、`~/.claude/.../memory/role-prompt-templates.md` のテンプレートも**本規律を織り込む形に改訂済み**である。

1. **空振り禁止** — 新規テストは観測対象が 1 件以上あることを assert する (パラメータ化された全 plug/adapter で)。「このテストは X を固定する」と書くなら、X を壊す変異を全 plug で赤にした実測を報告に添える
2. **変異先行** — 完了条件 1 項目につき、それだけを壊す変異を 1 つ対応付ける。対応する変異の無い完了条件は残さない
3. **主張は実測の後** — docstring / CONDITIONS / runbook の断言は変異結果を得た後に、その数値・テスト名を引用して書く
4. **確定文言はファイル経由** — 依頼者確定の契約文・裁定文は scratchpad の確定文ファイルから複製し、**言い換えない**。契約側には確定文を逐語 assert する文字列ピンを置く
5. **設計外の拡張は実装前に上げる** — 設計に無い検査・機構は実装前に報告し、監督裁定を得てから実装する
6. **同型性テスト** — 両 peer に同名で置くヘルパは、peer 名・パッケージ名・パス・空白を正規化して diff する同型性テストで一致を固定する。**peer 間でコードを共有しない慣行は維持する** (依頼者裁定 2026-09-03、案 (a))
7. **実行規律** — 前景 Bash で直列、`timeout` 600000 明示、`ps` で他の pytest が無いことを確認。変異復元は scratchpad backup からの `cp` (`git checkout` 禁止)、`sleep 3` 後に sha256 を 2 回照合、変異文字列を全文 grep

**WP-1 への適用について (監督裁定 2026-09-04)**: 本規律は WP-1 の実装完了**後**に導入された。WP-1 は受け入れ監査 2 回 (+ 機械検査) で全完了条件を個別照合済みであるため、**規律 2 の対応表への組み替えは行わない**。組み替えの対象は WP-2〜WP-5 である。

### 2.4 運用前提の変更点 (第11次 §2.3 の前提 1〜4 は引き続き有効。以下は本フェーズが足した 3 点)

1. **宣言 `operations` / `target_kinds` の消費者への意味** — クライアント (AI エージェント統合者) は `capabilities().audit_query.operations` / `.target_kinds` を読めば、そのホストの監査行に現れうる語彙を**機械的に**知れる。ただし宣言は **⊇ (上位集合)** であって等号ではない — 「宣言に無い値は返らない」は保証されるが、「宣言のすべての値がいつか返る」は保証されない。共通 suite が見るのも「**そのセッションで実際に観測した値 ⊆ 宣言**」だけであり、**宣言の真実性の逆向き半分 (宣言にあるが `audit_query` が決して返さない語彙) は共通 suite の射程外**である。これを担うのは peer-local の (e) 等式と N の根拠だけである (`conformance-tests/CONDITIONS.md` の C-09 行に開示済み)
2. **D→N 降格はスナップショットテストだけが検出する (L5-1)** — (e) 等式 `U == D ∪ N` は「**耐久語彙を D から抜いて同時に N へ足す**」縮小に対して**緑のまま**である (変異で実測済み)。検出するのは `test_declared_audit_operations_change_only_deliberately` / `..._target_kinds_...` などの宣言スナップショットだけであり、これは**テスト側に人手で写した集合との一回きりの固定**である。フェーズ4 の L4-11 が `event_class` について記録した限界を、本フェーズが 2 フィールドへ**拡大した**ことになる
3. **除外リストの保守 (L5-2)** — `operation` は監査専用語ではない (識別子出現数 **r2db 335 / MitateDB 280**)。非監査の `operation` 仮引数を持つ定義が増えれば除外リストも伸びる。検証テスト (i)(ii′) が機械的に見張り、除外を「監査面への逃がし口」として使えないことも変異で実測済みだが、**リストが伸び続けること自体が「(c) の無差別性が `operation` については素直に効かない」という構造の表れ**である。伸びが目立つなら、監査フィールドを別名 (`audit_operation` 等) にする案の再検討材料になる

## 3. クライアント連携状態

**変更なし。一報は送らない (依頼者判断 2026-09-03)。** mitate-30 / mitate-cd は既に終了しており、**第10次 §3 / 第11次 §3 がそのまま有効**である。契約 1.4.0 で伝えるべき事項 (8 項目、`audit_query` が control ホストにあること、`/v1/audit/query` alias の寿命が 1 minor であること、`audit_events` 予約名、4 つの `*_note`) は第10次 §3 を読むこと。**本書はそれを複製しない。**

**1.5.0 のクライアント通知の可否は依頼者判断事項として残っている** (Q5 の結審に含まれていない)。将来クライアント側が 1.5.0 を取り込む際に伝えるべき事項を**記録としてここに残す** — 送る決定がなされたときの材料である。

1. **新しい宣言キー 2 つ** — `capabilities().audit_query.operations` / `.target_kinds`。**`audit_query` が `unavailable` でない実装にのみ現れる条件付きのキー**であり、値は「返されうる値の上位集合」である (§2.4 の 1)。`capability_status.defined.atomic_mutation.operations` および `schemas.MutationRequest.properties.operations` とは**別物**である (契約の曖昧解消文は前者のみを名指す — L5-3)
2. **1.4.0 無条件義務 (b) の明文化** — 義務 (b) は **control surface の `audit_query` control endpoint** (正典パスと **control ホスト上の** alias) に掛かる。**data ホストの `/v1/audit/query` alias に control/audit credential を出すと `AUTH_INVALID` になるのは適合挙動である**。これは新義務ではなく既存義務の適用範囲の明確化であり、実装挙動は変わっていない
3. **alias の寿命は 1 minor のまま** — `endpoints.audit_query` (`POST /v1/audit/query`) の alias は**本フェーズでは除去していない**。除去の可否は従属判断 9 項目 7 の再検討条件として別途裁定される (D-2 は alias が data ホスト上にも存在し続けることを前提にしている)

## 4. 次の一手 (優先順)

### 4-1. 配備実機への適用 (最優先。手順は揃っている)

**第11次 §4-1 がそのまま有効**である。`docs/work-orders/DEPLOY_PHASE4_20260903.md` が正本であり、本書はその目次を再掲しない。着手時にやることは 2 つ — **§0.2 の運用者裁定値 4 つ (A/B/C/D) を埋める**こと、**§1 の適用前チェック**を済ませること。第11次が再掲した 3 点 (migration を当てただけでは 1 行も INSERT されない / MitateDB は `mitatedb-ctrl` の新規配備が必要で `--max-instances=1` は正しさの要件 / `*_CONTROL_PLANE_STATUS` の `enabled` は配備者の表明) も変わらない。

**本フェーズが足した唯一の差分**: 実配備に載せるコードは**契約 1.5.0 のイメージ**になる。r2db は virtualenv 再インストール + 再起動、MitateDB は **1.5.0 コードからのイメージで再デプロイ**である。1.5.0 で増えたのは**宣言キー 2 つだけ**であり、migration・env 変数・endpoint はいずれも 1.4.0 から変わっていない — **DEPLOY 文書の手順自体は書き換え不要**である。**reader DSN を配線しない選択がいつでも正当である**という性質 (DEPLOY 文書 §0.1 の 4) も 1.5.0 でそのまま成り立つ — 項目 1 の義務は `audit_query` が `unavailable` の配備には掛からない。

### 4-2. 依頼者判断待ちと台帳

- **Q4 (`visibility_lag_ms` / `coalescing_window_ms` の 2 プロセス整合の構造化)** — **本フェーズに入っておらず、未着手のまま**である。正本は `PHASE4_DURABLE_AUDIT_SINK_V1.md` §11.2 Q4。監督推奨は**案 B (DB 側を単一の真実にする — 書き手 role の timeout を `ALTER ROLE ... SET` で固定し、control は `pg_db_role_setting` から導出)** を**独立の設計フェーズとして起票する**ことである。migration 新番号 (r2db 0008 / MitateDB 0006) と起動シーケンスに触る両 peer 同時の変更であり、台帳項目として抱え続ける形ではない。**`coalescing_window_ms` も同型なので同じフェーズで扱う**
- **L4-12 (記録のみ、実機未検証)** — `cloud-run-cloud-sql.md` §6.3 の `gcloud auth print-identity-token --audiences=<mitatedb-ctrl URL>` がユーザーアカウント principal に対して拒否され得る件。**対応は実配備時 (§4-1) に行う**
- **L4-13 (OPEN、記録のみ)** — data-plane プロセスの環境に control-credential pepper が存在するのは MitateDB のみという peer 非対称。**本フェーズでも変更していない**
- **L4-8 (据え置き、CLOSED ではない)** — C-09 vector 4 の射程明示のまま。本フェーズは触れていない
- **L5-1〜L5-4 (フェーズ5 起票、正本は設計 §11)** — L5-1 = D→N 降格の検出限界 (§2.4 の 2)、L5-2 = 除外リストの保守 (§2.4 の 3)、L5-3 = 契約内の**第 3 の `operations` 用法** (`schemas.MutationRequest` / `ScopedMutationRequest`) が曖昧解消文の射程外であること、L5-4 = D-2 vector の `provided` 分岐が同居宣言を **adapter の申告で信じる**こと (現時点で 4 plug とも `False` のため実害なし。将来 co-hosting 配備の plug が現れて初めて load-bearing になる)
- **WP-3 受け入れ監査が挙げた未起票の 2 件** (番号付与は WP-5 で行う) — (i) **同型性テストの左右非対称**: MitateDB 側は `inspect.getsource` (デコレータを含む)、r2db 側は `ast.get_source_segment` (デコレータを含まない) で本文を取得している。対象 11 ヘルパは現在いずれも無デコレータのため実害はないが、将来どちらかにデコレータが付くと実装差ではなく取得方式差で赤/緑がぶれる。(ii) **完了条件 17 が名指しする `_ms_from_pg_timeout_text` が同型性テストの対象に入っていない** — 当該ヘルパは **MitateDB-api/tests/test_application_audit.py にのみ存在**し、同型性テストが読む `test_audit_query.py` とは別モジュールであるため現行実装では構造的に対象にできない。**指示書の文言の誤りか、走査範囲を広げるべきかは監督裁定待ち**である

### 4-3. 本フェーズの未処理事項 (WP-5 で片付ける)

- **設計 §10 のプレースホルダ**を全て埋める — §10.1 の WP-3 / WP-4 / WP-5 行、§10.4 の差し戻しの閉じ方と MitateDB 固有の受理境界、§10.5。**プレースホルダが 1 つでも残る状態で本フェーズを完了としてはならない**
- **作業指示書 §10 の WP-1 集計行 `1561` は誤り**である。WP-1 の最終ログ (`scratchpad/wp1-150-fix3-test.log`) とコミット `6e38ef8` はいずれも **1562 passed / 1 xfailed** (1561 は fix3 前の値)。設計 §10.1 は 1562 を採っている。**作業指示書側を訂正する**
- **WP-3 完了条件 16 の文言**が「`xfailed` 1 → 0」のままで、v1.5 の WP-2 訂正 (`xfailed 2`) に追随していない。実態は **2 → 0** であり、2 本とも WP-3 が外すべきものであった (全体 vacuity guard + WP-2 の同型性 placeholder)。実装側の欠陥ではなく指示書の文言
- **WP-1 レビュー指摘 F-5 / F-7 / F-8 / F-9 の本文は失われている** — `scratchpad/review-wp1-150.log` が pytest 出力で上書きされたためであり、受け入れ監査は反映可否を**判定不能**とした。**記録として残す欠落であり、隠さない**

### 4-4. 運用規律の継続 (第11次 §4-4 を継承。本フェーズで足したものは §2.3 の常設規律)

- **完了ゲートの実測は suite を単独実行する** — 他の pytest プロセスが走っていないことを確認してから
- **push 前に `git log --format='%an <%ae>'` で r2fish noreply のみを確認する**
- **コミットは push とセット、さらに main へマージまでを 1 単位とする**
- **変異注入の復元は scratchpad 経由**。`git checkout` は使わない。`sleep 3` 後に sha256 を 2 回照合する
- **コミット前に変異文字列そのものを全文 grep する** — 本フェーズの全 WP で実施し、いずれも 0 件を確認している
- **2026-07-28 から常駐している `pytest tests -q` のプロセス (PID 32812)** — 第11次 §5 が挙げた項目であり、本セッションでも触っていない。**依頼者への確認は依然として未了**である (各 WP の完了ゲート前の `ps` 確認では他 pytest 0 件を確認できている)

## 5. 教訓の追加 (前書全項継承に追加)

- **撤回した設計は、次のフェーズでは「禁止事項」として書く**: フェーズ4 で撤回した走査器 **v2 (「三方向一致」)** — 定義集合に `append` が入りパッケージ内のあらゆる `list.append()` が違反になる名前衝突で緑にできなかった案 — は、本フェーズの作業指示書で**禁止事項 9 (callee 名フィルタを再導入しない) と禁止事項 10 (呼び出し地点ごとの値解決方式を採らない)** として明文化された。**撤回の記録を教訓のまま置くと、次の実装者が同じ形を再発明する。**撤回した案は「なぜ撤回したか」ではなく「**やってはいけないこと**」として発注文書に書き移す。本フェーズで走査器を 3 フィールドへ一般化しても v2 の形が復活しなかったのは、この書き換えがあったからである
- **`operation` は監査専用語ではない — 語の多義性は除外リストという形で表面化する**: `event_class` は監査面にしか現れない語なので「無差別 literal 規律」が素直に効いたが、`operation` は識別子として **r2db 335 / MitateDB 280** 回現れる普通の語である。結果として同じ規律を掛けると監査と無関係な仮引数を巻き込み、**名指しの除外リスト (r2db 8 定義 / MitateDB 1 定義)** が要った。**除外は「例外を彫り込む」ことではない** — 免ずるのは (c) の keyword-only 要求だけであり、(b) の literal 収集と (ii′) の転送禁止は掛かり続ける構造を保った。**「除外できる範囲を構文で狭めたうえで、除外そのものを機械検証する」**なら、除外リストは弱さではなく可視化である。ただし**リストが伸び続けること自体が構造の表れ**であることは台帳 (L5-2) に残した
- **N の実行時実測が静的推測を 2 回覆した**: 設計 §1.4 の候補表 (プロトタイプ走査器の静的出力) は、**2 点で実測と食い違った**。(i) r2db の `authenticate` は N 候補に挙がっていたが、**失敗 authenticate の `AUTH_INVALID` 拒否が `_DURABLE_DENIAL_CODES` 経由で耐久化する**ことが WP-2 の実行時実測で分かり **D 側**になった。(ii) 候補表に無かった `control_capabilities` が、**deny 分岐へ構造的に到達できない**という別の理由で **N 側**になった — しかも**両 peer で同型に**である。MitateDB は「N = ∅」という初期仮説で発注していた。**「この語は耐久表に届かない」という主張は、静的に読める構造からは決まらない** — 実際に耐久行を立てて観測するテストだけが決める。設計側は候補表を消さずに**訂正註**として残した (起草時の推測と実測の差そのものが記録である)
- **空振りは「緑」の顔で来る**: WP-1 の宣言整合 vector は、**4 adapter 中 2 つ (HTTP 形の plug) で `audit_query` の返却 `events` が 0 件**であり、部分集合検査が空 list に対して自明に通っていた。テストは緑、変異も一部の plug でしか赤にならない。修正は `_require_nonvacuous_provided` — **既知の耐久イベントを 1 件起こし、宣言 lag 内でポーリングし、非空を precondition として assert する** — であり、修正後は宣言語彙を空集合にする変異が **4 plug 全数で赤**になることを実測した。これが常設規律 1 (空振り禁止) の直接の由来である。**「全 plug でパラメータ化されている」ことは「全 plug で観測している」ことを意味しない。**
- **確定文言は複製し、言い換えない — そして機械で pin する**: WP-1 の受け入れ監査は、依頼者確定文 4 文のうち **2 文が逐語でない**ことを検出した。対処は逐語復元と、**確定文を逐語 assert する文字列ピンのテスト**である。最終ラウンドの機械照合で残った不一致 1 件は、**照合スクリプト側の正規化が ASCII 二重ハイフン `--` を扱わないこと**に起因する見かけの差であった (実文は確定文と一致)。**照合器自身も検証対象である** — 「不一致」が出たら実装を疑う前に照合器を疑う手順を持つこと。これが常設規律 4 の由来である
- **モデルが過負荷 (529) のときは、役割を落とさず担当を替える**: WP-1 の受け入れ監査 2 回目は Opus が 529 で応答できなくなった。**判定を諦めるのでも Opus の復帰を待つのでもなく、機械検査 (逐語照合・再帰 diff・`cmp`・変異注入・collect-only・秘密 grep) を Sonnet に実行させ、判定は監督が行った**。Sonnet への発注は「**機械的事実のみ、判定なし**」と明示し、出力は scratchpad (`audit-wp1-150-r2-mech.md`) に落とさせた。**受け入れ監査は「実測」と「判定」に分解でき、実測の側は担当を替えられる。**分解できる形で発注してあれば、モデルの可用性は工程の停止理由にならない
- **Google Drive 同期ツリー上の復元再出現は、まだ起きる (監督の観測)**: 第11次 §5 が挙げた現象 — 同期が復元より後に走り、ハッシュ照合を通った直後のファイルが古い内容へ戻される — は本セッションでも観測された。**常設規律 7 の「`sleep 3` 後に sha256 を 2 回照合」は、この 1 事象のための規律である。**本セッションの全レビュー・全監査の記録に「二重照合 全一致」が明記されているのは、規律が実際に回っていることの証拠である。**規律を教訓に格上げしたら、次は「実施したことを記録に書かせる」ところまでやる**
- **サブエージェントは長い suite でバックグラウンド待ちに入って止まる (監督の観測)**: 第11次 §5 と同じ現象が本セッションでも起きた。**完了ゲートの実測値は監督が自分で握る** — 各 WP の集計行はコミットメッセージの `Root suite alone:` 行として残してあり、後から `git log` で照合できる。実装・レビュー・監査の各報告に書かれた集計行は**監督の実測と突き合わせる対象**であって、それ自体を正本にしない
