# 引き継ぎ — 2026-09-24 (`security/CONTROL_MAPPING.md` を形式 3.0 へ移行した。契約は 1.8.0 のまま) 同日に並走した別チャットの引き継ぎ書 `docs/work-orders/HANDOVER_20260924_FABLE3.md` ([finding-cap]、main `8c9d4f2`) は本書と独立であり、本書の統合時に `HANDOVER_20260924_FABLE2.md` を `docs/archive/docs/work-orders/` へ回転した (最新 2 通 = FABLE3 と本書)。

本書は前書の全項を写さない。生きている事項だけを載せる。恒久の運用規律は `docs/work-orders/OPERATING_CONDITIONS.md`。前書は `docs/archive/docs/work-orders/HANDOVER_20260924_FABLE2.md` (正本と記録の分離、第 1 段) で、**同書の §3・§4・§5 と、そこが引く前々書 (`docs/archive/docs/work-orders/HANDOVER_20260924_FABLE.md`。R-79 閉止・R-80 計測。本書の変更セットで archive へ回転した) までの §3・§4・§5 は引き続き有効**である (本書の §3〜§5 は追加だけを書く)。前のチャットの scratchpad は読めない。監督のモデルは Fable。push は GitHub の請求上限のため停止中 (`OPERATING_CONDITIONS.md` §2 の 20)。**依頼者が言うまで push しない。** origin/main は `8bf21a2` のまま。

## 1. 現在地

- 基点のローカル main は **`94febb3`** (台帳 v1.113)。本チャットの commit は finalize.py による 1 commit と main への `--no-ff` merge (SHA は `git log -1 main` で読む)。
- 完了ゲート: `gate: 4018 passed, 2 subtests passed in 504.40s (0:08:24)` / `gate: judge=PASS` / `gate: pg_database/pg_roles diff 0` (2026-09-24, label cm-form-v3)。`tools/tests -q`: `pt: 588 passed in 73.71s (0:01:13)`。
- `security/CONTROL_MAPPING.md` は版 **3.0** (2.25 から移行)。台帳 `docs/design/ROADMAP_POST_PHASE7_V1.md` は **v1.114** (R-103 の起票と閉止を同じ版で。v1.113 の版上げで回転されていなかった v1.109・v1.108 の行も archive へ)。設計 `docs/design/CONTROL_MAPPING_FORM_V3_V0_1.md` は **v0.4** (§9 が実施記録)。
- 本チャットの worktree `.claude/worktrees/determined-nightingale-9c442a` (branch `claude/determined-nightingale-9c442a`) は本書のコミット後に `fold.py` で畳める。

## 2. 本チャットで閉じたもの

| 項目 | 要点 |
|---|---|
| **R-103** `security/CONTROL_MAPPING.md` の形式 2.25 → **3.0** (規模 L、Class D) | 設計 `docs/design/CONTROL_MAPPING_FORM_V3_V0_1.md` **v0.4** (§9 実施記録)、作業指示書 `docs/work-orders/WORK_ORDER_CONTROL_MAPPING_FORM_V3.md` v1.0 (訂正註 6 件)。**実測**: 旧 1,430 行 / 192,630 字 / 主張 525 (Control 333 / Evidence 119 / Status 73) → 新 2,192 行 / 247,501 字 / 主張 1,363 (577 / 642 / 144)。前文 136 行 10,910 字 → 75 行 5,421 字。主張長違反 0、施行箇所参照なし Control 0、参照なし Evidence 0。多重集合 `ids missing=0 / tests missing=0 / files missing=0 / TOTAL missing=0`、見出し集合は 2.25 と同一。`CONTROL_MAPPING_HISTORY.md` へ 13 件 (Status へ落ちた Evidence。撤回 Control 0)。字数 +28% は Evidence の 1 観測 1 主張への分割 (119 → 642 件) が主因で、Control 軸は 120,088 → 106,271 字に減った。**検査器**: 登録テスト 56 → 58 テスト (6 退役、新 3 検査 × 現物 + fixture)、`MAX_CLAIM_LENGTH`、床 10 個を再固定 (対応表は設計 §9.5)、Known gaps 3 → 5 項 (`.md` のみの施行箇所参照、主張行以外の行長)。一度きりの道具とテスト **6 ファイルを退役** (`tools/restructure_control_mapping.py`・`tools/check_control_mapping_restructure.py`・`tools/check_control_mapping_split.py`・`tools/control_mapping_axes.tsv`・テスト 2)。**役割**: 実装担当 (Sonnet) WP-1a / WP-1b + レビュー差し戻し 6 件、起草担当 (Opus) 作業指示書 / WP-2 / WP-3 (2 並列、scratchpad の別ファイル → 監督が差し込み) / 監査是正、レビュー担当 (Opus) コードレビュー 1 回 (7 件)、監査担当 (Opus) WP-4 監査 + 再監査。逐語の数値・判定はすべて設計 **§9** にある |

