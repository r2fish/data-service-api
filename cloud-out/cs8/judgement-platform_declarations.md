# 判定表 — `r2db-api/src/r2db_api/platform_declarations.py` (基点 `092e1a1`、変更セット 8 の草案)

対象 32 塊 (基点 `092e1a1`、67 塊のうち登録 helper の中 35 を除く。既存の CH-ID 0)。spec は `cs8-spec-platform_declarations.json` (7 塊、CH-0860〜CH-0866、編集 11)。削除した文 0。判定は設計 §3、作業指示書 §16.5 の Y7-3・Y7-4 と、§10.9 の教訓 (i)〜(iii) による。「作業ツリーの状態」は spec を当てて検査器を通した時点の状態で、作業ツリーは照合後に基点へ戻した。

## A. 全塊 (対象の塊 1 つにつき 1 行。spec の `blocks` の各項目が 1 行に対応し、spec に無い行は「基準のまま」)

| # | WP | 塊 (基点の行) | qualname | 種別 | 拾った理由 (目印 / 安全 / 保護参照 / 位置 / 参照先) | spec の CH-ID | 除いた語句 (spec の `old` → `new`) | 作業ツリーの状態 (照合時) | 判定 (§3) | 根拠 | 削除前の確認 (指示語・副詞・直後の 2 文。設計 §3) | 除去後の文を読んだ判定 | 点検語 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 8 | L1-60 | `<module>` | docstring | 目印 3 文、安全、保護参照、位置、参照先 | CH-0860 | ``process_ceilings`, Phase 10 WP-6a, migration `0012`)` → ``process_ceilings`, migration `0012`)`<br>`Reference-implementation module (supervisor ruling 2026-09-05,⏎`{scratchpad}/rulings-q4-wp12-rework.md` sec.1): every name, signature and⏎` → `Reference-implementation module (`{scratchpad}/rulings-q4-wp12-rework.md`⏎sec.1): every name, signature and⏎`<br>`Peer-local, independently maintained (no cross-peer sharing, requester⏎ruling 2026-09-03) -- this module's read/validate/derive/check helpers are⏎` → `Peer-local, independently maintained (no cross-peer sharing) -- this module's⏎read/validate/derive/check helpers are⏎` | 末尾に `History: CH-0860` (作業ツリー) | 移す (括弧内の経緯トークン・裁定の日付句の機械除去)。残りは残す | 除いたのは (a) `Phase 10 WP-6a, ` (process_ceilings の括弧。追加時期で、残る文は WP-6a を指さない。L94-99 の塊が自分で `Phase 10 WP-6a` を持つ)、(b) `supervisor ruling 2026-09-05, ` (Reference-implementation module の括弧。裁定の日付句。`{scratchpad}/rulings-q4-wp12-rework.md` sec.1 は実在しない作業ノート名で経緯トークンだが、`sec.1` が断片として残るので括弧ごとは消さない)、(c) `, requester ruling 2026-09-03` (Peer-local の括弧。`no cross-peer sharing` は否定語を含む内容語なので括弧ごとは消えない)。第 1 段落の括弧の日付 `2026-09-05` は検査器が拒んだ (下の一覧)。ラベル `Q4 phase (design docs/…, work order docs/… WP-1; …):` は実在パスを含み除外 2。`WP-1` は work order の位置指定。L36-38 の「the previous (pre-rework) round … was rejected」は現在の理由 (production-only の規約を使わない) と同じ文で残す。`(D-1(b))`・`(D-2(h))`・`design §3.8`・`(F-12, D-3(f))` は設計名付きの第 1 文に寄りかかる参照で、第 1 文は残るので (i) に当たらない | 削除した文 0。点検語 `this`/`that`/`exactly`/`instead` は、除いた括弧の中身を指さない (`that convention` = string-rewrite convention、`this table` = platform_declarations) | 除去後の文を読んだ: `(`surfaces`, …; `process_ceilings`, migration `0012`)`、`Reference-implementation module (`{scratchpad}/rulings-q4-wp12-rework.md` sec.1): every name, …`、`Peer-local, independently maintained (no cross-peer sharing) -- this module's …` で文法と意味が保たれる。行の切り直しは除去に接する 2 行ずつ (L14-15、L56-57) | `this`、`that`、`those`、`instead`、`the same` |
| 2 | 8 | L75-77 | `<module>` | comment | 目印 1 文 | CH-0861 | `Peer-local (no cross-peer sharing, requester⏎#: ruling 2026-09-03).⏎` → `Peer-local (no cross-peer sharing).⏎` | `# history: CH-0861` を末尾に足した (作業ツリー) | 移す (文頭ラベル・括弧・日付句の機械除去)。残りは残す | `#:` の塊。`(no cross-peer sharing, requester ruling 2026-09-03)` から `, requester ruling 2026-09-03` だけを除いた (括弧の `no cross-peer sharing` は否定語を含む内容語)。`design §3.8` は基準から設計名が無く、本件の除去で失う参照ではない。`#:` の行頭記号は残り、3 行 → 2 行 + 参照行 | 削除した文 0。点検語は、除いたラベル・括弧・日付句を指さない (指す先は残る文・同じ塊) | 除去後の文を読んだ: `Peer-local (no cross-peer sharing).` で文法と意味が保たれる。`#:` の行は 3 → 2 (折り返しの 2 行目ごと消えた) | `this` |
| 3 | 8 | L80-84 | `<module>` | comment | 全塊走査 (拾った理由なし) | なし | (除去なし) | 基準のバイト列 (CH なし) | 残す (§3。条件を満たさない又は除くものが無い) | 経緯トークン 0。裸の ID (出所の無い条項・決定 ID) は在るが、設計・契約の決定を指す唯一の手掛かりで、除くと参照そのものを失う (設計 §10.9 の教訓)。経緯だけの文も無い (全文を読んだ)。内容の除去が 0 なので CH-ID を付けない (Y7-3 (d) 相当) | 文の削除 0 | 除去なし (基準のまま) | `this`、`the same` |
| 4 | 8 | L88-90 | `<module>` | comment | 全塊走査 (拾った理由なし) | なし | (除去なし) | 基準のバイト列 (CH なし) | 残す (§3。条件を満たさない又は除くものが無い) | 経緯トークン 0。除去の対象になる語が無く、経緯だけの文も無い (全文を読んだ。§3 残す)。内容の除去が 0 なので CH-ID を付けない (Y7-3 (d) 相当) | 文の削除 0 | 除去なし (基準のまま) | `that` |
| 5 | 8 | L94-99 | `<module>` | comment | 保護参照、位置 | なし | (除去なし) | 基準のバイト列 (CH なし) | 残す (§3。検査器が許す候補が在るが Y7-3 (b) の条件を満たさず見送った。迷えば基準のまま) | ラベル `Phase 10 WP-6a (design docs/design/PHASE10_DEPLOYMENT_EVIDENCE_V1.md D-5(ii), Q4 D-2(a)):` は実在パスを含み除外 2。括弧の `D-5(ii)`・`D-2(a)` は同じ括弧の実在パスで出所付き (§9.2 規則 4)。`Phase 10 WP-6a` は括弧の外のラベル本体で単独では消せない。経緯トークン 2 はそのまま残る | 文の削除 0 | 除去なし (基準のまま) | `that` |
| 6 | 8 | L103-105 | `<module>` | comment | 全塊走査 (拾った理由なし) | なし | (除去なし) | 基準のバイト列 (CH なし) | 残す (§3。条件を満たさない又は除くものが無い) | 経緯トークン 0。除去の対象になる語が無く、経緯だけの文も無い (全文を読んだ。§3 残す)。内容の除去が 0 なので CH-ID を付けない (Y7-3 (d) 相当) | 文の削除 0 | 除去なし (基準のまま) | `that` |
| 7 | 8 | L108-111 | `<module>` | comment | 全塊走査 (拾った理由なし) | なし | (除去なし) | 基準のバイト列 (CH なし) | 残す (§3。条件を満たさない又は除くものが無い) | 経緯トークン 0。除去の対象になる語が無く、経緯だけの文も無い (全文を読んだ。§3 残す)。内容の除去が 0 なので CH-ID を付けない (Y7-3 (d) 相当) | 文の削除 0 | 除去なし (基準のまま) | `that` |
| 8 | 8 | L114-115 | `<module>` | comment | 全塊走査 (拾った理由なし) | なし | (除去なし) | 基準のバイト列 (CH なし) | 残す (§3。条件を満たさない又は除くものが無い) | 経緯トークン 0。裸の ID (出所の無い条項・決定 ID) は在るが、設計・契約の決定を指す唯一の手掛かりで、除くと参照そのものを失う (設計 §10.9 の教訓)。経緯だけの文も無い (全文を読んだ)。内容の除去が 0 なので CH-ID を付けない (Y7-3 (d) 相当) | 文の削除 0 | 除去なし (基準のまま) | `this` |
| 9 | 8 | L118-120 | `<module>` | comment | 全塊走査 (拾った理由なし) | なし | (除去なし) | 基準のバイト列 (CH なし) | 残す (§3。条件を満たさない又は除くものが無い) | 経緯トークン 0。除去の対象になる語が無く、経緯だけの文も無い (全文を読んだ。§3 残す)。内容の除去が 0 なので CH-ID を付けない (Y7-3 (d) 相当) | 文の削除 0 | 除去なし (基準のまま) | `that` |
| 10 | 8 | L123-129 | `<module>` | comment | 目印 1 文 | なし | (除去なし) | 基準のバイト列 (CH なし) | 残す (§3。検査器が許す候補が在るが Y7-3 (b) の条件を満たさず見送った。迷えば基準のまま) | 目印 `previously`。文は「the literal env var name was previously baked … -- this constant closes that the same way `PROVISION_DSN_ENV` already does」で、経緯と現在の理由 (定数を置く理由) が同居。括弧の `rulings-q4-wp12-rework.md` は実在しない作業ノート名 (経緯トークン) だが、除くと `sec.1` が断片として残る。基準のまま | 文の削除 0 | 除去なし (基準のまま) | `this`、`that`、`those`、`the same` |
| 11 | 8 | L132-137 | `<module>` | comment | 全塊走査 (拾った理由なし) | なし | (除去なし) | 基準のバイト列 (CH なし) | 残す (§3。検査器が許す候補が在るが Y7-3 (b) の条件を満たさず見送った。迷えば基準のまま) | `(rulings-q4-wp12-rework.md sec.1: "peer 名を含む定数は対応表に載せない")` は実在しない作業ノート名 + 引用文。ノート名だけ除くと `sec.1: …` が断片として残る。文は現在の規則 (os.environ ではなく渡された env mapping を見る、同型性の対応表に載せない) を述べる。基準のまま | 文の削除 0 | 除去なし (基準のまま) | `this`、`these` |
| 12 | 8 | L145-148 | `<module>` | comment | 全塊走査 (拾った理由なし) | なし | (除去なし) | 基準のバイト列 (CH なし) | 残す (§3。条件を満たさない又は除くものが無い) | 経緯トークン 0。裸の ID (出所の無い条項・決定 ID) は在るが、設計・契約の決定を指す唯一の手掛かりで、除くと参照そのものを失う (設計 §10.9 の教訓)。経緯だけの文も無い (全文を読んだ)。内容の除去が 0 なので CH-ID を付けない (Y7-3 (d) 相当) | 文の削除 0 | 除去なし (基準のまま) | `this` |
| 13 | 8 | L213-216 | `<module>` | comment | 全塊走査 (拾った理由なし) | なし | (除去なし) | 基準のバイト列 (CH なし) | 残す (§3。条件を満たさない又は除くものが無い) | 経緯トークン 0。裸の ID (出所の無い条項・決定 ID) は在るが、設計・契約の決定を指す唯一の手掛かりで、除くと参照そのものを失う (設計 §10.9 の教訓)。経緯だけの文も無い (全文を読んだ)。内容の除去が 0 なので CH-ID を付けない (Y7-3 (d) 相当) | 文の削除 0 | 除去なし (基準のまま) | なし |
| 14 | 8 | L262-267 | `<module>` | comment | 全塊走査 (拾った理由なし) | なし | (除去なし) | 基準のバイト列 (CH なし) | 残す (§3。条件を満たさない又は除くものが無い) | 経緯トークン 0。裸の ID (出所の無い条項・決定 ID) は在るが、設計・契約の決定を指す唯一の手掛かりで、除くと参照そのものを失う (設計 §10.9 の教訓)。経緯だけの文も無い (全文を読んだ)。内容の除去が 0 なので CH-ID を付けない (Y7-3 (d) 相当) | 文の削除 0 | 除去なし (基準のまま) | `the same` |
| 15 | 8 | L338-342 | `_validate_base_url` | docstring | 全塊走査 (拾った理由なし) | なし | (除去なし) | 基準のバイト列 (CH なし) | 残す (§3。条件を満たさない又は除くものが無い) | 経緯トークン 0。裸の ID (出所の無い条項・決定 ID) は在るが、設計・契約の決定を指す唯一の手掛かりで、除くと参照そのものを失う (設計 §10.9 の教訓)。経緯だけの文も無い (全文を読んだ)。内容の除去が 0 なので CH-ID を付けない (Y7-3 (d) 相当) | 文の削除 0 | 除去なし (基準のまま) | `this` |
| 16 | 8 | L351-356 | `_validate_base_url` | comment | 全塊走査 (拾った理由なし) | なし | (除去なし) | 基準のバイト列 (CH なし) | 残す (§3。条件を満たさない又は除くものが無い) | 経緯トークン 0。除去の対象になる語が無く、経緯だけの文も無い (全文を読んだ。§3 残す)。内容の除去が 0 なので CH-ID を付けない (Y7-3 (d) 相当) | 文の削除 0 | 除去なし (基準のまま) | `that`、`otherwise` |
| 17 | 8 | L420-432 | `<module>` | comment | 保護参照 | CH-0862 | `# F-15 (Phase 10 WP-6a, design D-5(ii)):` → `# F-15 (design D-5(ii)):` | `# history: CH-0862` を末尾に足した (作業ツリー) | 移す (文頭ラベル・括弧・日付句の機械除去)。残りは残す | F-15 は保護 ID (F-ID) でラベルは除外 2。括弧 `(Phase 10 WP-6a, design D-5(ii))` に出所語は無く (`design` は種類語)、`Phase 10 WP-6a, ` だけを除いた。残る文は `work order WP-6a's own §3 D-5(ii) reading` と自分で位置を指すので、ラベルの `WP-6a` に寄りかからない (Y7-3 (b))。`design D-5(ii)` は残した | 削除した文 0。点検語は、除いたラベル・括弧・日付句を指さない (指す先は残る文・同じ塊) | 除去後の文を読んだ: `# F-15 (design D-5(ii)): the `process_ceilings` row -- one combined check …` で文法と意味が保たれる | `the same` |
| 18 | 8 | L561-569 | `<module>` | comment | 全塊走査 (拾った理由なし) | なし | (除去なし) | 基準のバイト列 (CH なし) | 残す (§3。条件を満たさない又は除くものが無い) | 経緯トークン 0。裸の ID (出所の無い条項・決定 ID) は在るが、設計・契約の決定を指す唯一の手掛かりで、除くと参照そのものを失う (設計 §10.9 の教訓)。経緯だけの文も無い (全文を読んだ)。内容の除去が 0 なので CH-ID を付けない (Y7-3 (d) 相当) | 文の削除 0 | 除去なし (基準のまま) | `such`、`instead` |
| 19 | 8 | L607-615 | `<module>` | comment | 全塊走査 (拾った理由なし) | なし | (除去なし) | 基準のバイト列 (CH なし) | 残す (§3。条件を満たさない又は除くものが無い) | 経緯トークン 0。裸の ID (出所の無い条項・決定 ID) は在るが、設計・契約の決定を指す唯一の手掛かりで、除くと参照そのものを失う (設計 §10.9 の教訓)。経緯だけの文も無い (全文を読んだ)。内容の除去が 0 なので CH-ID を付けない (Y7-3 (d) 相当) | 文の削除 0 | 除去なし (基準のまま) | `this`、`that` |
| 20 | 8 | L685-692 | `_role_setting_rows` | docstring | 保護参照 | CH-0863 | `(design D-1(c) amendment 2026-09-05)` → `(design D-1(c) amendment)` | 末尾に `History: CH-0863` (作業ツリー) | 移す (文頭ラベル・括弧・日付句の機械除去)。残りは残す | `(design D-1(c) amendment 2026-09-05)` から純粋な日付だけを除いた (Y7-3 (a))。`amendment` は内容語で残る。同じ塊の `design §1.5 finding 6`・`F-11's own per-database override` は基準のまま | 削除した文 0。点検語は、除いたラベル・括弧・日付句を指さない (指す先は残る文・同じ塊) | 除去後の文を読んだ: `(design D-1(c) amendment), never every database on the cluster.` で文法と意味が保たれる | `this`、`that` |
| 21 | 8 | L790-835 | `<module>` | comment | 保護参照 | なし | (除去なし) | 基準のバイト列 (CH なし) | 残す (§3。検査器が許す候補が在るが Y7-3 (b) の条件を満たさず見送った。迷えば基準のまま) | ラベル `Contract 1.7.0 (design docs/design/PHASE9_…_V1.md D-1/D-6/D-5, work order §2 WP-2e F-3, `{scratchpad}/rulings-r3-r7-flip.md` F-3, WP-2e rework `{scratchpad}/audit-wp2e.md` D-2, ruling L-2 = (A)):` は版数付き文書名と実在パスを含み除外 2。括弧の `WP-2e` は `work order §2 WP-2e F-3` の位置指定で、`{scratchpad}/…` (実在しない) を除くと `F-3`・`D-2` が断片として残る。第 2 段落 (`The pre-rework … had exactly that flaw (audit finding D-2)`) は経緯の叙述だが、F-14 が死んだ検査だった理由 = 今の 3 検査の形の理由で、`PlatformDeclarationError(code="F-14")` (F-ID) を含み 0d で丸ごと消せない。`(b) M-7 (`{scratchpad}/audit-wp2e-2.md` R-7)` も同じ。基準のまま | 文の削除 0 | 除去なし (基準のまま) | `this`、`that`、`the same` |
| 22 | 8 | L900-901 | `<module>` | comment | 全塊走査 (拾った理由なし) | なし | (除去なし) | 基準のバイト列 (CH なし) | 残す (§3。条件を満たさない又は除くものが無い) | 経緯トークン 0。裸の ID (出所の無い条項・決定 ID) は在るが、設計・契約の決定を指す唯一の手掛かりで、除くと参照そのものを失う (設計 §10.9 の教訓)。経緯だけの文も無い (全文を読んだ)。内容の除去が 0 なので CH-ID を付けない (Y7-3 (d) 相当) | 文の削除 0 | 除去なし (基準のまま) | なし |
| 23 | 8 | L904-905 | `<module>` | comment | 全塊走査 (拾った理由なし) | なし | (除去なし) | 基準のバイト列 (CH なし) | 残す (§3。条件を満たさない又は除くものが無い) | 経緯トークン 0。裸の ID (出所の無い条項・決定 ID) は在るが、設計・契約の決定を指す唯一の手掛かりで、除くと参照そのものを失う (設計 §10.9 の教訓)。経緯だけの文も無い (全文を読んだ)。内容の除去が 0 なので CH-ID を付けない (Y7-3 (d) 相当) | 文の削除 0 | 除去なし (基準のまま) | なし |
| 24 | 8 | L909-952 | `<module>` | comment | 目印 1 文、安全、保護参照、位置、参照先 | CH-0864 | `# F-16 (Phase 10 WP-4f, supervisor ruling 2026-09-09, following the WP-4e⏎# conformance investigation's own finding -- see that WP's report): every⏎` → `# F-16 (following the WP-4e conformance investigation's own finding -- see⏎# that WP's report): every⏎` | `# history: CH-0864` を末尾に足した (作業ツリー) | 移す (文頭ラベル・括弧・日付句の機械除去)。残りは残す | F-16 は保護 ID でラベルは除外 2。括弧 `(Phase 10 WP-4f, supervisor ruling 2026-09-09, following the WP-4e conformance investigation's own finding -- see that WP's report)` から `Phase 10 WP-4f, supervisor ruling 2026-09-09, ` を除いた (CS6 CH-0512 と同じ裁定の日付句 + 追加時の WP)。残る `WP-4e` は `WP-4e's own measured … finding`・`see that WP's report` が指すので残す。`(measured 2026-09-10, WP-4 integration review M-1)` は日付だけ除くと `measured,` が宙に残るので基準のまま (CS6 A3 の `L-3 correction, WP-4 integration review 2026-09-10` と同じ扱い)。`(rulings-q4-writer-roles.md, rejected alternative (a))` のノート名は `(a)` の指す先なので除かない | 削除した文 0。点検語は、除いたラベル・括弧・日付句を指さない (指す先は残る文・同じ塊) | 除去後の文を読んだ: `# F-16 (following the WP-4e conformance investigation's own finding -- see # that WP's report): every PostgreSQL role …` で文法と意味が保たれる。切り直しは除去に接する 2 行 | `this`、`that`、`instead`、`also`、`otherwise`、`the same` |
| 25 | 8 | L954-957 | `<module>` | comment | 全塊走査 (拾った理由なし) | なし | (除去なし) | 基準のバイト列 (CH なし) | 残す (§3。条件を満たさない又は除くものが無い) | 経緯トークン 0。除去の対象になる語が無く、経緯だけの文も無い (全文を読んだ。§3 残す)。内容の除去が 0 なので CH-ID を付けない (Y7-3 (d) 相当) | 文の削除 0 | 除去なし (基準のまま) | なし |
| 26 | 8 | L960-964 | `<module>` | comment | 安全、位置、参照先 | なし | (除去なし) | 基準のバイト列 (CH なし) | 残す (§3。検査器が許す候補が在るが Y7-3 (b) の条件を満たさず見送った。迷えば基準のまま) | `(WP-4e's own investigated-and-reverted default, `build_control_app`'s own comment)` は所有格の位置指定で `control_main.py` の塊 (CS6 CH-0509) を指す。括弧は内容語を含み、`WP-4e` を除くと指す先を失う (Y7-3 (b))。基準のまま | 文の削除 0 | 除去なし (基準のまま) | なし |
| 27 | 8 | L967-970 | `<module>` | comment | 全塊走査 (拾った理由なし) | なし | (除去なし) | 基準のバイト列 (CH なし) | 残す (§3。条件を満たさない又は除くものが無い) | 経緯トークン 0。除去の対象になる語が無く、経緯だけの文も無い (全文を読んだ。§3 残す)。内容の除去が 0 なので CH-ID を付けない (Y7-3 (d) 相当) | 文の削除 0 | 除去なし (基準のまま) | なし |
| 28 | 8 | L1025-1027 | `<module>` | comment | 全塊走査 (拾った理由なし) | なし | (除去なし) | 基準のバイト列 (CH なし) | 残す (§3。条件を満たさない又は除くものが無い) | 経緯トークン 0。除去の対象になる語が無く、経緯だけの文も無い (全文を読んだ。§3 残す)。内容の除去が 0 なので CH-ID を付けない (Y7-3 (d) 相当) | 文の削除 0 | 除去なし (基準のまま) | `this` |
| 29 | 8 | L1037-1089 | `check_role_connection_limits` | docstring | 目印 1 文、安全、保護参照、位置、参照先 | CH-0865 | `    design D-3 (5): `role_pool_size(thread_limit)`⏎` → `    `role_pool_size(thread_limit)`⏎`<br>``pool_size * process_ceilings.data`, one store each, Phase 10 WP-8a).` → ``pool_size * process_ceilings.data`, one store each).`<br>`    Phase 10 WP-4g (supervisor ruling 2026-09-09): `role_classes`/⏎` → `    Phase 10 WP-4g: `role_classes`/⏎` | 末尾に `History: CH-0865` (作業ツリー) | 移す (文頭ラベル・括弧・日付句の機械除去)。残りは残す | 3 編集: (a) 第 2 段落のラベル `design D-3 (5): ` (設計名の無い裸の ID。CS7 CH-0600 `design D-3 (1): ` と同形。残る段落は `role_pool_size` と `rolconnlimit` の乗算の理由を自分で述べ、`D-3` を名指ししない)、(b) `, Phase 10 WP-8a` (floor の括弧。追加時期)、(c) `(supervisor ruling 2026-09-09)` (括弧ごと。CS6 CH-0509 と同形)。第 4 段落のラベル `Phase 10 WP-4g` は残す: 同じ段落の `(added this WP)` が指す (i)。`0013_role_connection_limits.sql` は実在パスで残る。MitateDB の対の docstring (CH-0550) は `design docs/design/MULTI_PROCESS_WORKER_V0_1.md D-3 (5):` と設計名付きで、こちらには設計名が無い点を 17.5 に挙げた | 削除した文 0。点検語 `this`/`that`/`exactly`/`also` は除いたラベル・括弧を指さない (`this function`、`this check`、`ITS OWN`) | 除去後の文を読んだ: 第 2 段落は `` `role_pool_size(thread_limit)` sizes ONE process' own pool; … `` で始まり文法と意味が保たれる。`(floor = `pool_size * process_ceilings.data`, one store each).`、`Phase 10 WP-4g: `role_classes`/`application_slugs` let a caller …` も同じ | `this`、`that`、`these`、`instead`、`still`、`the same` |
| 30 | 8 | L1093-1101 | `check_role_connection_limits` | comment | 安全、位置 | CH-0866 | `# M-1 (WP-4 integration review 2026-09-10): a role` → `# M-1 (WP-4 integration review): a role` | `# history: CH-0866` を末尾に足した (作業ツリー) | 移す (文頭ラベル・括弧・日付句の機械除去)。残りは残す | `M-1 (WP-4 integration review 2026-09-10)` から純粋な日付だけを除いた。ラベル `M-1 (WP-4 integration review)` は残す: module header (L909-952) の `(measured 2026-09-10, WP-4 integration review M-1)` が同じ指摘を名指しする | 削除した文 0。点検語は、除いたラベル・括弧・日付句を指さない (指す先は残る文・同じ塊) | 除去後の文を読んだ: `# M-1 (WP-4 integration review): a role can legitimately match MORE than one …` で文法と意味が保たれる | `that`、`instead` |
| 31 | 8 | L1224-1257 | `<module>` | comment | 全塊走査 (拾った理由なし) | なし | (除去なし) | 基準のバイト列 (CH なし) | 残す (§3。条件を満たさない又は除くものが無い) | 経緯トークン 0。裸の ID (出所の無い条項・決定 ID) は在るが、設計・契約の決定を指す唯一の手掛かりで、除くと参照そのものを失う (設計 §10.9 の教訓)。経緯だけの文も無い (全文を読んだ)。内容の除去が 0 なので CH-ID を付けない (Y7-3 (d) 相当) | 文の削除 0 | 除去なし (基準のまま) | `this`、`that`、`these`、`the same` |
| 32 | 8 | L1547-1550 | `<module>` | comment | 全塊走査 (拾った理由なし) | なし | (除去なし) | 基準のバイト列 (CH なし) | 残す (§3。条件を満たさない又は除くものが無い) | 経緯トークン 0。除去の対象になる語が無く、経緯だけの文も無い (全文を読んだ。§3 残す)。内容の除去が 0 なので CH-ID を付けない (Y7-3 (d) 相当) | 文の削除 0 | 除去なし (基準のまま) | `these` |

