# 引き継ぎ書 — 2026-10-04 R-122 の閉止 (MitateDB socket 隔離面の control URL)

本書は作業機の監督チャット (Fable) の記録である。依頼は「台帳 R-122 (規模 S) に着手し、枠決めから実装・レビュー・受け入れ・commit まで一気通貫で行う」(依頼者 2026-10-04) と、それに続く指示 (裁定の了承、worktree の畳み込み、本書) である。§1 の値は記載の commit の時点の記録であり、現在地は `docs/work-orders/OPERATING_CONDITIONS.md` (以下 `OC`) §1.8 の 55a の出所から読む。

## 1. 現在地 (2026-10-04、local main `d936c5a` の時点の記録)

- local main は `d936c5a`。GitHub へは送信していない (`OC` §2 の 20)。先頭 commit の件名には `[skip ci]` が付いている (文書だけの確認の記録)。未送信の範囲には本チャットのコード変更 (`33b7364`) と、別チャットの `.github/workflows/ci.yml` の変更が含まれる。
- 台帳は v1.167 (v1.166 = R-122 の閉止、v1.167 = 依頼者の事後確認)。`tools/dev/ledger.py --open` は open=18。
- 契約・`security/CONTROL_MAPPING.md`・`conformance-tests/CONDITIONS.md`・`conformance-tests/COLLECTION_FLOOR` は本チャットで変えていない。
- 完了ゲート (監督、main `2a3b65a` + 本変更の worktree の上): gate: 5232 passed, 2 subtests passed in 767.53s (0:12:47), judge=PASS, label r122, pg_database/pg_roles diff 0。ゲートの後に main は別チャットの変更 (CI の runner の固定、引き継ぎ書、`OC`) で進んでおり、merge 後の main では回し直していない (触るファイルの重なり 0)。
- worktree: 本チャットに割り当てられた worktree と branch は `tools/dev/fold.py --apply` で畳んだ。本書の commit に使った worktree `ho-r122` は merge 後に畳む対象である。

## 2. 本チャットで閉じたもの

### 2.1 R-122 (規模 S、Class C。commit `33b7364`、merge `b994db1`)

- 欠陥: MitateDB の socket plug の isolated copy は control の port を新しく予約して自分の文書に宣言するが、その port で応答する surface はどの経路でも作られなかった。
- 再現 (修正前、test だけを書き換えて実行): `pt: 1 failed, 3 passed, 33 deselected`。赤は `test_socket_redirect_location_keeps_the_declared_authority[control-MitateDB-api-socket]` だけ (`httpx.ReadTimeout`)。r2db の socket plug は緑で該当しない。
- 是正: `MitateDB-api/conformance/conformance_adapter_mitatedb_socket.py` の `_reset_surface_state` は control の予約を reset せず、親の control surface を isolated copy の registry に引き継ぐ (台帳行の候補 (i))。isolated surface の文書は親の control URL を宣言する。
- test: `conformance-tests/test_wire_entry.py::test_socket_redirect_location_keeps_the_declared_authority` の control 側は、isolated surface 自身の文書から URL を取る形に戻した。
- 完了条件 → 変異: 「isolated surface の文書が宣言する control base URL への dial が応答する (socket の 2 plug)」→ `M1-reset-control-reservation` (reset を戻す) `expect=red got=red OK | 1 failed, 3 passed | restore=ok`。修正後は `conformance-tests/test_wire_entry.py conformance-tests/test_socket_harness.py` が `pt: 82 passed`。
- レビュー: コードレビュー 1 回 (Class C の経路)。監査担当は起動していない (`OC` §1.13 の 74)。
- 記録: 台帳の記録ファイル `docs/archive/docs/design/ROADMAP_POST_PHASE7_V1__LEDGER_CLOSED.md` の R-122 の節。

### 2.2 依頼者の事後確認 (commit `58f986b`、merge `d936c5a`)

依頼者 (逐語): 「裁定 5 件を了承します」。台帳 v1.167 と記録ファイルの R-122 の節に記録した。

## 3. 次の一手

- 着手できる行は `tools/dev/ledger.py --open` で選ぶ (着手条件の欄が `-` の行)。本チャットから持ち越した作業は無い。
- 送信するときは `OC` §2 の 20・21 に従う。未送信の範囲に Class A 以外の変更があるので、21 の (a)(b)(c) が要る。

## 4. 依頼者判断待ち・未決

なし。

## 5. 運用上の教訓

- 別チャットの完了ゲートが排他ロックを持っているとき、`tools/dev/pt.py` は既定で即 REFUSED を返す。`--wait 1800` を付けて背景で走らせれば、迂回せずに待てる (今回の待ちは約 13 分)。
- 「修正前に赤」を取るまで修正を作業ツリーに入れない。待ち受け中の実行は、ロックが取れた時点のファイルを読む。
- `tools/dev/fold.py` は `-C` が指す worktree を畳まない。自分の worktree を畳むときは main checkout の道具を `-C <main checkout>` で呼び、`claude/*` の branch は `--include` で、24 時間未満なら `--min-age-hours 0` で対象にする。先に dry-run で対象が 1 件だけであることを見る。

## 6. 裁定

| 指摘 | 裁定 | 理由 |
|---|---|---|
| レビュー 1: isolated copy で `_build_client(_control_app, ...)` が呼ばれると親の port に 2 本目の surface を作る形が残る (届く経路は無い) | 直した | 親の surface を registry に引き継ぎ、面そのものを共有する形にした |
| レビュー 2: `_surfaces_value` の docstring が isolated copy での呼び出しを書いていない | 直した | 追記した |

監督裁定 5 件 (候補 (i) の採用、test の回避を戻す、レビュー 1 の直し方、`security/CONTROL_MAPPING.md` と `conformance-tests/CONDITIONS.md` を変えない、完了ゲートは merge 前の worktree で 1 回) は依頼者が 2026-10-04 に了承した (§2.2)。
