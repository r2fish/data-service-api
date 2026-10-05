# 変更セット 9 判定表 — `MitateDB-api/src/mitatedb_api/platform_declarations.py` (草案)

基点 `092e1a1` (このセッションの checkout の origin/main、fetch 後。作業機の local main はこれより先に進んでいる可能性がある)。行番号はすべて基点の値。HEAD の状態の行番号は書かない (作業機で取り直す)。この表は草案の記録であり受け入れの証拠ではない。数え方は作業指示書 §16.2・§16.4 と同じ (塊 = `extract_all_blocks`、文 = `split_sentences(_flatten(...))`、目印 = 設計 §3、安全 / 保護参照 / 位置 = §14.2 の正規表現)。

対象の塊 31 (docstring 3 / comment 28)、spec に入れた塊 6 (編集 6)、検査器が拒んだ塊 2 (番号は欠番のまま)、削除した文 0。

## A. 判定表 (全塊。対象の塊 1 つにつき 1 行。spec の `blocks` の各項目が 1 行に対応し、spec に無い行は「基準のまま」)

| # | 塊 (基点の行) | qualname | 種別 | 拾った理由 (目印 / 安全 / 保護参照 / 位置 / 参照先) | spec の CH-ID | 除いた語句 (spec の `old` → `new`) | HEAD の状態 | 判定 (§3) | 根拠 | 削除前の確認 (指示語・副詞・直後の 2 文。設計 §3) | 除去後の文を読んだ判定 | 点検語 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | L1-47 | `<module>` | docstring | 目印 3 文、保護参照、位置、参照先/参照元 | CH-1060 | `(no cross-peer sharing, requester ruling 2026-09-03)` → `(no cross-peer sharing)` | `History: CH-1060` | 移す (文頭ラベル・括弧内トークン・日付の機械除去)。残りは残す | 第 4 段落の括弧 `(no cross-peer sharing, requester ruling 2026-09-03)` から裁定の日付句 `requester ruling 2026-09-03` と区切りを除く (検査器が受け付けた。Y7-3 (a))。第 1 文のラベル `Q4 phase D-1/D-2 (docs/design/Q4_DB_SIDE_SINGLE_TRUTH_V1.md v1.3): ` は実在パス + 版数で保護。第 3 段落の括弧 `(supervisor ruling 2026-09-05, `{scratchpad}/rulings-q4-wp12-rework.md` §1)` は検査器が許す候補だが、残る文 `not specified verbatim by the ruling, which only fixes … listed in §1` と `this WP's own completion report` が寄りかかる ((i)) ので残す。作業ノートの参照 (L24) はこのため残る。L60-65・L887-920・L941-945 が `this module's own docstring/header` で指す参照先 | 文の削除 0 | Peer-local, independently maintained (no cross-peer sharing) -- this module's read/validate/derive/check helpers are pinned isomorphic … -- 読める | `instead`、`that`、`this` |
| 2 | L60-65 | `<module>` | comment | 参照先/参照元 | なし | (除去なし) | 基準のバイト列 (CH なし) | 残す (§3) | 経緯トークン 0。除去の対象になる語が無く、経緯だけの文も無い (全文を読んだ。§3 残す)。内容の除去が 0 なので CH-ID を付けない (Y7-3 (d)) | 文の削除 0 | 除去なし (基準のまま) | `that`、`this` |
| 3 | L69-73 | `<module>` | comment | 目印 1 文、安全 | CH-1061 (欠番) | (試した除去: `allocation, requester ruling #: 2026-09-05: MitateDB` → `allocation: MitateDB`) → 検査器が拒んだ | 基準のバイト列 (CH なし) | 残す (§3。除去を試したが検査器が受け付けない (`--base` で赤を実測)。基準のまま) | 括弧 `(design §8 migration allocation, requester ruling 2026-09-05: MitateDB `0007`; …)` から裁定の日付句 `, requester ruling 2026-09-05` を除く編集を検査器が拒んだ (括弧の中で `: ` が続く形。FAIL (§4.1 (3)) retained text has no order-preserving match)。CH-1061 は欠番 | 文の削除 0 | 除去なし (基準のまま) | `that` |
| 4 | L77-82 | `<module>` | comment | 保護参照 | CH-1062 | `#: Phase 10 WP-6b (design D-5 (ii)): the platform` → `#: the platform` | `# history: CH-1062` | 移す (文頭ラベル・括弧内トークン・日付の機械除去)。残りは残す | `#: ` の後の文頭ラベル `Phase 10 WP-6b (design D-5 (ii)): ` (経緯トークン Phase 10・WP-6b、裸 ID D-5 (ii)) を (6) で除く。`#:` の行頭記号は保つ (0g 6)。残る文は F-15 (保護) と migration の現在の役割を述べ、D-5・WP-6b を名指さない | 文の削除 0 | #: the platform single-shot migration that widens `platform_declarations.key`'s own CHECK constraint … -- 読める | `that`、`this` |
| 5 | L86-88 | `<module>` | comment | 全塊走査 (拾った理由なし) | なし | (除去なし) | 基準のバイト列 (CH なし) | 残す (§3) | 経緯トークン 0。除去の対象になる語が無く、経緯だけの文も無い (全文を読んだ。§3 残す)。内容の除去が 0 なので CH-ID を付けない (Y7-3 (d)) | 文の削除 0 | 除去なし (基準のまま) | `that` |
| 6 | L91-94 | `<module>` | comment | 全塊走査 (拾った理由なし) | なし | (除去なし) | 基準のバイト列 (CH なし) | 残す (§3) | 経緯トークン 0。除去の対象になる語が無く、経緯だけの文も無い (全文を読んだ。§3 残す)。内容の除去が 0 なので CH-ID を付けない (Y7-3 (d)) | 文の削除 0 | 除去なし (基準のまま) | `that` |
| 7 | L97-98 | `<module>` | comment | 全塊走査 (拾った理由なし) | なし | (除去なし) | 基準のバイト列 (CH なし) | 残す (§3) | 経緯トークン 0。除去の対象になる語が無く、経緯だけの文も無い (全文を読んだ。§3 残す)。内容の除去が 0 なので CH-ID を付けない (Y7-3 (d)) | 文の削除 0 | 除去なし (基準のまま) | なし |
| 8 | L101-104 | `<module>` | comment | 全塊走査 (拾った理由なし) | なし | (除去なし) | 基準のバイト列 (CH なし) | 残す (§3) | 経緯トークン 0。除去の対象になる語が無く、経緯だけの文も無い (全文を読んだ。§3 残す)。内容の除去が 0 なので CH-ID を付けない (Y7-3 (d)) | 文の削除 0 | 除去なし (基準のまま) | なし |
| 9 | L108-114 | `<module>` | comment | 目印 1 文 | なし | (除去なし) | 基準のバイト列 (CH なし) | 残す (§3) | 括弧 `(Agent C isomorphism convergence, rulings-q4-wp12-rework.md sec.1: the literal env var name was previously baked …)` は内容語を含み (4) で括弧ごとは消えない。`previously` の経緯と現在の理由 (定数で normalize-diff を通す) が同じ文に同居 | 文の削除 0 | 除去なし (基準のまま) | `that`、`this` |
| 10 | L121-125 | `<module>` | comment | 全塊走査 (拾った理由なし) | なし | (除去なし) | 基準のバイト列 (CH なし) | 残す (§3) | 括弧 `(… Agent C isomorphism convergence, rulings-q4-wp12-rework.md sec.1)` は内容語を含む。経緯トークン 0 | 文の削除 0 | 除去なし (基準のまま) | `that`、`this` |
| 11 | L128-129 | `<module>` | comment | 全塊走査 (拾った理由なし) | なし | (除去なし) | 基準のバイト列 (CH なし) | 残す (§3) | 経緯トークン 0。除去の対象になる語が無く、経緯だけの文も無い (全文を読んだ。§3 残す)。内容の除去が 0 なので CH-ID を付けない (Y7-3 (d)) | 文の削除 0 | 除去なし (基準のまま) | なし |
| 12 | L132-136 | `<module>` | comment | 全塊走査 (拾った理由なし) | なし | (除去なし) | 基準のバイト列 (CH なし) | 残す (§3) | 括弧 `(ruling §1: "peer 名を含む定数は対応表に載せない")` は引用の内容語を含む | 文の削除 0 | 除去なし (基準のまま) | なし |
| 13 | L199-202 | `<module>` | comment | 全塊走査 (拾った理由なし) | なし | (除去なし) | 基準のバイト列 (CH なし) | 残す (§3) | 経緯トークン 0。除去の対象になる語が無く、経緯だけの文も無い (全文を読んだ。§3 残す)。内容の除去が 0 なので CH-ID を付けない (Y7-3 (d)) | 文の削除 0 | 除去なし (基準のまま) | なし |
| 14 | L249-254 | `<module>` | comment | 参照先/参照元 | なし | (除去なし) | 基準のバイト列 (CH なし) | 残す (§3) | 経緯トークン 0。除去の対象になる語が無く、経緯だけの文も無い (全文を読んだ。§3 残す)。内容の除去が 0 なので CH-ID を付けない (Y7-3 (d)) | 文の削除 0 | 除去なし (基準のまま) | なし |
| 15 | L361-370 | `_validate_base_url` | docstring | 全塊走査 (拾った理由なし) | なし | (除去なし) | 基準のバイト列 (CH なし) | 残す (§3) | 第 2 文のラベル `Agent C isomorphism convergence (rulings-q4-wp12-rework.md sec.1, §12 LQ4-23): ` は内容語 4 語 (Agent / C / isomorphism / convergence)。括弧の中の `sec.1`・`LQ4-23` (ID 文法に当たらない) は内容語で括弧ごとは消えない。残る文は現在の置き場所 (design §3.10) を述べる | 文の削除 0 | 除去なし (基準のまま) | `that`、`this` |
| 16 | L379-384 | `_validate_base_url` | comment | 全塊走査 (拾った理由なし) | なし | (除去なし) | 基準のバイト列 (CH なし) | 残す (§3) | 経緯トークン 0。除去の対象になる語が無く、経緯だけの文も無い (全文を読んだ。§3 残す)。内容の除去が 0 なので CH-ID を付けない (Y7-3 (d)) | 文の削除 0 | 除去なし (基準のまま) | `otherwise`、`that` |
| 17 | L525-530 | `<module>` | comment | 目印 1 文、安全、保護参照 | CH-1063 (欠番) | (試した除去: `design # D-2(f), monitor ruling 2026-09-05.` → `design # D-2(f).`) → 検査器が拒んだ | 基準のバイト列 (CH なし) | 残す (§3。除去を試したが検査器が受け付けない (`--base` で赤を実測)。基準のまま) | 見出し行の文末 `-- design D-2(f), monitor ruling 2026-09-05.` の裁定の日付句は括弧でもラベルでもなく、許容操作に当たらない (検査器が拒んだ。FAIL (§4.1 (3)) cannot delete a whole sentence carrying a protected reference)。CH-1063 は欠番 | 文の削除 0 | 除去なし (基準のまま) | なし |
| 18 | L579-586 | `<module>` | comment | 全塊走査 (拾った理由なし) | なし | (除去なし) | 基準のバイト列 (CH なし) | 残す (§3) | 経緯トークン 0。除去の対象になる語が無く、経緯だけの文も無い (全文を読んだ。§3 残す)。内容の除去が 0 なので CH-ID を付けない (Y7-3 (d)) | 文の削除 0 | 除去なし (基準のまま) | `that`、`this` |
| 19 | L656-663 | `_role_setting_rows` | docstring | 保護参照 | CH-1064 | `(design D-1(c) amendment 2026-09-05)` → `(design D-1(c) amendment)` | `History: CH-1064` | 移す (文頭ラベル・括弧内トークン・日付の機械除去)。残りは残す | 括弧 `(design D-1(c) amendment 2026-09-05)` から日付 1 語を除く (検査器が受け付けた。Y7-3 (a))。残る `(design D-1(c) amendment)` は条項と訂正を名指し、文は catalog query の範囲 (安全: cluster 全体を読まない) を述べる | 文の削除 0 | (`setdatabase = <this db's oid>`, F-11's own per-database override) -- the catalog query itself is restricted to `setdatabase IN (0, own db oid)` (design D-1(c) amendment), never every database … -- 読める | `that`、`this` |
| 20 | L758-797 | `<module>` | comment | 保護参照、参照先/参照元 | なし | (除去なし) | 基準のバイト列 (CH なし) | 残す (§3) | ラベルの括弧は実在パス `docs/design/PHASE9_CONTRACT_170_DECLARATION_AND_VERIFICATION_V1.md` (折返しで割れる) と `Contract 1.7.0` を持ち保護。括弧内の `{scratchpad}/rulings-r3-r7-flip.md` ×2 だけを除くと `F-3, F-3;`・`L-2/M-7` が出所の無い断片として残る。残る文は `T3 rework`・`the PRE-rework version` に寄りかかる ((i))。作業ノートの参照 (L760・L761) はこのため残る | 文の削除 0 | 除去なし (基準のまま) | `that`、`this` |
| 21 | L856-859 | `<module>` | comment | 全塊走査 (拾った理由なし) | なし | (除去なし) | 基準のバイト列 (CH なし) | 残す (§3) | 経緯トークン 0。除去の対象になる語が無く、経緯だけの文も無い (全文を読んだ。§3 残す)。内容の除去が 0 なので CH-ID を付けない (Y7-3 (d)) | 文の削除 0 | 除去なし (基準のまま) | なし |
| 22 | L862-883 | `<module>` | comment | 目印 1 文、参照先/参照元 | CH-1065 | `WP-3e rework T3 (ruling #: `{scratchpad}/rulings-r3-r7-flip.md` L-2/M-7) removed this module's #: former` → `WP-3e rework T3 removed this #: module's former` | `# history: CH-1065` | 移す (文頭ラベル・括弧内トークン・日付の機械除去)。残りは残す | 文中の括弧 `(ruling `{scratchpad}/rulings-r3-r7-flip.md` L-2/M-7)` (種類語 ruling、非実在パス、裸 ID) を括弧ごと (4) で除く (§9 規則 3)。`#:` の 3 行を 2 行に切り直した (`#:` は保つ)。`WP-3e rework T3 removed …` は文中の主語で残る (`used to` の経緯と現在の理由の同居文)。残る文は L-2/M-7 を名指さない | 文の削除 0 | #: … -- never here. WP-3e rework T3 removed this module's former `_CONTRACT_170_LIMIT_ATTRIBUTES` (…) for exactly that reason: … -- 読める | `again`、`instead`、`that`、`this` |
| 23 | L887-920 | `<module>` | comment | 目印 1 文、安全、保護参照、位置、参照先/参照元 | CH-1066 | `(Phase 10 WP-4f, supervisor ruling 2026-09-09; peer-symmetric` → `(peer-symmetric` | `# history: CH-1066` | 移す (文頭ラベル・括弧内トークン・日付の機械除去)。残りは残す | 第 1 文の括弧 `(Phase 10 WP-4f, supervisor ruling 2026-09-09; peer-symmetric with …)` から経緯トークン 3 語 (Phase 10・WP-4f・supervisor ruling 2026-09-09) と区切り `; ` を除く (検査器が受け付けた)。ラベル `F-16 (…)` の F-16 は保護参照で残る。残る文の `the full WP-4e finding this responds to` は WP-4e (残る) を指す。第 3 段落の `(measured 2026-09-10, WP-4 integration review M-1, …)` は日付を除くと `measured,` が何時の計測か失うので残す (Y7-3 (b))。role の安全上の理由 (CONNECTION LIMIT) を含む文は残す | 文の削除 0 | # F-16 (peer-symmetric with r2db-api's own same-numbered check -- see that peer's own module for the full WP-4e finding this responds to): every PostgreSQL role … -- 読める | `also`、`instead`、`otherwise`、`that`、`this` |
| 24 | L922-928 | `<module>` | comment | 全塊走査 (拾った理由なし) | なし | (除去なし) | 基準のバイト列 (CH なし) | 残す (§3) | 経緯トークン 0。除去の対象になる語が無く、経緯だけの文も無い (全文を読んだ。§3 残す)。内容の除去が 0 なので CH-ID を付けない (Y7-3 (d)) | 文の削除 0 | 除去なし (基準のまま) | なし |
| 25 | L931-938 | `<module>` | comment | 全塊走査 (拾った理由なし) | なし | (除去なし) | 基準のバイト列 (CH なし) | 残す (§3) | 経緯トークン 0。除去の対象になる語が無く、経緯だけの文も無い (全文を読んだ。§3 残す)。内容の除去が 0 なので CH-ID を付けない (Y7-3 (d)) | 文の削除 0 | 除去なし (基準のまま) | `this` |
| 26 | L941-945 | `<module>` | comment | 全塊走査 (拾った理由なし) | なし | (除去なし) | 基準のバイト列 (CH なし) | 残す (§3) | 経緯トークン 0。除去の対象になる語が無く、経緯だけの文も無い (全文を読んだ。§3 残す)。内容の除去が 0 なので CH-ID を付けない (Y7-3 (d)) | 文の削除 0 | 除去なし (基準のまま) | `this` |
| 27 | L998-1001 | `<module>` | comment | 参照先/参照元 | なし | (除去なし) | 基準のバイト列 (CH なし) | 残す (§3) | 経緯トークン 0。除去の対象になる語が無く、経緯だけの文も無い (全文を読んだ。§3 残す)。内容の除去が 0 なので CH-ID を付けない (Y7-3 (d)) | 文の削除 0 | 除去なし (基準のまま) | `this` |
| 28 | L1068-1074 | `check_role_connection_limits` | comment | 安全、位置、参照先/参照元 | CH-1067 | `# M-1 (WP-4 integration review 2026-09-10): a role` → `# a role` | `# history: CH-1067` | 移す (文頭ラベル・括弧内トークン・日付の機械除去)。残りは残す | 文頭ラベル `M-1 (WP-4 integration review 2026-09-10): ` (裸 ID M-1、経緯トークン WP-4・review・日付、内容語 integration 1) を (6) で除く。残る文は `max(...)` と `_table_owner` の現在の理由で M-1 を名指さない (L887-920 第 3 段落の `WP-4 integration review M-1` は別の塊)。integration は module 内で現行の区分名として使われない | 文の削除 0 | # a role can legitimately match MORE than one platform-plane class below … -- 読める | `instead`、`that` |
| 29 | L1095-1098 | `check_role_connection_limits` | comment | 全塊走査 (拾った理由なし) | なし | (除去なし) | 基準のバイト列 (CH なし) | 残す (§3) | 経緯トークン 0。除去の対象になる語が無く、経緯だけの文も無い (全文を読んだ。§3 残す)。内容の除去が 0 なので CH-ID を付けない (Y7-3 (d)) | 文の削除 0 | 除去なし (基準のまま) | `still` |
| 30 | L1201-1236 | `<module>` | comment | 参照先/参照元 | なし | (除去なし) | 基準のバイト列 (CH なし) | 残す (§3) | ラベル `F-18 (R-91, work order docs/work-orders/WORK_ORDER_R91_MAX_CONNECTIONS_HEADROOM_CHECK_V1.md §1.2 D-1, …): ` は F-18 と実在パス (折返しで割れる) で保護。経緯トークン 0。残る文の `(§1.1 (c))` は同じ括弧の work order を出所に持つ | 文の削除 0 | 除去なし (基準のまま) | `that`、`this` |
| 31 | L1525-1528 | `<module>` | comment | 全塊走査 (拾った理由なし) | なし | (除去なし) | 基準のバイト列 (CH なし) | 残す (§3) | 経緯トークン 0。除去の対象になる語が無く、経緯だけの文も無い (全文を読んだ。§3 残す)。内容の除去が 0 なので CH-ID を付けない (Y7-3 (d)) | 文の削除 0 | 除去なし (基準のまま) | なし |

## B. 目印一覧に当たる文 (8 文 / 6 塊。完了条件 27)

| # | 塊 (基点の行) | CH-ID | 目印 | 文 (先頭の数語) | HEAD の状態 | 判定 (§3) | 根拠 | 点検語 | A の行 |
|---|---|---|---|---|---|---|---|---|---|
| 1 | L1-47 | CH-1060 | `(supervisor|supervisory|monitor|requester) ruling` | `Reference-implementation module (supervisor ruling 2026-09-05, `{scrat…` | `History: CH-1060` | 残す (文は削除しない) | ラベル・括弧・日付だけを除き、文は残す (経緯と現在の理由の同居文) | `instead`、`that`、`this` | 1 |
| 2 | L1-47 | CH-1060 | `this (WP|commit|change set|round)` | `This is a deliberate, documented implementation choice (not specified …` | `History: CH-1060` | 残す (文は削除しない) | ラベル・括弧・日付だけを除き、文は残す (経緯と現在の理由の同居文) | `instead`、`that`、`this` | 1 |
| 3 | L1-47 | CH-1060 | `(supervisor|supervisory|monitor|requester) ruling` | `Peer-local, independently maintained (no cross-peer sharing, requester…` | `History: CH-1060` | 残す (文は削除しない) | ラベル・括弧・日付だけを除き、文は残す (経緯と現在の理由の同居文) | `instead`、`that`、`this` | 1 |
| 4 | L69-73 | なし | `(supervisor|supervisory|monitor|requester) ruling` | `The platform single-shot migration that creates the table and seeds th…` | 基準のバイト列 (CH なし) | 残す (文は削除しない) | 検査器が除去を受け付けず、基準のまま | `that` | 3 |
| 5 | L108-114 | なし | `previously` | `F-6's own env var name -- referenced by bare name from `_f6_forward_me…` | 基準のバイト列 (CH なし) | 残す (文は削除しない) | 同居文は残す (A の行の根拠) | `that`、`this` | 9 |
| 6 | L525-530 | なし | `(supervisor|supervisory|monitor|requester) ruling` | `----------------------------------------------------------------------…` | 基準のバイト列 (CH なし) | 残す (文は削除しない) | 検査器が除去を受け付けず、基準のまま | なし | 17 |
| 7 | L862-883 | CH-1065 | `used to` | `WP-3e rework T3 (ruling `{scratchpad}/rulings-r3-r7-flip.md` L-2/M-7) …` | `# history: CH-1065` | 残す (文は削除しない) | ラベル・括弧・日付だけを除き、文は残す (経緯と現在の理由の同居文) | `again`、`instead`、`that`、`this` | 22 |
| 8 | L887-920 | CH-1066 | `(supervisor|supervisory|monitor|requester) ruling` | `----------------------------------------------------------------------…` | `# history: CH-1066` | 残す (文は削除しない) | ラベル・括弧・日付だけを除き、文は残す (経緯と現在の理由の同居文) | `also`、`instead`、`otherwise`、`that`、`this` | 23 |

## C. 経緯と同じ文にある安全上の理由・保護参照・位置 (安全 4 塊と、保護参照・位置だけの塊)

| # | 塊 | CH-ID | 種別 | HEAD の状態 | 判定 (§3) | 根拠 (その塊の安全上の理由・保護参照が残ること) | 点検語 | A の行 |
|---|---|---|---|---|---|---|---|---|
| 1 | L1-47 | CH-1060 | 保護参照、位置 | `History: CH-1060` | 残す (文は削除しない。除去は経緯トークンの機械除去だけ) | 経緯トークンを含む文のうち 安全 0 / 保護参照 1 / 位置 1 文。文は消していない。除去はラベル・括弧内トークン・日付だけ | `instead`、`that`、`this` | 1 |
| 2 | L69-73 | なし | 安全 (role、timeout) | 基準のバイト列 (CH なし) | 残す (文は削除しない。除去は経緯トークンの機械除去だけ) | 経緯トークンを含む文のうち 安全 1 / 保護参照 0 / 位置 0 文。文は消していない。除去なし | `that` | 3 |
| 3 | L77-82 | CH-1062 | 保護参照 | `# history: CH-1062` | 残す (文は削除しない。除去は経緯トークンの機械除去だけ) | 経緯トークンを含む文のうち 安全 0 / 保護参照 1 / 位置 0 文。文は消していない。除去はラベル・括弧内トークン・日付だけ | `that`、`this` | 4 |
| 4 | L525-530 | なし | 安全 (role)、保護参照 | 基準のバイト列 (CH なし) | 残す (文は削除しない。除去は経緯トークンの機械除去だけ) | 経緯トークンを含む文のうち 安全 1 / 保護参照 1 / 位置 0 文。文は消していない。除去なし | なし | 17 |
| 5 | L656-663 | CH-1064 | 保護参照 | `History: CH-1064` | 残す (文は削除しない。除去は経緯トークンの機械除去だけ) | 経緯トークンを含む文のうち 安全 0 / 保護参照 1 / 位置 0 文。文は消していない。除去はラベル・括弧内トークン・日付だけ | `that`、`this` | 19 |
| 6 | L758-797 | なし | 保護参照 | 基準のバイト列 (CH なし) | 残す (文は削除しない。除去は経緯トークンの機械除去だけ) | 経緯トークンを含む文のうち 安全 0 / 保護参照 1 / 位置 0 文。文は消していない。除去なし | `that`、`this` | 20 |
| 7 | L887-920 | CH-1066 | 安全 (role)、保護参照、位置 | `# history: CH-1066` | 残す (文は削除しない。除去は経緯トークンの機械除去だけ) | 経緯トークンを含む文のうち 安全 2 / 保護参照 1 / 位置 1 文。文は消していない。除去はラベル・括弧内トークン・日付だけ | `also`、`instead`、`otherwise`、`that`、`this` | 23 |
| 8 | L1068-1074 | CH-1067 | 安全 (role)、位置 | `# history: CH-1067` | 残す (文は削除しない。除去は経緯トークンの機械除去だけ) | 経緯トークンを含む文のうち 安全 1 / 保護参照 0 / 位置 1 文。文は消していない。除去はラベル・括弧内トークン・日付だけ | `instead`、`that` | 28 |

## 除いた語の一覧 (完了条件 30。`cs9_removed_tokens.py` の `REMOVED` 行 7 行と同じ順で 1 行ずつ対応。実行は checks.md)

| # | 塊 (基点の行) | CH-ID | 種類 | 除いた語 | 回数 | 意味と出所が残る根拠 |
|---|---|---|---|---|---|---|
| 1 | L77-82 | CH-1062 | id | `D-5` | 1 | 設計名 (ファイル名・版数) の付かない裸の局所 ID `D-5`。出所を持たず、残る文は名指しも指示語でも指さない。保護参照 (SI-・F-ID・実在パス・版数付き文書名) は変わらない (`--base` exit 0) |
| 2 | L77-82 | CH-1062 | id | `WP-6b` | 1 | WP の位置指定 `WP-6b` はラベル又は括弧の中だけにあった。残る文は `this WP`・`pre-WP`・`WP-` でこの WP を指さない (A の根拠欄で点検済み) |
| 3 | L862-883 | CH-1065 | id | `L-2` | 1 | 設計名 (ファイル名・版数) の付かない裸の局所 ID `L-2`。出所を持たず、残る文は名指しも指示語でも指さない。保護参照 (SI-・F-ID・実在パス・版数付き文書名) は変わらない (`--base` exit 0) |
| 4 | L862-883 | CH-1065 | id | `M-7` | 1 | 設計名 (ファイル名・版数) の付かない裸の局所 ID `M-7`。出所を持たず、残る文は名指しも指示語でも指さない。保護参照 (SI-・F-ID・実在パス・版数付き文書名) は変わらない (`--base` exit 0) |
| 5 | L887-920 | CH-1066 | id | `WP-4f` | 1 | WP の位置指定 `WP-4f` はラベル又は括弧の中だけにあった。残る文は `this WP`・`pre-WP`・`WP-` でこの WP を指さない (A の根拠欄で点検済み) |
| 6 | L1068-1074 | CH-1067 | id | `M-1` | 1 | 設計名 (ファイル名・版数) の付かない裸の局所 ID `M-1`。出所を持たず、残る文は名指しも指示語でも指さない。保護参照 (SI-・F-ID・実在パス・版数付き文書名) は変わらない (`--base` exit 0) |
| 7 | L1068-1074 | CH-1067 | id | `WP-4` | 1 | WP の位置指定 `WP-4` はラベル又は括弧の中だけにあった。残る文は `this WP`・`pre-WP`・`WP-` でこの WP を指さない (A の根拠欄で点検済み) |

## 塊をまたぐ参照先一覧 (行番号は基点。参照先の文は「残す」と固定)

| # | 参照元 (`file:line`) | 参照の語 | 参照先 (`file:line`) | 参照先の文 (先頭の数語) | 残っているか (spec を当てた作業ツリー) |
|---|---|---|---|---|---|
| 1 | `platform_declarations.py` L60-65 | this module's own docstring above explains why that is safe | L1-47 (CH-1060) 第 3 段落 | `Reference-implementation module (supervisor ruling 2026-09-05, `{scratchpad}/rulings-q4-wp12-rework.md` §1): every name, signature and return type below is shared verbatim` | はい (第 3 段落は基準のまま。除いたのは第 4 段落の裁定の日付句) |
| 2 | `platform_declarations.py` L887-920 (`this module's own header already avoids that technique`)、L941-945 (`this module's own header`) | this module's own header | L1-47 (CH-1060) 第 1 段落 (D-2(h)) | ``pg_db_role_setting` … is now the single source of both the two writer timeouts AND which roles are declared audit writers (D-2(h))` | はい |
| 3 | `platform_declarations.py` L1068-1074 | see the module header above | L887-920 (CH-1066) 第 3 段落 | `Deliberately excludes `mitatedbsvc_provision` … This is an EXPLICIT exclusion (`_table_owner`, below)` | はい (除いたのは第 1 文の括弧の経緯トークンだけ) |
| 4 | `platform_declarations.py` L379-384 / L1095-1098 / L1525-1528 | `surfaces.data.base_url`'s own `suffix` check / `0012_role_connection_limits.sql`'s own migration-time loop / `check_denial_window_function` compares | コード・migration | `—` | はい (コードへの参照) |
| 5 | `platform_declarations.py` L77-82 (CH-1062) | referenced by `_f15_missing_message` only | コード | `—` | はい |
| 6 | `platform_declarations.py` L1201-1236 | F-16 above never asks / UNLIKE F-16's own narrowed startup calls | L887-920 (CH-1066) と `check_role_connection_limits` のコード | `every PostgreSQL role this deployment's own processes pool connections against must have a `CONNECTION LIMIT`` | はい |
| 7 | 登録 helper の中から対象の塊へ: L964-980 (`_table_owner`) | Used below to keep that owner … (M-1, WP-4 integration review 2026-09-10, …) | L1068-1074 (CH-1067) のコードと、同じ M-1 の裁定 | `M-1 (WP-4 integration review 2026-09-10): a role can legitimately match MORE than one platform-plane class` | はい (helper 側は M-1 と日付を自ら持つ。対象の塊のラベルを除いても helper の文は指す先 (コード) を失わない) |
| 8 | 登録 helper の中から対象の塊へ: L1352-1369 (`check_max_connections_headroom`)、L1314-1317 (`HeadroomReport`)、L1268-1273 | `headroom_lower_bound`, above / `_f18_message` below / unlike `check_role_connection_limits`'s own read | コード (登録 helper 同士) | `—` | 対象外 (helper → helper / コード) |
| 9 | 登録 helper の中から対象の塊へ: L803-823 (`check_contract_170_declarations`) | the signature above is bare … (版フリップ監査, ruling `{scratchpad}/rulings-r3-r7-flip.md` 追補4) | コード (自身の signature)。周辺の塊 L758-797 (基準のまま) | `Contract 1.7.0 (design docs/design/PHASE9_CONTRACT_170_DECLARATION_AND_VERIFICATION_V1.md D-1/D-6/D-5, …)` | はい |
| 10 | 登録 helper の中から対象の塊へ: L557-561 (`check_control_surface_consistency`) | it has its own unconditional F-3c check below, monitor ruling 2026-09-05 | コード (`require_control_surface_declared`)。見出し L525-530 (基準のまま、CH-1063 欠番) | `F-6 / F-3c: `surfaces.control`'s presence must agree with the calling process' own role` | はい |
| 11 | MitateDB `conformance/real_server_mitatedb.py:460`、r2db `conformance/real_server_r2db.py:528` | left below `check_role_connection_limits`'s own floor | 数値の比較 (コメントへの参照ではない) | `—` | 対象外 |
| 12 | MitateDB `tests/test_audit_query.py:2722` | Unlike `check_role_connection_limits` (excluded above: …) | 同じテストファイルの同型性の表のコメント | `—` | 対象外 |
| 13 | r2db `tests/test_application_audit.py:2848` | the central claim `check_writer_role_timeouts`'s own docstring makes (design D-1(c)) | r2db 側の同名 docstring (と MitateDB の登録 helper L732-745) | `—` | 対象外 (登録 helper の docstring。触らない) |
| 14 | `security/CONTROL_MAPPING.md` (15 件) / `conformance-tests/` (0 件) / README・`docs/` (0 件) | 位置参照 `MitateDB-api/src/mitatedb_api/platform_declarations.py:N` (すべてパス付き。basename だけの形は 0) | コードの行 (コメント・docstring の行を指すものは 0) | `—` | `repull.py --dry-run` が 15 件とも引き直す (unresolved 0) |

## 文頭でない位置のラベル除去の全件 (直前に残る段落・文のラベル・見出しと並べる)

| # | 塊 (CH-ID、基点の行) | 除去したラベル | 除去の位置 | 直前に残る段落・文のラベル・見出し | 判定 |
|---|---|---|---|---|---|
| 1 | — | `—` | — | 文頭でない位置のラベル除去は 0 件 (CH-1062・CH-1067 のラベルは塊の先頭。CH-1060・CH-1064・CH-1065・CH-1066 の編集は括弧・日付で、ラベルは基準のまま) | 該当なし |

## ラベルを除いた全編集の内容語の走査 ((iii)。ラベルの中の、経緯トークン・ID・括弧・接続語・種類語 (design / ruling / review) 以外の語)

| # | 塊 (CH-ID、基点の行) | 除いたラベル | 内容語 | module 内の他の出現 (現行の区分名・規則名か) | 判定 |
|---|---|---|---|---|---|
| 1 | CH-1062 (L77) | `Phase 10 WP-6b (design D-5 (ii)): ` | なし | — | 除いてよい |
| 2 | CH-1067 (L1068) | `M-1 (WP-4 integration review 2026-09-10): ` | integration | L918 (経緯ラベル) と登録 helper L971 の docstring の中だけ。現行の区分名・規則名ではない | 除いてよい |

## 見送った除去の一覧 (候補が在ったが基準のまま残した塊。型は依頼の (i)〜(iv) と Y7-3 (b)、検査器が拒んだもの)

| # | 塊 (基点の行) | 型 | 根拠 (A の行と同じ) |
|---|---|---|---|
| 1 | L1-47 (A の行 1) | (i) 見送り 1 件 | 第 4 段落の括弧 `(no cross-peer sharing, requester ruling 2026-09-03)` から裁定の日付句 `requester ruling 2026-09-03` と区切りを除く (検査器が受け付けた。Y7-3 (a))。第 1 文のラベル `Q4 phase D-1/D-2 (docs/design/Q4_DB_SIDE_SINGLE_TRUTH_V1.md v1.3): ` は実在パス + 版数で保護。第 3 段落の括弧 `(supervisor ruling 2026-09-05, `{scratchpad}/rulings-q4-wp12-rework.md` §1)` は検査器が許す候補だが、残る文 `not specified verbatim by the ruling, which only fixes … listed in §1` と `this WP's own completion report` が寄りかかる ((i)) ので残す。作業ノートの参照 (L24) はこのため残る。L60-65・L887-920・L941-945 が `this module's own docstring/header` で指す参照先 |
| 2 | L69-73 (A の行 3) | 検査器が拒んだ | 括弧 `(design §8 migration allocation, requester ruling 2026-09-05: MitateDB `0007`; …)` から裁定の日付句 `, requester ruling 2026-09-05` を除く編集を検査器が拒んだ (括弧の中で `: ` が続く形。FAIL (§4.1 (3)) retained text has no order-preserving match)。CH-1061 は欠番 |
| 3 | L361-370 (A の行 15) | (iii) | 第 2 文のラベル `Agent C isomorphism convergence (rulings-q4-wp12-rework.md sec.1, §12 LQ4-23): ` は内容語 4 語 (Agent / C / isomorphism / convergence)。括弧の中の `sec.1`・`LQ4-23` (ID 文法に当たらない) は内容語で括弧ごとは消えない。残る文は現在の置き場所 (design §3.10) を述べる |
| 4 | L525-530 (A の行 17) | 検査器が拒んだ | 見出し行の文末 `-- design D-2(f), monitor ruling 2026-09-05.` の裁定の日付句は括弧でもラベルでもなく、許容操作に当たらない (検査器が拒んだ。FAIL (§4.1 (3)) cannot delete a whole sentence carrying a protected reference)。CH-1063 は欠番 |
| 5 | L758-797 (A の行 20) | (i) / 断片 | ラベルの括弧は実在パス `docs/design/PHASE9_CONTRACT_170_DECLARATION_AND_VERIFICATION_V1.md` (折返しで割れる) と `Contract 1.7.0` を持ち保護。括弧内の `{scratchpad}/rulings-r3-r7-flip.md` ×2 だけを除くと `F-3, F-3;`・`L-2/M-7` が出所の無い断片として残る。残る文は `T3 rework`・`the PRE-rework version` に寄りかかる ((i))。作業ノートの参照 (L760・L761) はこのため残る |
| 6 | L887-920 (A の行 23) | 一部残し (measured 2026-09-10) | 第 1 文の括弧 `(Phase 10 WP-4f, supervisor ruling 2026-09-09; peer-symmetric with …)` から経緯トークン 3 語 (Phase 10・WP-4f・supervisor ruling 2026-09-09) と区切り `; ` を除く (検査器が受け付けた)。ラベル `F-16 (…)` の F-16 は保護参照で残る。残る文の `the full WP-4e finding this responds to` は WP-4e (残る) を指す。第 3 段落の `(measured 2026-09-10, WP-4 integration review M-1, …)` は日付を除くと `measured,` が何時の計測か失うので残す (Y7-3 (b))。role の安全上の理由 (CONNECTION LIMIT) を含む文は残す |

## 作業ノートの参照の残し (`{scratchpad}/…`・`scratchpad/…`)

| 行 (基点) | 置き場 | 残した理由 |
|---|---|---|
| L24 | 対象の塊 (L1-47、CH-1060) の第 3 段落 | 残る文が `the ruling`・`listed in §1`・`this WP's own completion report` で寄りかかる ((i)) |
| L760・L761 | 対象の塊 (L758-797、基準のまま) | 実在パス + 版数付きの括弧の中。除くと `F-3, F-3;`・`L-2/M-7` が断片として残り、残る文が `T3 rework` に寄りかかる ((i)) |
| L871 (除いた) | 対象の塊 (L862-883、CH-1065) | 括弧ごと除いた (REMOVED path 行) |
| L266-271、L441-460、L803-823 | 登録 helper (`_f3c_message`・`validate_process_ceilings_value`・`check_contract_170_declarations`) の docstring | 対象外 (Y7-5 と同じ) |

## 指示語チェックの候補一覧 (削除した文 1 つにつき 1 行)

削除した文は 0 文 (spec の `new` が空の編集はすべて文頭ラベルの除去で、文の削除ではない)。候補一覧は該当なし。

## HTTP の status・error code を含む削除文の監査一覧

削除した文が 0 文のため該当なし。

## 0d の保護参照があるために残った、経緯だけの文

| # | 塊 (行) | 文 (先頭の数語) | 保護参照 | 状態 |
|---|---|---|---|---|
| 1 | L1-47 (第 3 段落) | `Reference-implementation module (supervisor ruling 2026-09-05, `{scratchpad}/rulings-q4-wp12-rework.md` §1): every name, signature and return type below is shared verbatim with r2db-api's own same-named realization …` | (ラベルの内容語 Reference-implementation module) と残る文の寄りかかり | 基準のまま ((i))。CH-1060 は第 4 段落の日付句だけ除いた |
| 2 | L758-797 (第 1 文) | `Contract 1.7.0 (design docs/design/PHASE9_CONTRACT_170_DECLARATION_AND_VERIFICATION_V1.md D-1/D-6/D-5, work order §2 WP-3e F-3, `{scratchpad}/rulings-r3-r7-flip.md` F-3; WP-3e rework T3, …): pinned isomorphic to r2db-api's own `check_contract_170_declarations` …` | 実在パス (折返しで割れる)、版数付き文書名 | 基準のまま。経緯 (T3 rework の前後) と現在の構造 (`capabilities_document` を caller から受ける) が同居 |
| 3 | L887-920 (第 3 段落末) | `… (measured 2026-09-10, WP-4 integration review M-1, peer-symmetric with r2db-api's own `r2dbsvc_control`).` | (保護参照は無い) 計測の事実 | 基準のまま。日付を除くと `measured,` が何時の計測か失う (Y7-3 (b)) |

## 訂正の記録 (0g)

`docs/code-history/MitateDB-api/platform_declarations.md` の `### correction:` は基点で 1 件 (CH-0550、2026-10-01 の既存の記録)。本草案は訂正の記録を足さない。
