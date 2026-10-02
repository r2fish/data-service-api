# 作業指示書 — R-33 cell 経路と HTTP 経路で digest の材料が食い違い得る (死んだ引数 `destructive` の除去)

## 0. 出所と基点

- **v1.0 (2026-10-03)。** 基点はローカル main `c7403a4` (作業ツリー `.claude/worktrees/r33`、branch `r33`。cloud session の読解報告 `docs/design/R33_DIGEST_MATERIAL_READING_V0_1.md` を merge `2dc4b88` で取り込み済み)。台帳は `docs/design/ROADMAP_POST_PHASE7_V1.md` §8 の R-33 (規模 M)。
- **変更クラスは Class B** (`MitateDB-api/src/mitatedb_api/cell.py` の署名 1 行と `MitateDB-api/tests` の 2 ファイル。`tools/change_class.py`: class=B)。契約 1.14.0 のまま、`spec/`・`conformance-tests/`・`security/` の差分 0。
- 規律: `docs/work-orders/OPERATING_CONDITIONS.md` §1.5 の 32〜40、§1.13 の 74 (規模 M: 作業指示書 1 節、実装担当、変異、レビュー担当、完了ゲート。監査担当は Class B なので起動しない)。commit・merge・`gate.py`・`finalize.py` は監督のみ。下請け Agent を使わない。

## 1. 裁定前の特性化 (監督実施 2026-10-03。報告書 §4 の E-1〜E-7)

実装担当 (特性化) が報告書 §4 の名前で 5 本を書き、`tools/dev/pt.py -C .claude/worktrees/r33 -- MitateDB-api/tests/test_dry_run_and_plan.py MitateDB-api/tests/test_http.py -q` → `103 passed` (新規 5 件は `-k` で `5 passed, 98 deselected`)。E-1〜E-5 は **5 件とも報告書の見込みと一致** (不一致 0)。E-6 (M1: `cell.py` の `create_collection` の `if digest_extra:` → `if False:`) と E-7 (M2: `http.py` の `digest_extra` のタプルから `"destructive"` を落とす) は E-2 のテストで**両方とも赤** (`mutate: 2 mutations, 2 as expected, restores verified 2/2 files (sha256 x2), grep counts unchanged`)。特性化の時点で src は無変更。

## 2. 裁定 (監督 2026-10-03)