行数: 対象の塊 32 (spec に入れた塊 7、編集 11、削除した文 0)。

## B. 目印一覧に当たる文 (対象の塊だけ。設計 §3 の叙述の目印)

| # | WP | 塊 (基点の行) | CH-ID | 目印 | 文 (先頭の数語) | 作業ツリーの状態 | 判定 (§3) | 根拠 | 点検語 | A の行 |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 8 | L1-60 | CH-0860 | `supervisor ruling` | `Reference-implementation module (supervisor ruling 2026-09-05, `{scratchpad}/rulings-q4-wp…` | ラベル・括弧・日付句の除去のみ (文は残る) | 残す | 文は残す (同居文)。除去は経緯トークン・ラベル・日付句の機械除去だけで、この文の削除は無い | `this`、`that`、`those`、`instead`、`the same` | 1 |
| 2 | 8 | L1-60 | CH-0860 | `was rejected` | ``current_user`-based role identification, NOT naming-convention-derived role names (ruling…` | ラベル・括弧・日付句の除去のみ (文は残る) | 残す | 文は残す (同居文)。除去は経緯トークン・ラベル・日付句の機械除去だけで、この文の削除は無い | `this`、`that`、`those`、`instead`、`the same` | 1 |
| 3 | 8 | L1-60 | CH-0860 | `requester ruling` | `Peer-local, independently maintained (no cross-peer sharing, requester ruling 2026-09-03) …` | ラベル・括弧・日付句の除去のみ (文は残る) | 残す | 文は残す (同居文)。除去は経緯トークン・ラベル・日付句の機械除去だけで、この文の削除は無い | `this`、`that`、`those`、`instead`、`the same` | 1 |
| 4 | 8 | L75-77 | CH-0861 | `requester ruling` | `Peer-local (no cross-peer sharing, requester ruling 2026-09-03).…` | ラベル・括弧・日付句の除去のみ (文は残る) | 残す | 文は残す (同居文)。除去は経緯トークン・ラベル・日付句の機械除去だけで、この文の削除は無い | `this` | 2 |
| 5 | 8 | L123-129 | なし | `previously` | `F-6's own env var name -- referenced by bare name from `_f6_forward_message`/`_f6_reverse_…` | 基準のまま | 残す | 基準のまま。文は現在の理由・規則と同居する叙述で、削除しない | `this`、`that`、`those`、`the same` | 10 |
| 6 | 8 | L909-952 | CH-0864 | `supervisor ruling` | `--------------------------------------------------------------------------- F-16 (Phase 10…` | ラベル・括弧・日付句の除去のみ (文は残る) | 残す | 文は残す (同居文)。除去は経緯トークン・ラベル・日付句の機械除去だけで、この文の削除は無い | `this`、`that`、`instead`、`also`、`otherwise`、`the same` | 24 |
| 7 | 8 | L1037-1089 | CH-0865 | `this WP`、`supervisor ruling` | `Phase 10 WP-4g (supervisor ruling 2026-09-09): `role_classes`/`application_slugs` let a ca…` | ラベル・括弧・日付句の除去のみ (文は残る) | 残す | 文は残す (同居文)。除去は経緯トークン・ラベル・日付句の機械除去だけで、この文の削除は無い | `this`、`that`、`these`、`instead`、`still`、`the same` | 29 |

目印に当たる文 7 / 塊 5。

## C. 経緯と同じ文にある安全上の理由・保護参照・位置 (経緯トークンを含む文のうち §14.2 の正規表現に当たるもの)

| # | WP | 塊 | CH-ID | 種別 | 語 (安全) / 保護参照 / 位置の語 | 作業ツリーの状態 | 判定 (§3) | 根拠 (その塊の安全上の理由・保護参照が残ること) | A の行 |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 8 | L1-60 | CH-0860 | 安全、保護参照、位置 | 安全: role, timeout; 保護参照 2 文; 位置: below | ラベル・括弧・日付句の除去のみ | 残す (文は削除しない) | 同居文は消さない。SI-10・F-12・`PlatformDeclarationError` の fail-fast の文、`check_writer_role_timeouts` の同一接続の理由、実在パス 2 本は逐語で残る | 1 |
| 2 | 8 | L94-99 | なし | 保護参照、位置 | 保護参照 1 文; 位置: above | 基準のまま | 残す (文は削除しない) | 基準のまま (塊に除去なし) | 5 |
| 3 | 8 | L420-432 | CH-0862 | 保護参照 | 保護参照 1 文 | ラベル・括弧・日付句の除去のみ | 残す (文は削除しない) | 同居文は消さない。除いたのは経緯トークン・ラベル・日付句だけで、安全上の語・保護参照・位置の語を含む文は逐語で残る (検査器 `--base` exit 0) | 17 |
| 4 | 8 | L685-692 | CH-0863 | 保護参照 | 保護参照 1 文 | ラベル・括弧・日付句の除去のみ | 残す (文は削除しない) | 同居文は消さない。除いたのは経緯トークン・ラベル・日付句だけで、安全上の語・保護参照・位置の語を含む文は逐語で残る (検査器 `--base` exit 0) | 20 |
| 5 | 8 | L790-835 | なし | 保護参照 | 保護参照 1 文 | 基準のまま | 残す (文は削除しない) | 安全 (fail-closed per-application) と保護参照 (版数付き文書名、実在パス、F-14) は基準のまま | 21 |
| 6 | 8 | L909-952 | CH-0864 | 安全、保護参照、位置 | 安全: role; 保護参照 1 文; 位置: below | ラベル・括弧・日付句の除去のみ | 残す (文は削除しない) | 安全 (`CONNECTION LIMIT`、role の識別を文字列書き換えで行わない理由、`r2dbsvc_control` の明示除外) と `0007/0006` の実在ファイル名は逐語で残る | 24 |
| 7 | 8 | L960-964 | なし | 安全、位置 | 安全: credentials; 位置: above | 基準のまま | 残す (文は削除しない) | 基準のまま (塊に除去なし) | 26 |
| 8 | 8 | L1037-1089 | CH-0865 | 安全、保護参照、位置 | 安全: role; 保護参照 1 文; 位置: above | ラベル・括弧・日付句の除去のみ | 残す (文は削除しない) | 安全 (`CONNECTION LIMIT`、role 識別、floor の乗算) と F-16 は逐語で残る | 29 |
| 9 | 8 | L1093-1101 | CH-0866 | 安全、位置 | 安全: role; 位置: below | ラベル・括弧・日付句の除去のみ | 残す (文は削除しない) | 安全 (`_table_owner` の除外、owner ACL) は逐語で残る | 30 |

安全 / 保護参照 / 位置 の塊: 5 / 7 / 6 (文: 7 / 8 / 6)。

## 参照先一覧

### 塊をまたぐ参照 (module の中。§13.2 の正規表現 + `'s identical comment` / `own (comment|docstring|paragraph)` / `identical(-purpose) comment` に当たる文。同じ塊の中を指す文も含む)

| # | 参照元の塊 (基点の行) | CH-ID | 語 | 文 (先頭の数語) | 参照元の塊の状態 |
|---|---|---|---|---|---|
| 1 | L1-60 | CH-0860 | `below` | `Reference-implementation module (supervisor ruling 2026-09-05, `{scratchpad}/rulings-q4-wp12-rework.…` | 除去あり (文は残る) |
| 2 | L1-60 | CH-0860 | `below` | `A handful of message-building helpers below (`_f1_message`/`_f2_message`/`_f8_message`/`_f13_message…` | 除去あり (文は残る) |
| 3 | L94-99 | なし | `above` | `Phase 10 WP-6a (design docs/design/PHASE10_DEPLOYMENT_EVIDENCE_V1.md D-5(ii), Q4 D-2(a)): the platfo…` | 基準のまま |
| 4 | L262-267 | なし | `below` | `Both write (`ops declare-*`) and read paths call the SAME `validate_*` functions below (design D-2(d…` | 基準のまま |
| 5 | L420-432 | CH-0862 | `below` | `The row-existence check (inlined directly in `read_platform_declarations` below, as `"process_ceilin…` | 除去あり (文は残る) |
| 6 | L561-569 | なし | `above` | `Data-plane only -- the control-plane process has no such env var to cross-check against (it uses `re…` | 基準のまま |
| 7 | L790-835 | なし | `above` | ``check_contract_170_declarations` replaces it with three checks, only the third of which is genuinel…` | 基準のまま |
| 8 | L909-952 | CH-0864 | `above` | `Runtime/developer role names, unlike the platform-plane roles above, ARE read directly off `<schema>…` | 除去あり (文は残る) |
| 9 | L909-952 | CH-0864 | `below` | `This is an EXPLICIT exclusion (`_table_owner`, below), not merely "no grants match its identity" -- …` | 除去あり (文は残る) |
| 10 | L960-964 | なし | `above`, `own comment` | ``r2db_api.control_main`'s own 4 platform-plane stores (`applications`/`credentials`/`control_credent…` | 基準のまま |
| 11 | L1025-1027 | なし | `below` | `The three platform-plane role classes `check_role_connection_limits` knows how to identify -- a call…` | 基準のまま |
| 12 | L1037-1089 | CH-0865 | `below` | `F-16: raises `PlatformDeclarationError(code="F-16")` for the FIRST role (in the deterministic order …` | 除去あり (文は残る) |
| 13 | L1037-1089 | CH-0865 | `above` | `Checks exactly the role classes `0013_role_connection_limits.sql` (this peer) / the sibling peer's o…` | 除去あり (文は残る) |
| 14 | L1037-1089 | CH-0865 | `above` | `A role with no grants matching any of the three platform-plane shapes above (identity unknown to thi…` | 除去あり (文は残る) |
| 15 | L1093-1101 | CH-0866 | `below` | `M-1 (WP-4 integration review 2026-09-10): a role can legitimately match MORE than one platform-plane…` | 除去あり (文は残る) |
| 16 | L1093-1101 | CH-0866 | `above` | ``_table_owner` exclusion keeps the table-owning operator role (`r2dbsvc_control`, never a real poole…` | 除去あり (文は残る) |
| 17 | L1224-1257 | なし | `above` | `--------------------------------------------------------------------------- F-18 (R-91, work order d…` | 基準のまま |

参照の語を含む文: 17。

### module の外からの参照先 (両 peer の `src/`・`tests/`・`conformance/`、`conformance-tests/`、`security/`、README を grep し、手で選別した)

| # | 参照元 (`file:line`) | 参照の語 | 参照先の塊 (基点の行) | 参照先の文 (先頭の数語) | 残っているか (作業ツリー) |
|---|---|---|---|---|---|
| 1 | `r2db-api/conformance/real_server_r2db.py:528` | below `check_role_connection_limits`'s own floor of 64 | L1037-1089 (CH-0865) | `F-16: raises `PlatformDeclarationError(code="F-16")` for the FIRST role …` (floor の説明) | はい (ラベル・括弧・日付句の除去のみ。floor の文は逐語) |
| 2 | `r2db-api/tests/test_application_audit.py:2848` | claim `check_writer_role_timeouts`'s own docstring makes (design D-1(c)) | L761-777 (登録 helper の中。対象外) | `check_writer_role_timeouts` の docstring | はい (触らない) |
| 3 | `r2db-api/src/r2db_api/credential_store.py:1387` | `r2db_api.platform_declarations.check_writer_role_timeouts` | L761-777 (登録 helper。関数を指し、コメントではない) | — | はい (触らない) |
| 4 | `r2db-api/tests/test_process_ceilings_declaration.py:839-840` | `inspect.getsource(getattr(pd, name))` に `"os.environ" not in`・`"getenv" not in` | `validate_process_ceilings_value` (L466-485)・`read_platform_declarations` (L500-535)。登録 helper の中 (対象外) | 文字列検査 (`not in`)。設計 §5 (b) | はい (触らない。完了条件 10 (a) の変異先) |
| 5 | `security/CONTROL_MAPPING.md:700/701/766/773/781-788/790/1872/1874/1960-1964` | 位置参照 20 件 + 続きの形 2 件 (`:1369`・`:1346`) | L1168、L1152、L499、L465、L1031、L1108、L1260、L1369、L1346、L1515、L1584、L748 (コード行) | — | 引き直す対象 (repull.py: `changed 22, unresolved 0`) |
| 6 | (逆向き) L80-84・L960-964・L1037-1089 → `r2db-api/src/r2db_api/control_main.py` | `r2db_api.control_main`'s own `R2DB_PLATFORM_SCHEMA`、`build_control_app`'s own comment、`control_main`'s own startup fail-fast calls | CS6 §14.2 の参照表 (L1-194、L442-483、L561-573 を指す) | 本 module から出る参照で、文は逐語で残る | はい |

## 検査器が拒んだ除去 (spec から外し、塊は基準のまま)

| # | 塊 (基点の行) | 試した除去 (`old` → `new`) | 検査器の行 (逐語) | 扱い |
|---|---|---|---|---|
| 1 | L1-60 (CH-0860) | `rework round, supervisor rulings 2026-09-05 -- rulings-q4-wp12-rework.md` → `rework round, supervisor rulings -- rulings-q4-wp12-rework.md` (第 1 段落の括弧の日付) | `FAIL (§4.1 (3)) r2db-api/src/r2db_api/platform_declarations.py:1 cannot delete a whole sentence carrying a protected reference: 'Q4 phase (design docs/design/Q4_DB_SIDE_SINGLE_TRUTH_V1.md D-1/D-2, …):'` | spec から外し、第 1 段落は基準のまま (日付 1 つが残る)。実在パスを持つ括弧の中で ` -- ` に接する日付の除去を (4) が導けないため |

## 見送った除去 (検査器は許す可能性があるが、Y7-3 (b) 又は (i)〜(iii) の型で基準のまま残した)

| # | 塊 (基点の行) | 候補の除去 | 型 | 根拠 |
|---|---|---|---|---|
| 1 | L1-60 | `Reference-implementation module (…)` のラベルごとの除去 (条件 1〜3 は満たしうる) | (iii) | ラベルの内容語 `Reference-implementation module` が塊の主題。括弧の日付句だけを除いた |
| 2 | L94-99 | なし (除ける語が無い) | — | 実在パスの括弧 (§9.2 規則 4) |
| 3 | L123-129 | `rulings-q4-wp12-rework.md` (実在しない作業ノート名) | 断片 | `sec.1` が残る |
| 4 | L420-432 | `(design D-5(ii))` の括弧ごと (規則 3 で導けうる) | (i) | 残る文の `work order WP-6a's own §3 D-5(ii) reading` が同じ条項を引く。設計の手掛かりを残した |
| 5 | L909-952 | `(measured 2026-09-10, WP-4 integration review M-1)` の日付 | 断片 | `measured,` が宙に残る (CS6 A3 と同じ扱い) |
| 6 | L909-952 | `rulings-q4-writer-roles.md` (実在しない作業ノート名) | 指示先 | `rejected alternative (a)` の `(a)` の指す先 |
| 7 | L960-964 | `WP-4e's own …` | Y7-3 (b) | 所有格の位置指定 (control_main.py の塊を指す) |
| 8 | L1037-1089 | ラベル `Phase 10 WP-4g` (第 4 段落) | (i) | 同じ段落の `(added this WP)` が指す |
| 9 | L1093-1101 | ラベル `M-1 (WP-4 integration review): ` ごと | (iii)/参照 | module header が `WP-4 integration review M-1` と名指しする |

## 指示語チェックの候補一覧 (削除した文 1 つにつき 1 行)

| # | WP | 塊 (基点の行) | 削除した文 | 直後の残す文 1 | 直後の残す文 2 | 点検語の参照 | 結果 |
|---|---|---|---|---|---|---|---|
| — | 8 | (該当なし) | 操作 (3) による文の削除は 0 文 (spec の `new` が空の編集も無い) | — | — | — | — |

## HTTP の status・error code を含む削除文の監査一覧

| # | WP | 塊 | 削除した文 | 含む語 | 判定表の根拠 |
|---|---|---|---|---|---|
| — | 8 | (該当なし) | 削除した文は 0 文 | — | — |

## 0d の保護参照があるために残った、経緯だけの文

| # | WP | 塊 (行) | 文 (先頭の数語) | 保護参照 | 状態 |
|---|---|---|---|---|---|
| 1 | 8 | L1-60 (第 1 段落) | `Q4 phase (design docs/design/Q4_DB_SIDE_SINGLE_TRUTH_V1.md D-1/D-2, work order docs/… WP-1; rework round, supervisor rulings 2026-09-05 -- rulings-q4-wp12-rework.md sec.1, …):` | 実在パス 2 本 | 基準のまま (日付 2026-09-05 の除去は検査器が拒んだ) |
| 2 | 8 | L790-835 (第 1 文) | `Contract 1.7.0 (design docs/design/PHASE9_…_V1.md D-1/D-6/D-5, work order §2 WP-2e F-3, …): a new `ops verify-declarations` check …` | 版数付き文書名、実在パス、F-3 | 基準のまま |

## 訂正の記録 (0g)

該当なし (この草案は受け皿に訂正の記録を足していない)。

