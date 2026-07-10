# Delta Spec — UX Refinement: consistency + light theme + Insights redesign + mobile

## Goal (one line)
Enforce the **Electric Azure Dark** design system across every surface, add a real
**light theme** (auto + manual toggle), give the **Insights** tab a proper data-viz
identity with one signature motion moment, and make every view genuinely usable at
**375px** — UX/UI only, zero backend change.

## Design commitment (Gate-1, confirmed verbatim)
- **Purpose**: local single-user chess-coach cockpit. Each screen answers one thing —
  Play/Analysis: "how good was that move"; trainers: "what's the prepared line";
  Review: "where do I go wrong"; Insights: "what patterns should I fix".
- **Named aesthetic**: **Electric Azure Dark** (keep + enforce). Layered OKLCH surfaces,
  electric-azure accent, Inter UI + JetBrains Mono notation. Mood anchor: lichess-dark × Linear.
- **Scope**: all 6 tabs + board column + mode bars. Workstreams: (1) consistency+polish
  sweep, (2) deep redesign: Insights dashboard, (3) mobile pass at 375px.
- **Theming**: dark primary; new light theme, AA on every surface; auto via
  `prefers-color-scheme` + manual header toggle persisted through `prefs.js`.
- **Motion**: subtle base (existing 120/200ms tokens) + one signature moment:
  Insights charts animate-in (no replay on re-render). All reduced-motion-guarded.
- **A11y**: WCAG 2.2 AA both themes — 4.5:1 text / 3:1 UI, 24px min targets,
  `:focus-visible` everywhere. Screen-reader depth out of scope.
- **Breakpoints**: 375 + 1440 verified per view.
- **Anti-goals**: no indigo/violet gradient wash; no even same-size card grids; no
  centered-hero-two-buttons; no gradient blobs; no Inter-only; **no emoji as UI icons**
  (Lucide only); **no dense borders** — spacing + elevation over box-lines.

## In scope (work items)