- **D-1 選択肢 (a) 死んだ引数を除く。** 理由: spec (`spec/data-service-api.v1.json:848`、`:851`) は digest の材料を「契約上の要求オブジェクトの全フィールド」と定め、HTTP 経路はそのとおり `destructive` を digest に入れる (E-2・E-3 で実測)。in-process の公開入口 (`ApplicationDeveloper.create_entity` / `add_field` / `alter_field`) は `destructive` を含む 5 キー (`destructive` / `confirmation` / `revision` / `index` / `unique`) を `digest_extra` keyword の 1 本でだけ運び (`cell.py:3814-3816`。既存 pin `test_dry_run_and_plan.py:928` が `dev.add_field(..., digest_extra={"revision": "5"})` で固定)、HTTP 層と同じ merge に入るので、一般則「同じ契約上の要求は入口によらず同じ digest」は in-process 側でも成立している。唯一の穴は `ApplicationCell.create_collection` の `destructive` 引数 — `digest_extra` と並ぶ死んだ第 2 経路で、4 位置引数か `destructive=` keyword の直接呼び出しだけが到達する。除去すれば `destructive` の経路が他 4 キーと同じ `digest_extra` 1 本になり、署名が現状を正直に表す。**【訂正註 1 (2026-10-03、コードレビュー 1 の指摘 2)】** 起草時の本文は「in-process の公開入口は 5 キーのどれも表現できない」「一般則は in-process 側では空に成立」と書いていたが、上のとおり `digest_extra` keyword が在るので誤りであり、本文を差し替えた。読解報告 `docs/design/R33_DIGEST_MATERIAL_READING_V0_1.md:29`・`:31` の同じ記述 (「in-process の公開入口にも対応する引数が無い」) も同じ誤りで、報告書は書き換えず台帳 R-33 行の閉止註に記録する。結論 (a) は変わらない (むしろ強まる)。(b) は、`create_entity` に意味を持たない flag を in-process から表現する機構 (入口の署名拡張、`None` 既定による省略/明示 False の区別、3 操作の整合) を呼び出し元 0 件のまま足し、新しい非対称 (報告書 §5 (b)) を作る。堅牢で安全が第一 (両案とも挙動不変)、次に自由 (両案とも client を制約しない) で差が無く、単純さと長期の正しさで (a)。
- **D-2 行 4 (`transact` の in-process 再構築、報告書 §3 行 4) は R-33 の範囲に含めない。** E-5 で token の hex 部の相違を実測した (見込みどおり)。`cell.py:236-243` の docstring が開示済みの既知の構造であり、閉じるには conformance の port file に触る別の変更セット (Class C 以上) が要る。`OPERATING_CONDITIONS.md` §1.15 の 77 の問い (b): in-process 経路は `spec/` を通る client の経路ではないので DB の利用者は気づかない → **観察** (起票しない)。E-5 のテストは開示の実測 pin として残す (名前が「differ」である。直す変更セットは docstring とこのテストを同時に反転する)。
- **D-3 報告書 §6 の 1 (`confirmation` / `revision` / `index` / `unique` を `create_entity` に付けると受理して無視し digest にだけ入る) は本件に抱き込まない。** E-4 で `destructive: true` の実要求が `committed: true` で実行されることを実測した。`revision` の意味は R-107 (MitateDB の revision_preconditions) の範囲、他 3 キーは shape 上許されて意味を持たない要求であり、観察として引き継ぎ書に残す。
- **D-4 E-1 は反転ではなく置換する。** (a) では 4 位置引数の呼び出しが `TypeError` になるので、E-1 (`destructive=True` ありなしで token 同一) は成立しない。代わりに署名 pin を置く (§3 の完了条件 1)。E-2〜E-5 は現行の HTTP 挙動と開示の pin としてそのまま残す。

## 3. WP-1 Change Set Manifest

| 触ってよいファイル | 触らないファイル |
|---|---|
| `MitateDB-api/src/mitatedb_api/cell.py` (`:990` の署名から `destructive=False` を除く。本体・docstring は無変更)、`MitateDB-api/tests/test_dry_run_and_plan.py` (E-1 を署名 pin に置換)、`MitateDB-api/tests/test_http.py` (必要なら docstring の整え) | それ以外の全部 (`spec/`・`security/`・`conformance-tests/`・r2db-api・`docs/`・台帳 (記録は監督)) |

着手手順: (1) `git diff --name-only main...HEAD` と作業ツリーの変更を `tools/change_class.py` に通し B を貼る。(2) `ApplicationCell.create_collection` を 4 位置引数以上または `destructive=` で呼ぶ箇所が 0 件であることを現物で再照合 (`git ls-files -z | xargs -0 grep -n "create_collection("` を `docs/` を除いて読む。1 件でもあれば止めて監督へ)。(3) 署名から `destructive=False` を除く。(4) E-1 を署名 pin に置換。(5) `tools/dev/pt.py -C . --wait 300 -- MitateDB-api/tests -q` と `tools/dev/pt.py -C . --wait 300 -- MitateDB-api/conformance -q` (担当 peer の suite と conformance plug。suite 全体は回さない)。(6) 変異。(7) `tools/check_comment_provenance.py --base c7403a4 MitateDB-api/src/mitatedb_api/cell.py` (署名行のコード変更は §4.1 (1) で赤 = 受理、経緯トークン 0 件であること)。

