# Delta spec — Move AI game commentary into the Analysis panel

**Goal:** Relocate the review-mode AI commentary block from the center card (under
the board, below the accuracy %) into the right **Analysis** panel, laid out
**side-by-side to the right of the Evaluation readouts** — filling the horizontal
space that is otherwise wasted on a wide/full-screen window.

## Why
On full screen the Analysis panel is wide and mostly empty beside the small eval
number; the commentary meanwhile sits in a full-width center card. User wants
commentary + evaluation to read together, at the same level, in one panel.

## Current state (verified in browser + source)
- `#review-narrative` (the "AI Game Commentary" story block, incl. its
  "Generate commentary" CTA) lives inside `#review-bar` in the center
  `<section>`, as a sibling of `#review-game-summary` (accuracy %) and
  `#review-foresight`. `static/index.html:175`.
- `renderNarrativePanel()` (`static/review.js:857`) resolves its host via
  `byId('review-narrative')` — **id-based, DOM-location-independent**. Moving the
  node needs no change to the render logic.
- Today the block hides on review exit **only because** its parent `#review-bar`
  gets `hidden` in `showReviewUI(false)` (`static/app.js:732`). `.review-narrative`
  itself already collapses via `.review-narrative[hidden]{display:none}`
  (`static/review.css`).
- Analysis panel order (`#tab-analysis`): status → `#engine-restart-btn` →
  `.analyze-color-row` → `.eval-block` → `.quality-block` → `.best-block` →
  `.movelist-block`. Eval blocks have no conflicting flex CSS.
- Layout: `main` is single-column at `≤820px` (panel drops below board); panel
  width is not a fixed function of viewport → prefer flex-wrap over a hardcoded
  breakpoint.

## Change
**Files to touch:**
- `static/index.html` — remove `#review-narrative` from `#review-bar`; wrap
  `.eval-block` + `.quality-block` + `.best-block` in a left column, and place
  `#review-narrative` as the right column inside a new flex row:
  ```html
  <div class="analysis-eval-row">
    <div class="analysis-eval-col">
      …eval-block / quality-block / best-block (unchanged)…
    </div>
    <div id="review-narrative" class="review-narrative" hidden></div>
  </div>
  ```
- `static/style.css` — add the two-column row (panel owner). Flex-wrap so it
  auto-stacks when the panel is too narrow; when `#review-narrative` is `hidden`
  (`display:none`) the left column fills the row. **The eval blocks lose their
  free vertical rhythm once nested** — today `.eval-block`/`.quality-block`/
  `.best-block` are direct children of `.panel > [role="tabpanel"]` which supplies
  `gap: var(--space-5)`; none carry own margins (`grep` → zero CSS hits). The new
  `.analysis-eval-col` MUST re-supply that gap or the three blocks render with
  zero spacing (refuter, high):
  ```css
  .analysis-eval-row { display:flex; flex-wrap:wrap; gap:var(--space-4);
                       align-items:flex-start; }
  .analysis-eval-col { flex:1 1 200px; min-width:0;
                       display:flex; flex-direction:column; gap:var(--space-5); }
  .analysis-eval-row > .review-narrative { flex:1 1 240px; min-width:0; }
  ```
- `static/review.css` — **likely no change needed.** The narrative block's old
  visual separation came structurally from `#review-bar`'s gap and
  `#review-game-summary`'s `border-bottom`, NOT from any margin/border on
  `.review-narrative*` itself (refuter verified: zero such rules). Only touch it
  if the browser check reveals a real gap issue; if so, tokens-only, no raw hex.
- `static/app.js` — in `showReviewUI(on)`, explicitly hide the narrative on exit
  now that it no longer lives under `#review-bar`:
  `if (!on) byId('review-narrative').hidden = true;`
- `static/review.js` — update the stale comment at `:852-854` ("a sibling of
  #review-game-summary") to reflect the new home.

## Out of scope
- The accuracy % block (`#review-game-summary`) and pre-blunder foresight cards
  (`#review-foresight`) STAY in the center card under the board — not moved.
- The in-replay narrative **moment cards** (appended into `#review-foresight`,
  `review.js:763`) are a different feature — untouched.
- No change to narrative generation, the `/api/games/{id}/narrative` contract, or
  any backend / DB.
- No change to eval / best-move logic or the movelist.

## Constraints (from profile invariants)
- Frontend modules receive an injected `api`; never import from app.js. (No new
  cross-module import — `showReviewUI` already lives in the app.js hub.)
- Tokens-only CSS (no raw hex), AA contrast, `:focus-visible` on interactive
  controls (the Generate/Regenerate/Read-more buttons keep their existing classes).
- No DB schema change. Pure modules stay engine-free.

## Verify-by (end to end)
1. `.venv/bin/python -m pytest -q` passes; `.venv/bin/ruff check app tests` clean
   (no backend change expected, but confirm nothing broke).
2. Live server + Playwright-MCP at **1920px wide**: open a saved game in Review →
   click **Generate commentary** → the commentary renders in the Analysis panel,
   **right of the Evaluation readouts**, filling the previously-empty space; Moves
   list stays below at full width.
3. Narrow the window (panel narrow / ≤820px single-column): the commentary
   **stacks below** the eval readouts, full width — no overflow, no clipping.
4. Click **Return to my game** (exit review) → the commentary is **gone** from the
   Analysis panel; the eval column fills the row normally in play mode.
5. Re-open the game → commentary reappears in the panel. Center card still shows
   only title + accuracy % (no commentary under the board).
