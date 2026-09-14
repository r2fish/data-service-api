# docs/code-history/ -- コード内経緯コメントの受け皿

正本設計: `docs/design/CODE_COMMENT_PROVENANCE_V1.md` (D-1 / D-2)。この
README 自体は受け皿の走査対象外である (走査対象は `<peer>/*.md` と
`pair.md` だけ。`tools/check_comment_provenance.py --register`)。

## 置き場所

- peer ごとの companion: `docs/code-history/<peer>/<module>.md`
  (`<peer>` は `r2db-api` / `MitateDB-api`、`<module>` は移動時点のファイル
  名。後の抽出で symbol が移っても節は動かさない)。
- 登録 helper (`_ISOMORPHIC_TARGETS` 等) 用: `docs/code-history/pair.md`
  (最後の専用変更セットまで対象外)。

## 節の形

```
## CH-NNNN

- moved from: `<peer 相対パス>` (`<qualname>`)
- parent commit: `<親コミットの sha>`
- kind: comment | docstring

```
<移した塊の全体。dedent 後、逐語>
```
```

- `CH-NNNN` は 4 桁、両 peer 通しの連番。再利用しない。
- fenced block の中身は、移動元コードの塊全体 (dedent 後) と byte 一致する
  こと (`--base` 照合)。要約・言い換えをしない。
- 各節はその変更セットの親コミット時点の写しである。後のコード変更に合わ
  せて書き換えない。

## CH-ID の規則

- 形は `CH-NNNN`。module・symbol・peer の名を含めない。
- 1 塊 = 1 ID。塊とは、同じインデントで連続する `#` 行の最大の並び (空行
  で切れる)、又は 1 つの docstring である。
- コード側の参照行は 2 形だけ:
  - `#` 塊: `# history: CH-NNNN` を 1 行 (残した文があるときは塊の末尾行)。
  - docstring: 末尾に `History: CH-NNNN` を 1 行。
- 新旧の塊の対応は CH-ID で取る (位置では取らない)。

詳細な判定基準・照合方法は設計 §3〜§4 を正本とする。
