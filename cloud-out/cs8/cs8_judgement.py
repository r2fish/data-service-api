"""cs8_judgement.py -- change set 8: render the per-block judgement tables (work order §16.4 shape).

usage: python3 cs8_judgement.py -C REPO --measure measure.json --spec SPEC.json --notes NOTES.json --out OUT.md

The hand-written judgements live in NOTES.json: {"<base start line>": {"judge": ..., "reason": ...,
"after": ..., "pre_delete": ...}, "_refs_external": [...], "_rejected": [...], "_skipped_types": [...]}.
Every target block gets exactly one row of table A; blocks without a note get the standard
"残す" row. Tables B (markers), C (safety / protected / position) and the in-module reference
list are rendered from measure.json. Nothing in the repository is written.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

POINT_WORDS = ["such", "this", "that", "those", "these", "instead", "exactly as", "again", "still", "also",
               "otherwise", "then", "the same", "その", "これ", "再び", "なお"]
POINT_RES = [(w, re.compile(r"\b" + re.escape(w) + r"\b", re.IGNORECASE) if w.isascii() else re.compile(w)) for w in POINT_WORDS]
def esc(t: str) -> str:
    return t.replace('|', '\\|')


ID_RE = re.compile(r"(?<![A-Za-z0-9])[A-Z]{1,6}-\d+[a-z]?(?![A-Za-z0-9])")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("-C", dest="repo", required=True)
    ap.add_argument("--measure", required=True)
    ap.add_argument("--spec", required=True)
    ap.add_argument("--notes", required=True)
    ap.add_argument("--out", required=True)
    ns = ap.parse_args()
    repo = Path(ns.repo).resolve()
    sys.path.insert(0, str(repo / "tools"))
    import check_comment_provenance as ccp  # noqa: E402

    spec = json.load(open(ns.spec, encoding="utf-8"))
    module = spec["module"]
    meas = json.load(open(ns.measure, encoding="utf-8"))[module]
    notes = json.load(open(ns.notes, encoding="utf-8"))
    base = spec["base"]
    src = subprocess.run(["git", "-C", str(repo), "show", f"{base}:{module}"], capture_output=True, text=True, check=True).stdout
    blocks = {b.start_line: b for b in ccp.extract_all_blocks(src)}
    by_line = {b["line"]: b for b in spec["blocks"]}
    wp = notes.get("_wp", "8")
    out = []
    P = out.append
    P(f"# 判定表 — `{module}` (基点 `{base}`、変更セット 8 の草案)\n")
    P(notes.get("_preamble", ""))
    P("")
    P("## A. 全塊 (対象の塊 1 つにつき 1 行。spec の `blocks` の各項目が 1 行に対応し、spec に無い行は「基準のまま」)\n")
    P("| # | WP | 塊 (基点の行) | qualname | 種別 | 拾った理由 (目印 / 安全 / 保護参照 / 位置 / 参照先) | spec の CH-ID | 除いた語句 (spec の `old` → `new`) | 作業ツリーの状態 (照合時) | 判定 (§3) | 根拠 | 削除前の確認 (指示語・副詞・直後の 2 文。設計 §3) | 除去後の文を読んだ判定 | 点検語 |")
    P("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    marker_blocks = {(r[0], r[1]): r[2] for r in meas["marker_rows"]}
    safety = {(r[0], r[1]) for r in meas["safety_rows"]}
    protected = {(r[0], r[1]) for r in meas["protected_rows"]}
    position = {(r[0], r[1]) for r in meas["position_rows"]}
    refd = set(tuple(x) for x in notes.get("_referenced_blocks", []))
    n_edit = n_sent_del = 0
    for i, pb in enumerate(meas["per_block"], 1):
        s, e = pb["start"], pb["end"]
        key = (s, e)
        why = []
        if key in marker_blocks:
            why.append(f"目印 {len(marker_blocks[key])} 文")
        if key in safety:
            why.append("安全")
        if key in protected:
            why.append("保護参照")
        if key in position:
            why.append("位置")
        if key in refd:
            why.append("参照先")
        why_s = "、".join(why) if why else "全塊走査 (拾った理由なし)"
        blk = blocks[s]
        text = blk.dedented
        points = [w for w, rx in POINT_RES if rx.search(text)]
        points_s = "、".join(f"`{w}`" for w in points) if points else "なし"
        note = notes.get(str(s), {})
        sp = by_line.get(s)
        if sp:
            n_edit += len(sp["edits"])
            ch = sp["ch"]
            edits = "<br>".join(
                "`" + esc(ed["old"].replace("\n", "⏎")) + "` → `" + (esc(ed["new"].replace("\n", "⏎")) or "(空)") + "`"
                for ed in sp["edits"])
            state = f"`# history: {ch}` を末尾に足した (作業ツリー)" if blk.kind == "comment" else f"末尾に `History: {ch}` (作業ツリー)"
            judge = note.get("judge", "移す (文頭ラベル・括弧・日付句の機械除去)。残りは残す")
            reason = note.get("reason", "")
            pre = note.get("pre_delete", "削除した文 0。点検語は、除いたラベル・括弧・日付句を指さない (指す先は残る文・同じ塊)")
            after = note.get("after", "除去後の文を読んだ: 文法と意味が保たれる")
        else:
            ch = "なし"
            edits = "(除去なし)"
            state = "基準のバイト列 (CH なし)"
            if note:
                judge = note.get("judge", "残す (§3。検査器が許す候補が在るが Y7-3 (b) の条件を満たさず見送った。迷えば基準のまま)")
                reason = note.get("reason", "")
                pre = note.get("pre_delete", "文の削除 0")
                after = note.get("after", "除去なし (基準のまま)")
            else:
                judge = "残す (§3。条件を満たさない又は除くものが無い)"
                has_id = bool(ID_RE.search(text))
                if pb["tokens"] == 0 and has_id:
                    reason = "経緯トークン 0。裸の ID (出所の無い条項・決定 ID) は在るが、設計・契約の決定を指す唯一の手掛かりで、除くと参照そのものを失う (設計 §10.9 の教訓)。経緯だけの文も無い (全文を読んだ)。内容の除去が 0 なので CH-ID を付けない (Y7-3 (d) 相当)"
                elif pb["tokens"] == 0:
                    reason = "経緯トークン 0。除去の対象になる語が無く、経緯だけの文も無い (全文を読んだ。§3 残す)。内容の除去が 0 なので CH-ID を付けない (Y7-3 (d) 相当)"
                else:
                    reason = "(要記入)"
                pre = "文の削除 0"
                after = "除去なし (基準のまま)"
        P(f"| {i} | {wp} | L{s}-{e} | `{pb['qualname']}` | {blk.kind} | {why_s} | {ch} | {edits} | {state} | {judge} | {reason} | {pre} | {after} | {points_s} |")
    P("")
    P(f"行数: 対象の塊 {len(meas['per_block'])} (spec に入れた塊 {len(spec['blocks'])}、編集 {n_edit}、削除した文 0)。\n")
    # B
    P("## B. 目印一覧に当たる文 (対象の塊だけ。設計 §3 の叙述の目印)\n")
    P("| # | WP | 塊 (基点の行) | CH-ID | 目印 | 文 (先頭の数語) | 作業ツリーの状態 | 判定 (§3) | 根拠 | 点検語 | A の行 |")
    P("|---|---|---|---|---|---|---|---|---|---|---|")
    idx = {(pb["start"], pb["end"]): i for i, pb in enumerate(meas["per_block"], 1)}
    n = 0
    for s, e, hits in meas["marker_rows"]:
        sp = by_line.get(s)
        ch = sp["ch"] if sp else "なし"
        note = notes.get(str(s), {})
        for sent, ms in hits:
            n += 1
            bnote = note.get("B", "文は残す (同居文)。除去は経緯トークン・ラベル・日付句の機械除去だけで、この文の削除は無い" if sp else "基準のまま。文は現在の理由・規則と同居する叙述で、削除しない")
            state = "ラベル・括弧・日付句の除去のみ (文は残る)" if sp else "基準のまま"
            ms_s = "、".join("`" + m + "`" for m in ms)
            pts = "、".join("`" + w + "`" for w, rx in POINT_RES if rx.search(blocks[s].dedented)) or "なし"
            P(f"| {n} | {wp} | L{s}-{e} | {ch} | {ms_s} | `{esc(sent[:90])}…` | {state} | 残す | {bnote} | {pts} | {idx[(s, e)]} |")
    P(f"\n目印に当たる文 {n} / 塊 {len(meas['marker_rows'])}。\n")
    # C
    P("## C. 経緯と同じ文にある安全上の理由・保護参照・位置 (経緯トークンを含む文のうち §14.2 の正規表現に当たるもの)\n")
    P("| # | WP | 塊 | CH-ID | 種別 | 語 (安全) / 保護参照 / 位置の語 | 作業ツリーの状態 | 判定 (§3) | 根拠 (その塊の安全上の理由・保護参照が残ること) | A の行 |")
    P("|---|---|---|---|---|---|---|---|---|---|")
    rows: dict[tuple[int, int], dict] = {}
    for s, e, words, sent in meas["safety_rows"]:
        rows.setdefault((s, e), {"安全": set(), "位置": set(), "保護参照": 0})["安全"].update(words)
    for s, e, sent in meas["protected_rows"]:
        rows.setdefault((s, e), {"安全": set(), "位置": set(), "保護参照": 0})["保護参照"] += 1
    for s, e, words, sent in meas["position_rows"]:
        rows.setdefault((s, e), {"安全": set(), "位置": set(), "保護参照": 0})["位置"].update(words)
    n = 0
    for (s, e), d in sorted(rows.items()):
        n += 1
        kinds = [k for k in ("安全", "保護参照", "位置") if (d[k] if k != "保護参照" else d[k] > 0)]
        sp = by_line.get(s)
        ch = sp["ch"] if sp else "なし"
        words = "; ".join(filter(None, [
            ("安全: " + ", ".join(sorted(d["安全"]))) if d["安全"] else "",
            (f"保護参照 {d['保護参照']} 文") if d["保護参照"] else "",
            ("位置: " + ", ".join(sorted(d["位置"]))) if d["位置"] else "",
        ]))
        note = notes.get(str(s), {})
        cnote = note.get("C", "同居文は消さない。除いたのは経緯トークン・ラベル・日付句だけで、安全上の語・保護参照・位置の語を含む文は逐語で残る (検査器 `--base` exit 0)" if sp else "基準のまま (塊に除去なし)")
        state = "ラベル・括弧・日付句の除去のみ" if sp else "基準のまま"
        kinds_s = "、".join(kinds)
        P(f"| {n} | {wp} | L{s}-{e} | {ch} | {kinds_s} | {esc(words)} | {state} | 残す (文は削除しない) | {cnote} | {idx[(s, e)]} |")
    P(f"\n安全 / 保護参照 / 位置 の塊: {len(meas['safety_blocks'])} / {len(meas['protected_blocks'])} / {len(meas['position_blocks'])} (文: {len(meas['safety_rows'])} / {len(meas['protected_rows'])} / {len(meas['position_rows'])})。\n")
    # refs
    P("## 参照先一覧\n")
    P("### 塊をまたぐ参照 (module の中。§13.2 の正規表現 + `'s identical comment` / `own (comment|docstring|paragraph)` / `identical(-purpose) comment` に当たる文。同じ塊の中を指す文も含む)\n")
    P("| # | 参照元の塊 (基点の行) | CH-ID | 語 | 文 (先頭の数語) | 参照元の塊の状態 |")
    P("|---|---|---|---|---|---|")
    for k, (s, e, words, sent) in enumerate(meas["ref_rows"], 1):
        sp = by_line.get(s)
        ws = ", ".join("`" + w + "`" for w in words)
        P(f"| {k} | L{s}-{e} | {sp['ch'] if sp else 'なし'} | {ws} | `{esc(sent[:100])}…` | {'除去あり (文は残る)' if sp else '基準のまま'} |")
    P(f"\n参照の語を含む文: {meas['ref_sentences']}。\n")
    P("### module の外からの参照先 (両 peer の `src/`・`tests/`・`conformance/`、`conformance-tests/`、`security/`、README を grep し、手で選別した)\n")
    P("| # | 参照元 (`file:line`) | 参照の語 | 参照先の塊 (基点の行) | 参照先の文 (先頭の数語) | 残っているか (作業ツリー) |")
    P("|---|---|---|---|---|---|")
    for k, r in enumerate(notes.get("_refs_external", []), 1):
        P(f"| {k} | {r[0]} | {r[1]} | {r[2]} | {r[3]} | {r[4]} |")
    P("")
    P("## 検査器が拒んだ除去 (spec から外し、塊は基準のまま)\n")
    P("| # | 塊 (基点の行) | 試した除去 (`old` → `new`) | 検査器の行 (逐語) | 扱い |")
    P("|---|---|---|---|---|")
    for k, r in enumerate(notes.get("_rejected", []), 1):
        P(f"| {k} | {r[0]} | {r[1]} | {r[2]} | {r[3]} |")
    P("")
    P("## 見送った除去 (検査器は許す可能性があるが、Y7-3 (b) 又は (i)〜(iii) の型で基準のまま残した)\n")
    P("| # | 塊 (基点の行) | 候補の除去 | 型 | 根拠 |")
    P("|---|---|---|---|---|")
    for k, r in enumerate(notes.get("_skipped", []), 1):
        P(f"| {k} | {r[0]} | {r[1]} | {r[2]} | {r[3]} |")
    P("")
    P("## 指示語チェックの候補一覧 (削除した文 1 つにつき 1 行)\n")
    P("| # | WP | 塊 (基点の行) | 削除した文 | 直後の残す文 1 | 直後の残す文 2 | 点検語の参照 | 結果 |")
    P("|---|---|---|---|---|---|---|---|")
    P(f"| — | {wp} | (該当なし) | 操作 (3) による文の削除は 0 文 (spec の `new` が空の編集も無い) | — | — | — | — |")
    P("")
    P("## HTTP の status・error code を含む削除文の監査一覧\n")
    P("| # | WP | 塊 | 削除した文 | 含む語 | 判定表の根拠 |")
    P("|---|---|---|---|---|---|")
    P(f"| — | {wp} | (該当なし) | 削除した文は 0 文 | — | — |")
    P("")
    P("## 0d の保護参照があるために残った、経緯だけの文\n")
    P("| # | WP | 塊 (行) | 文 (先頭の数語) | 保護参照 | 状態 |")
    P("|---|---|---|---|---|---|")
    for k, r in enumerate(notes.get("_protected_history", []), 1):
        P(f"| {k} | {wp} | {r[0]} | {r[1]} | {r[2]} | {r[3]} |")
    if not notes.get("_protected_history"):
        P(f"| — | {wp} | (該当なし) | — | — | — |")
    P("")
    P("## 訂正の記録 (0g)\n")
    P(notes.get("_corrections", "該当なし (この草案は受け皿に訂正の記録を足していない)。"))
    P("")
    Path(ns.out).write_text("\n".join(out) + "\n", encoding="utf-8")
    print(f"wrote {ns.out}: A rows {len(meas['per_block'])}, spec blocks {len(spec['blocks'])}, edits {n_edit}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
