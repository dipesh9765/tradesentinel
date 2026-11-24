# Design notes

TradeSentinel is a trading desk, so it is drawn like a ledger: flat panels with hairlines, prices in
a tabular monospace face so columns line up, one accent colour, and the up and down colours kept for
price movement only. The tokens in `src/tokens.css` are shared with the other web projects in this
portfolio (see `SIH-Big-Data-Searching/web/DESIGN.md` for the full reasoning and the rules taken from
[Hallmark](https://github.com/nutlope/hallmark)).

## What changed from the first version

| Before | Now |
| --- | --- |
| Cyan-on-navy neon, glow shadows on every card | Light and dark from the system setting; one vermilion accent |
| Glass panels with backdrop blur, gradient buttons | Flat panels, flat buttons |
| Google Fonts (Outfit, JetBrains Mono) fetched at load | System faces; no third-party request |
| Confetti when a trade was approved | Removed. A confirmation is not a celebration, and the dependency is gone |
| Shouted copy (LIVE TRADING (REAL ORDERS)), emoji as icons, tracked capitals | Sentence case, no emoji |
| Chart colours hard-coded in the canvas code | Resolved from the tokens on every draw, so light and dark both work |
| `transition: all`, animating width and height | Named properties; the countdown and level bars scale with `transform` |

## Honest limits

- About 300 inline `style={{}}` objects remain in the components. Every colour in them now comes from
  a token and the checker enforces that, but they should become classes. `npm run check:design`
  skips the inline-style rule for this reason (`--skip=inline-style`); it is the one rule this
  project does not meet yet.
- Checked in a real browser against a stand-in backend at 375px and 1280px, light and dark: no
  horizontal overflow, no text under 4.5:1 contrast in either scheme, no console errors, no third-party
  requests. Not checked: a live Zerodha session, the voice radar with a real microphone, Safari.