| # | 完了条件 | 変異 | 赤になる test id |
|---|---|---|---|
| 1 | `ApplicationCell.create_collection` の署名に `destructive` が無く、`principal, name, fields` の後は keyword-only である (`inspect.signature`)。4 位置引数の呼び出しは `TypeError` | M-a1: `cell.py:990` に `destructive=False` を戻す → 赤 | `MitateDB-api/tests/test_dry_run_and_plan.py::test_create_collection_has_no_destructive_parameter` |
| 2 | HTTP の `create_entity` の plan token は body の `destructive` に commit する (E-2) | M1 (`if digest_extra:` → `if False:`) → 赤; M2 (タプルから `"destructive"` を落とす) → 赤 | `MitateDB-api/tests/test_http.py::test_http_create_entity_plan_digest_commits_to_destructive` |
| 3 | HTTP で省略と明示 `false` は別の token (E-3) | M2 → 赤 (省略と明示 false が同じ token になる) | `MitateDB-api/tests/test_http.py::test_http_create_entity_plan_digest_differs_between_omitted_and_explicit_false_destructive` |
| 4 | HTTP の `create_entity` は `destructive: true` を受理して実行する (E-4) | M3: `http.py` の `create_entity` 分岐で body に `destructive` が在れば `ValidationError` を上げる (1 行の挿入) → 赤 | `MitateDB-api/tests/test_http.py::test_http_create_entity_accepts_and_ignores_destructive` |
| 5 | in-process と HTTP の同じ単一 entity batch の token は hex 部が違う (E-5、開示 `cell.py:236-243` の実測 pin) | M4: `cell.py` の `_reconstruct_digest_operation` が `entity` を各 operation に置く行を落とす、または HTTP 側と同じ形に揃える 1 箇所の変異 → 緑のままなら別の差 (`values` の有無) が原因。**赤にならなければ監査照合に切り替え**: 両 token の hex 部を報告に貼る。**【訂正註 2 (2026-10-03)】** M4 (per-operation の `entity` を落とすだけ) は緑のまま。赤にするのはコードレビュー 1 の変異 **R-E5-close** (per-operation の `entity` を落とし、単一 entity の batch なら top level に置く 2 箇所の編集 = in-process の digest を HTTP の形に揃える) で、両 token が一致して赤になる。原因は `values` の有無ではなく **top level の `entity` の有無** | `MitateDB-api/tests/test_dry_run_and_plan.py::test_in_process_and_http_plan_tokens_differ_for_the_same_single_entity_batch` |
| 6 | MitateDB-api の suite と conformance plug の集計行が署名変更の前後で同数 (削除 0) | 監査照合: 手順 (5) の前後の集計行 | — |
| 7 | 上の表に変異も監査照合も無い行が無い | 監査照合 | — |

道具: `tools/dev/mutate.py "$SP/r33-mutations.json" -C .claude/worktrees/r33 --wait 300` (1 変異 1 entry、`tests` に node id)。`tools/dev/gate.py -C .claude/worktrees/r33 --label r33` (監督のみ。root の期待値は main `c7403a4` の 5019 + 新規 5 本 = 5024)。

## 4. レビューと監査

設計レビュー無し (Class B、設計は本書 §2)。コードレビュー 1 回 (`reviewer`、モード: コードレビュー)。受け入れは監督が対応表と集計行で判定する。

## 5. 実施記録 (監督が書く)

### 5.1 訂正註と監督裁定

- 訂正註 1 (§2 D-1 の前提) と訂正註 2 (§3 行 5 の変異) は本文中に置いた。どちらもコードレビュー 1 の指摘 (2 と 3) による。
- コードレビュー 1 の指摘 1・4 (E-5 の docstring が開示済みの穴を期待挙動のように読ませる、節コメント・E-4 の docstring・module docstring が裁定後の現状とずれる) は差し戻し 1 で docstring とコメントだけを直した (テストのコードと src は無変更)。指摘 5 (conformance `-k mitatedb` の前の実行で `test_c27_same_digest_executes_once[MitateDB-api-http]` / `[-socket]` が `_control_actor_is_live` → `/control/v1/capabilities` の `LIMIT_EXCEEDED` で一過性に赤、src 無変更の時点、後の実行で緑) は観察 (引き継ぎ書の「裁定」節)。
- 手順 (5) の `MitateDB-api/conformance` はテストを持たない (adapter の置き場) ので、実装担当の読み替え `conformance-tests -q -k mitatedb` (549 件) を受理した。

