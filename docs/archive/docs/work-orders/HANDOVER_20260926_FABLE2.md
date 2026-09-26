# 引き継ぎ — 2026-09-26 (R-41: 削除確認 phrase の契約規則を C-06 で固定。Class C、規模 M、1 WP)

監督チャット (Fable)。同日の前書 `HANDOVER_20260926_FABLE.md` (R-111) とは別チャット。本書の commit で `HANDOVER_20260925_FABLE2.md` を `docs/archive/docs/work-orders/` へ回転した (`OC` §1.16 の 78)。R-101 (性能) は別チャット (worktree `r101`) で並行中で、本チャットは `tools/perf_baseline.py` と `docs/design/PERF_*` に触れていない。

## 1. 現在地

- worktree `.claude/worktrees/goofy-easley-1e390c` (branch `r41`、基点 main `a1c1ee3`)。変更セット: `conformance-tests/test_c06_destructive_confirmation.py` (V9〜V13 + module docstring)、`conformance-tests/CONDITIONS.md` (C-06 行)、`conformance-tests/CONDITIONS_HISTORY.md` (`## C-06` 末尾)、`conformance-tests/COLLECTION_FLOOR` 4198 → 4233、作業指示書 `docs/work-orders/WORK_ORDER_R41_C06_PHRASE_RULES_V1.md` (v1.1 + §4 訂正註 2 + §5 実施記録)、台帳 v1.124 (R-41 行【追記】、v1.119 の行を記録へ回転)、本書。`security/CONTROL_MAPPING.md` は 3.4 のまま。
- 完了ゲート (監督、solo、使い捨てクラスタ): label r41 `gate: 4233 passed, 2 subtests passed in 996.30s (0:16:36)`、judge=PASS、diff 0; 最終 tree の label r41b `gate: 4233 passed, 2 subtests passed in 492.02s (0:08:12)、judge=PASS、pg_database/pg_roles diff 0`。
- merge: `tools/dev/finalize.py --tools-tests` で main へ `--no-ff`。push は停止中 (GitHub 課金上限)。

## 2. 本チャットで閉じたもの

- **R-41 閉止** (台帳 v1.124)。C-06 に V9 (規則 1: destructive / confirmation 値からの独立)、V10 (規則 3: `json` field で `1` と `"1"` の phrase が別)、V11 (規則 6: 契約 JSON の `confirmation.maxLength` 4 箇所から読む上限。63 文字 entity + 2,000 文字 where 値の delete と drop_entity)、V12 (規則 4: 同一 entity の add_field 後に旧 phrase 拒否・新 phrase で `affected == 1`)、V13 (規則 5: 契約文法違反の名前 2 つが `identifier_syntax` の拒否で phrase を持たず `NOT_FOUND` でない) を足した。30 node 全緑、両 peer とも是正なし。変異 11 + レビュー 1 + 監査 2 すべて期待どおり。
- 監督裁定 2 点 (作業指示書 §1 の 3・4、台帳【追記】): request_id 独立は「別々の要求が同じ phrase」の形でのみ観測 (port は改版しない); 台帳 (b) の `VALIDATION_FAILED` は契約の 2 code (`VALIDATION_FAILED` / `IDENTIFIER_INVALID`) + `identifier_syntax` に読み替え (C-21 D-3(6) の開示と整合。契約変更ではない)。

## 3. 次の一手

- 本書の commit → finalize → main `--no-ff`。他チャット (R-101) が先に main へ入っていれば、台帳の版数行 (v1.124) と引き継ぎ書名 (FABLE2) を renumber してから merge する。
- 台帳 `RM` §8 の未着手項目の着手順は依頼者裁定 (R-38 は別チャットの chip が承認済み)。
- push 再開後: main 先頭で CI を 1 回。

## 4. 依頼者判断待ち・未決

- なし (本件の裁定 2 点は監督裁定として記録済み。異論があれば台帳の R-41 行を見直す)。

## 5. 本チャットで足した運用上の教訓