### A. Theme foundation (light theme)
- **Mechanism**: pre-paint inline `<script>` in `<head>` reads localStorage
  `chess-training:ui:v1` → `theme` (`'light'|'dark'|'system'`, default `'system'`),
  resolves `system` via `matchMedia('(prefers-color-scheme: light)')`, sets
  `document.documentElement.dataset.theme = 'light'|'dark'` **before** `style.css` paints
  (kills FOUC — contracts risk #3). Inline script duplicates the storage-key read by
  design (cannot import modules pre-paint); key name stays in sync with `prefs.js:3`.
- **CSS**: dark values stay in `:root`; light overrides live in one
  `html[data-theme="light"] { … }` block in `style.css` redefining ONLY tokens —
  explicitly: surfaces, borders, text, accent trio, error, quality ramp, shadows, scrim,
  **AND every Section-B-derived token** (`--q-best-dim`, `--q-blunder-dim`,
  `--q-inaccuracy-dim`, `--accent-dim-hover`, `--q-blunder-border`, `--shadow-toast`).
  Each `-dim` token validated against its own PAIRED text/border color (4.5:1 text,
  3:1 UI), not just page surfaces (refuter major 2).
  **`color-scheme` keeps BOTH values in both themes** — `dark light` on `:root`,
  `light dark` in the light block (reorder only, never a single value): dropping `dark`
  reintroduces Chrome auto-dark force-inverting the black piece SVGs
  (refuter BLOCKER; load-bearing comment `index.html:6-9`, `style.css:9-11`).
- **Toggle**: header button (Lucide sun/moon/monitor, aria-label, ≥24px target) cycling
  system → light → dark; new standalone module `static/theme.js` (self-contained script;
  needs no injected `api`, imports `prefs.js` only — verified clean leaf ESM) — writes
  `writeUiPref('theme', …)`, updates `dataset.theme`. **matchMedia guard (refuter minor):**
  the `change` handler re-reads the stored pref via `readUiPrefs()` on every fire and
  no-ops unless it is `'system'` — an OS theme flip must never override an explicit
  manual choice.
- **Board stays theme-independent** (brown squares + cburnett pieces in both themes) —
  decided; conventional for chess UIs.
- **Quality colors**: light-theme variants of `--q-*` retuned to ≥4.5:1 on light surfaces.

### B. Token completion (unblocks A; contracts risk #4)
Convert all 9 raw `oklch()` literals outside `:root` to new semantic tokens:
`--eval-bar-black` / `--eval-bar-white` (theme-INDEPENDENT, chess-semantic —
`panel.css:20,31`); `--q-best-dim` / `--q-blunder-dim` / `--q-inaccuracy-dim`
(`review.css:281-283,356`); `--accent-dim-hover` (`review.css:346`);
`--q-blunder-border` (`review.css:351`); toast shadow → new `--shadow-toast` preserving
the existing `0 2px 8px` geometry (`review.css:790`) — NOT `--shadow-md`, which has a
different two-layer silhouette (refuter minor: token completion must not smuggle in a
visual change). Delete dead aliases `--bg` / `--panel-bg` (`style.css:28-29`, zero
consumers — refuter-verified).

### C. Consistency + polish sweep (app-wide)
- Normalize 3 plain-`:focus` sites in `review.css` (411, 448, 734) to the app-standard
  `:focus-visible { outline: 2px solid var(--accent) }` pattern; remove `outline: none`.
- Remove orphaned `body.review-mode` toggle (`app.js:1842` — no CSS consumer; contracts
  risk #5). Only `app.js` edit in this pass.
- Add explicit reduced-motion override for `@keyframes review-toast-in` (`review.css:800`).
- Border-diet per anti-goals: where panels use box-lines for grouping, prefer spacing +
  surface elevation; keep hairlines (`--border-subtle`) only where grouping fails.
- Icon audit: emoji/entity glyphs in UI controls → Lucide (text labels kept).
  **Scope clarification (refuter low):** chess-piece Unicode glyphs (♔–♟ in setup
  palette + promo dialog) are domain notation, NOT UI icons — they STAY. In scope for
  Lucide swap: directional stepper arrows (`index.html:118-129` trap-stepper ⏮◀▶⏭ →
  ChevronFirst/Left/Right/Last) and any similar generic control glyphs.
- Microcopy/empty-state consistency: all empty/loading states use `.empty-state` /
  existing feedback patterns (never redefine `.empty-state` — owned by `style.css:546`).

### D. Insights deep redesign (data-viz identity)
- Visual rework of `insights.css` + markup inside `insights.js` render functions:
  coverage as stat blocks; win-rate families/lines as horizontal token-colored bars with
  tabular-nums; adherence/theory as compact metric rows; mistake clusters as ranked cards
  with quality-color accents; time-trouble buckets as a mini bar row.
- **Signature motion**: on first build of each sub-panel only (piggyback existing
  `_shellBuilt` / `_mistakesLoaded` one-shot guards), staggered fade/slide-in of sections
  + bar-fill sweep. Never replays on sub-tab switch. Reduced-motion: instant.
- **Preserved contracts** (binding, from `contracts/ux-refinement-ux.md`): all
  `#insights-*` IDs + `role=tab/tablist/tabpanel` + `.is-active` pattern (generic rule
  `style.css:435`); lazy fetch-once sequencing untouched; per-metric min-sample gating
  rendering (`renderGatedLine`/`renderThinData`) stays per-metric, "one long-run trend,
  always visually secondary"; deep-link `_api.actions.openGameAtPly(gameId, ply)` call
  signature + clickable button; ALL JSON key reads unchanged (`book_exit_ply===0`
  sentinel, `'<10s'` bucket literal, `clusterDisplayName()` suffix strip).

### E. Mobile 375 pass
- **375px overflow is real today, not hypothetical** (refuter major 3): available main
  content = 375 − 32 (padding) = 343px, but eval-bar(14) + gap(8) + board(92vw=345) =
  367px → 24px overflow. **Concrete fix**: at the ≤560px tier, size the board as
  `width/height: calc(92vw - 22px)` (yields eval-bar + gap), with `#eval-bar
  min-height` matching — or equivalent flex-yield (`#board flex: 1 1 auto; min-width: 0`)
  keeping the board square. Verify at exactly 375px.
- Every tab + mode bar verified at 375px: no horizontal overflow, panel readable below
  board, mode bars wrap.
- Touch targets ≥24×24 CSS px (WCAG 2.2 AA) on all interactive controls; enlarge
  `.trap-chip-dismiss`, `.rep-line-practice`. **`.movelist-move`: the SC 2.5.8 spacing
  exception does NOT apply** (rows are flush, ~21-22px tall, zero row-gap — refuter
  major 4). Fix: mobile-only (≤820px) hit-box increase via `.movelist-move` padding to
  ≥24px computed height; desktop density unchanged.
- Review the 561–820px band where fixed 480px widths persist — bump breakpoints only
  if something visibly breaks; no layout rearchitecture.

## Out of scope (explicit)
Backend / `app/` code (except deleting the one orphaned `classList.toggle` line) ·
insights fetch/refresh logic or any JSON-shape change · live-refresh of Insights ·
ARIA board/movelist semantics, live-region announcements · board square/piece light
theming · review.js replay logic · eval graph / new features · `app.js` module split ·
tablet (768) verification.

## Constraints (binding)
- Profile invariants: modules receive injected `api`, never import from `app.js`
  (`theme.js` imports `prefs.js` only — allowed, `prefs.js` is a leaf); tokens-only CSS —
  after this pass the grep gate is: **no `oklch(`/`#hex`/`rgb(` outside `style.css`
  token blocks**; AA contrast both themes; `:focus-visible` on all interactive controls.
- JS-coupled classnames (contracts §JS-coupled) must not be renamed CSS-side without the
  matching JS edit — this pass renames none.
- `body[data-mode]` selector list (`style.css:441-453`) keeps `review` mode EXCLUDED
  (panel must stay visible in review mode) — contracts risk #2.
- localStorage key/shape `chess-training:ui:v1` unchanged (flat JSON, new `theme` key only).
- No debug artifacts committed (console.log, screenshots, `.playwright-mcp/`).
- Commit policy: implemented + verified + reviewed; Conventional Commits; feature branch.

## Verify-by (end-to-end)
1. `pytest` green (no backend change); `ruff check app tests` clean.
2. **Grep gate**: no raw color literals outside `style.css` token blocks
   (`grep -nE 'oklch\(|#[0-9a-fA-F]{3,8}\b|rgb\(' static/*.css` → only `:root` +
   `[data-theme="light"]` blocks + comments).
3. **Playwright matrix**: {dark, light} × {375, 1440} × all 6 tabs + setup/trap/review/rep
   mode bars — load, interact, screenshot; **0 console errors**; no horizontal overflow
   at 375; theme toggle cycles + persists across reload; **no FOUC** on hard reload in
   each stored state; system-mode follows emulated `prefers-color-scheme`.
4. Insights: sub-tabs render all sections; animate-in plays once on first open only;
   deep-link button enters review mode at correct ply; thin-data gating lines intact.
5. Reduced-motion emulation: no transitions/animations anywhere.
6. AA contrast spot-check both themes (text, quality colors, focus rings ≥3:1).
7. **design-reviewer pass** (maker ≠ checker) grading against the Gate-1 commitment on
   all in-scope pages at both breakpoints, both themes → verdict `pass`.

## Refuter resolutions (folded in above — summary)
Verdict was **needs-changes**; all issues resolved inline:
1. **(blocker)** `color-scheme` keeps both values per theme (`dark light` / `light dark`),
   never a single value — prevents Chrome auto-dark piece-SVG inversion. → §A.
2. **(major)** Light block explicitly overrides every Section-B derived token; each `-dim`
   validated against its PAIRED text/border color. → §A.
3. **(major)** 375px overflow (24px, real in current CSS) gets a concrete dimension fix:
   `calc(92vw - 22px)` board or flex-yield. → §E.
4. **(major)** `.movelist-move` spacing exception rejected; mobile-only hit-box padding
   to ≥24px instead. → §E.
5. **(minor)** Toast shadow → dedicated `--shadow-toast` preserving `0 2px 8px` geometry.
   → §B.
6. **(minor)** matchMedia handler no-ops unless stored pref is `'system'`. → §A.
7. **(low)** Chess-piece Unicode glyphs stay (domain notation); only generic control
   glyphs (trap-stepper arrows) go Lucide. → §C.

Refuter-verified baselines: pytest **513 passed**; ruff clean; raw-color census = exactly
the 9 listed sites; `.review-mode` orphan confirmed (zero CSS/JS consumers); insights
animate-once-via-existing-guards claim verified sound; `prefs.js` clean leaf ESM;
grep gate feasible with no undocumented exceptions.