### 5.2 実施と受け入れ

- **差分**: `MitateDB-api/src/mitatedb_api/cell.py:990` (署名から `destructive=False` を除く 1 行)、`MitateDB-api/tests/test_dry_run_and_plan.py` (`import inspect`、`test_http` / `test_postgres` からの fixture import、R-33 の節: 署名 pin `test_create_collection_has_no_destructive_parameter` と E-5 `test_in_process_and_http_plan_tokens_differ_for_the_same_single_entity_batch`、module docstring に E-5 だけが PostgreSQL を使う旨)、`MitateDB-api/tests/test_http.py` (補助 `_r33_schema_dry_run_plan` と E-2 / E-3 / E-4 の 3 本)。`tools/change_class.py` → `class=B`。
- **呼び出し元の再照合**: `ApplicationCell.create_collection` を 4 位置引数以上または `destructive=` で呼ぶ箇所は src・tests・conformance adapter で 0 件 (src の caller は `cell.py:1364` と `:3811` の 2 つ、どちらも 3 位置 + kwargs)。
- **集計行 (署名変更の前 → 後)**: `MitateDB-api/tests` `1855 passed, 2 subtests passed` → 同 (削除 0)。`conformance-tests -k mitatedb` 前 `2 failed, 547 passed, 908 deselected` (c27 の一過性の赤。§5.1) → 後 `549 passed, 908 deselected`。差し戻し 1 の後の 2 ファイル: `103 passed`。
- **変異 (監督が最終の木で再実行)**: `mutate: 6 mutations, 6 as expected, restores verified 2/2 files (sha256 x2), grep counts unchanged` — M-a1 (署名に `destructive=False` を戻す → 条件 1 赤)、M1 (`if digest_extra:` → `if False:` → 条件 2 赤)、M2 (タプルから `"destructive"` を落とす → 条件 2 赤)、M2b (同じ変異で条件 3 赤)、M3 (`create_entity` 分岐で `destructive` を拒否 → 条件 4 赤)、R-E5-close (in-process の digest を HTTP の形に揃える → 条件 5 赤、両 token が `03eceef9…` で一致)。M4 (per-operation の `entity` を落とすだけ) は緑のまま (訂正註 2)。
- **E-5 の token (診断変異で取得、復元照合済み)**: 無変異の in-process `6da2852618c6f63f9275c059798258b32f876641624b2cbabaae161b266054b0.1`、HTTP `03eceef9232e2819ae834cdad4a8ef833e902151708aa48ae3da51781ca5d8ee.1`、M4 適用後の in-process `4741935785de74694994f4beb15472b4b6e780fe466885376c2eb15fa9515d3b.1` (実装担当の報告は無変異と M4 の対応が逆で、レビュー担当が canonical JSON の sha256 の再計算で訂正した)。revision 部は両経路とも `.1`。
- **来歴検査**: `tools/check_comment_provenance.py --base c7403a4 MitateDB-api/src/mitatedb_api/cell.py` → `FAIL (§4.1 (1)) …cell.py:990 code changed` のみ (署名行のコード変更 = 受理)、経緯トークン 0 件。
- **コードレビュー 1** (`reviewer`、Class B、担当観点 指定なし): 指摘 5 件 (低〜中 1、低 3、観察 1)、クラスの引き上げ無し。4 件を同じ変更セットで直し、1 件は観察。
- **完了ゲート** (監督単独、main `1abd5e8` を merge した最終の木、`--label r33`): `5024 passed, 2 subtests passed in 474.56s (0:07:54)`、`judge=PASS`、実行クラスタの差分 0。root collection は main の 5019 + 新規 5 本 = 5024 (`COLLECTION_FLOOR` 5019 → 5024)。
- **最終判定**: 受け入れ。台帳 R-33 を閉じた (v1.155)。起票は無し。