## 3. 次の一手

1. 台帳の着手順は `docs/archive/docs/work-orders/HANDOVER_20260924_FABLE.md` §3 のとおり (印なし > 運用開始後)。
2. 正本と記録の分離の **第 2 段・第 3 段** (前書 §3)。
3. **R-82 先行順**の依頼者裁定待ち (前々書 §4)。
4. 3.0 以後の `CONTROL_MAPPING.md` の更新は設計 **§3** の更新規約による (文言訂正・参照更新は git が履歴、撤回と弱化だけ `CONTROL_MAPPING_HISTORY.md`)。

## 4. 依頼者判断待ち・未決 (前書 §4 に足すもの)

- 新規なし。前書 §4 の (g)(h) と、そこが引く前々書 §4 は継続。

## 5. 本チャットで足した運用上の教訓 (前書 §5 に足すもの)

1. **同一ファイルの 2 並列起草は「scratchpad の別ファイル + 監督の差し込み」で成立する** (`OPERATING_CONDITIONS.md` §1.2 の 16・17 と両立する)。
2. **起草担当は「落とさない」規律から、相互参照や案内文にまで施行箇所参照を付けて Control に残しがち。** prompt に「制御を述べていない文は削除する」を先に書く。
3. **監査の観察 (class 宣言行を指す参照、`.md` だけを引く参照) は登録テストが構造的に見ない** (設計 D-9) ので、Control の施行箇所は監査で読む。
4. **別チャットの版上げが台帳の回転規則 (6 版目を archive へ) を飛ばすことがある。** 版上げ時に版数行の本数を数える。
5. **監査の件数は主張単位、是正は参照単位で数が違う** (37 件 vs 43 件)。
6. **`mutate.py` の変異で fixture の境界長を定数から動的に算出すると、変異が緑のままになる。** リテラルで固定する。

## 裁定