- **contract の `json` 型語彙が「非型付け」の共通乗り物**: 両 peer とも json field の `eq` に型付きの値をそのまま通すので、`1` と `"1"` を同じ entity に両方受理させたい conformance はこれで書ける。port の `create_entity` は text / integer しか受けず、`create_entity_with_declared_types` が要る。
- **register 3 file の単独実行は HEAD でも赤** (`test_every_executable_condition_has_a_marked_test` は conformance-tests 全体の marker を集める)。register の緑は完了ゲートで判定する。作業指示書の道具引数に書くときは注記を付ける。
- **MitateDB の delete 経路の identifier 検証は 3 箇所の多重防御**: 単一の呼び出しを外す変異では赤にならない。共通関数本体を素通しにする (作業指示書 §4 の 1)。
- **完了ゲートの所要時間は並行チャットの負荷で 3 倍になる** (996 s。R-101 の性能計測は排他 lock を取るので同時には走らないが、CPU は共有)。件数と判定が基点 + 追加分に一致すれば有効。
- `tools/dev/section.py` の見出し引数を zsh で `'5.26'` のように quote する (`=` 始まりの echo 引数は zsh の `=cmd` 展開に当たる)。

## 裁定

| 指摘 | 裁定 | 理由 |
|---|---|---|
| 設計レビュー F1 (V13 の `"C06Upper"` は契約上正しい名前) | 直した | 先頭数字の `"1c06_bad"` に替えた |
| 設計レビュー F2 (port の `create_entity` は `json` を受けない) | 直した | `create_entity_with_declared_types` に替えた |
| 設計レビュー F3 (V12 の entity と affected が未定) | 直した | 同一 entity、行 1 件、`affected == 1` |
| 設計レビュー F4 (V13 が固定するのは規則 5 でなく順序; M5 が弱い) | 直した | M5 を検証除去に差し替え、開示 (6) を足した |
| 設計レビュー F5 (63 文字 entity の未実測ほか) | 直した | タスク 0 (iv)、V11 の field 型・4 箇所・63 の開示 |
| 設計レビュー F6 (§2.7 の cwd と check_doc_refs の走査先) | 直した | worktree を cwd に、検査器は worktree 側の copy |
| 設計レビュー F7 (CONDITIONS セルの予算、"four adapters") | 直した | 3,000 字以内を明記、six plugs に修正 (2,992 字) |
| 設計レビュー F8 (V9 の文字列と M1-m の箇所) | 直した | 短い ASCII 文字列、`_validate_delete_confirmation` を明記 |
| コードレビュー 1 (作業指示書の絶対パス 3 件) | 直した | `<main checkout>` / `<repo>` に置換 |
| コードレビュー 2 (HISTORY の「none of the 5 is vacuous」が実測超え) | 直した | -k 各 peer 1 plug、drop 側は RV1-r と書き直した |
| コードレビュー 3 (V11 drop_entity 側の変異が無い) | 直した | RV1-r を §2.6 に追加 |
| コードレビュー 4 (「V1-V8 は直接探っていない」の誤り) | 直した | V3/V4/V6 の実検査範囲に合わせた |
| コードレビュー 5 (開示 (3) の plug 割り当てが 4 plug 時代) | 直した | 6 plug の実測 (socket は http を継承) に修正 |
| コードレビュー 6 (V9 docstring の存在しない節参照) | 直した | `QueryResult.request_id` の記述に置換 |
| コードレビュー 7 (「this WP's supervisor confirmation」が辿れない) | 直した | 作業指示書 §1 の 2 / 4 を名前で指す |
| コードレビュー O1 (M5-m は検証欠落を見る変異; 呼び出し元 24 箇所) | 直した | §4 訂正註 1 の語を実測に合わせた (観察としても残す) |
| コードレビュー O2 (V13 の `!= NOT_FOUND` は直前 assert の後で常に真) | 観察 | 害なし。読み手への明示として残す |
| 監査 未充足 1 (作業指示書 §5 が空) | 直した | §5 を記入 |
| 監査 O-1 (V10 の取り違え脚が code を見ない) | 直した | 2 脚とも `DESTRUCTIVE_CONFIRMATION_REQUIRED` + 4 宣言を assert、HISTORY に追記、ゲート r41b |
| 監査 O-2 (ゲート 996 s と stderr の `KeyboardInterrupt` warning 1 件) | 観察 | 件数 4233 = 4203 + 30、判定 PASS。負荷は並行チャット由来 (§5) |
| 監査 設計疑義 (契約規則 4 "any other schema change" の範囲) | 観察 | V12 は狭い読みを出所付きで開示し過大な主張はしない。契約側の判断で本 WP の範囲外 |
