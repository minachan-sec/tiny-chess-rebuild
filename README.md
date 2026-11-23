# tiny-chess-rebuild

![tiny-chess-01](https://make.fun/badge/tiny-chess-01.svg)
![rank](https://make.fun/badge/tiny-chess-01/minachan-sec/tiny-chess-rebuild/rank.svg)
![reward](https://make.fun/badge/tiny-chess-01/minachan-sec/tiny-chess-rebuild/reward.svg)

A chess engine for make.fun's **tiny-chess-01** — "Build the strongest chess
engine in 4 KB of Python".

`main.py` (3,942 bytes) is the entry: the `makefun compress` packing of
`src.py`, the readable source in this repo. The engine is a 0x88-board
negamax search with alpha-beta and PVS, quiescence search with check
evasions, late-move reductions, a transposition table used for move
ordering, MVV-LVA capture ordering, and a piece-square evaluation with
passed-pawn terms. It thinks under a fixed node budget — never a clock —
so a replayed trial reproduces the same moves.

Local practice gauntlet (kit trial 0, sealed scorer): **Elo 1279**
(3 won / 0 drawn / 3 lost, all six games finished cleanly), above the
1,154-point practice floor.

## Layout

- `src.py` — the engine source, written to be read.
- `main.py` — the packed entry, produced by `makefun compress src.py`.
- `.makefun/` — make.fun anchor and owner records.

## License

MIT — see `LICENSE`.