| 指摘 | 裁定 | 理由 |
|---|---|---|
| 起草時の疑義 3: 前文は `MAX_BLOCK_LENGTH`・`MAX_NAMED_SUBBLOCKS` も宣言する | 直した | 作業指示書 訂正註 1 (段落ごと削除 / 据え置き文へ書き換え) |
| 起草時の疑義 4: 退役ファイルを引く正本 2 つ (`DEPROVISION_FORCED_DROP_V0_1.md`:243、登録テスト :53) | 直した | 訂正註 2 (退役註 1 行 / docstring から path 表記を除去) |
| 起草時の疑義 5: Known gaps 項目 4 (床の偽の赤) の時点付き文言 | 直した | 訂正註 3 (時点なしの形に、項目は残す) |
| 起草時の疑義 6: WP-2 / WP-3 の負荷が 1 : 2.5 | 観察 | 枠固定 (SI 範囲は依頼者指示)。WP-3 は 44 分で完走した |
| WP-2 疑義 1: Control のテスト名を同 block の Evidence へ移す | 直した (採用) | §2.1 の軸定義どおり。監督裁定 4 |
| WP-2 疑義 2: 旧 :293 を Status へ落とした | 直した | C-14 の Control へ移す (監督裁定 2) |
| WP-2 出力の相互参照・案内文に施行箇所参照を付けて Control に残した | 直した | §3 の「削除する散文」として削除 (監督裁定 1、7 行) |
| WP-3 疑義 1: `- —` の増減 (24 → 15) | 観察 | 規約は混在を禁じるだけで増減は禁じない。混在 0 |
| WP-3 疑義 4: 旧 :711 の MitateDB 側 `0013` の名前、旧 :1331 の C-13 のファイル名 | 直した | 実在するファイル名にした (多重集合は旧の名前も保つ) |
| WP-4 監査 条件 13 未充足: 主語 7 語以上 20 件・制御主体でない主語 7 件・断片 5 件・境界例 12 件 | 直した | 是正担当 (drafter) で書き直し、再監査 (§9.8) |
| WP-4 監査 W-1 / W-2: 限界文の弱化 2 件 | 直した | 逐語で復元 |
| WP-4 監査 O-1: class 宣言行を指す位置参照 37 件 | 直した | 施行する行へ付け替え (class 全体が主体のものだけ残す) |
| WP-4 監査 O-2: 設計 §6.1 の「正本 8 件を直す」前提が実測と食い違う | 観察 | 訂正註 5 で手順を落とした。設計本文は記録として残す |
| WP-4 監査 O-3: 空になった軸 3 件に対し対応表の記録 2 件 | 観察 | scratchpad の対応表の記載漏れ。判定に影響なし |
| WP-4 監査 O-4: WP-3 報告要旨の軸移動の内訳 (29) が総数 (27) と合わない | 観察 | 対応表の行 (21) が母数で整合 |
| コードレビュー 1: 設計 §9 が未記入 | 直した | WP-5 で記入 |
| コードレビュー 2: 床コメントの基点が未 commit の作業ツリー | 直した | 「version 3.0 (the R-103 change set)」で特定 (SHA は commit 前に確定しない) |
| コードレビュー 3: 検査 (2) は `.md` だけの参照も施行箇所と認める | 直した | (a) 現物の :690/:691 を Status へ、`.md` だけの Control 28 件を見直し (b) Known gaps 1 項 |
| コードレビュー 4: Evidence の file 参照抽出が (E) の逐語と部分一致で異なる (現物での差 0) | 直した | docstring に 1 行 (実測 0 件)。検査は締めない |
| コードレビュー 5: 主張行以外に長さの上限が無い | 既知の穴 (§1.12 の 71) | 製品の欠陥は通らない (前文・CCR-14・Rule は主張でない)。Known gaps 1 項 |
| コードレビュー 6: 空振りの assertion 2 つ (`too_many_named` / `block_length`) | 直した | フィールドと該当 2 項を削除 |
| コードレビュー 7: Known gaps 項目 3 の caught by が本設計を引く | 直した | 床コメントを指す形に |
| 設計 §0 「R-73 は本設計の受け入れで閉じる」だが R-73 は 2026-09-22 に閉止済み | 観察 | 訂正註 6。R-73 行に【追記】で残りの性質の消滅を記す |
| 再監査 観察 N-1: MitateDB の `mitatedbsvc_provision` の `statement_timeout` 限界が r2db と非対称 | 直した | 監督が是正 (設計 §9.7) |
| 再監査 観察 N-2: 配備の既定に依存する 3 主張 (Cloud Run の IAM 分離・環境変数の不在・`0014` 後の再起動) | 直した | 監督が是正 (設計 §9.7) |
| 再監査 観察 N-3: class 宣言行より範囲の広い 3 主張の参照 | 直した | 監督が是正 (設計 §9.7) |
| 再監査 観察 N-4: 動詞のない 2 主張 | 直した | 監督が是正 (設計 §9.7) |
| 再監査 :1301: 主語が 6 語を超える | 直した | 監督が是正 (設計 §9.7) |
