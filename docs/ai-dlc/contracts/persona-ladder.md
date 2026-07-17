# Contracts — B4: Persona ladder (play-vs-bot)

Read-only scan (contract-mapper, 2026-07-16). Evidence is `file:line`.

## 1. Bot engine strength — `app/bot_engine.py`
- Strength is a **process-global UCI config applied whole on every (re)spawn**:
  `BOT_ENGINE_OPTIONS = {Threads:1, Hash:16, UCI_LimitStrength:True,
  UCI_Elo:1350}` (`:59-64`), applied atomically in `start()` via
  `engine.configure(...)` (`:190`). Kept as one dict so start + watchdog-restart
  cannot drift (`:56-58`, `:19-23`).
- **No per-request/per-game strength param.** `candidates(fen, k)` (`:331`) takes
  only FEN + count. Confirmed the ISOLATED engine (own subprocess, own lock
  `:158`, no `game=`/`ucinewgame` `:298-301`); never touches the shared analysis
  engine → `note_interactive_start/end` does NOT apply.
- Restart re-applies the FULL option set lazily (`:258-266`, `:287-288`) — the
  guard against a restart silently dropping the weakening.

**Sharp edge:** per-persona `UCI_Elo` mutation must become **instance state that
`start()` reads**, else a watchdog restart re-applies the hardcoded 1350 and
silently resets the persona's strength. Persona switch happens **between games**
(color/persona locked mid-game, §3) → reconfigure at next-game-start (or restart
per switch — cheap, loses warm TT) is sufficient; no mid-move reconfigure.
**`UCI_Elo` min ≈ 1320** → personas below that need `Skill Level` (0–20).

## 2. Bot routes — `app/main.py`
- `BOT_PERSONA_LABEL = "Casual sparring bot"` (`:575`), fuzzy, no Elo claim.
- `POST /api/bot/move` request is `{fen}` only (`:578-581`) → **add persona/
  strength here** and reconfigure/select at request time (keep server stateless
  `:568`). Plays `candidates(fen, k=1)[0]` (`:652`, `:674`); bot failure → 503.
- `GET /api/bot/status` → `{available, personaLabel, maia}` (`:592-602`).
- `POST /api/bot/save` `{...personaLabel, rated}` → `personaLabel` becomes the
  PGN player name (`:759-762`); `headers_json` stores verbatim (`:773`, `:889`).
  **Persona rating/id can ride `headers_json` — no schema change** (B8 reads it).

## 3. Frontend — `static/botplay.js` / `app.js` / `index.html`
- `startGame()` reads color (`:281`), `rated` fresh from `#bot-rated` (`:282`,
  not persisted), `personaLabel` from `#botplay-persona` text (`:298`).
- Color/rated locked while busy or mid-game (`wireColorPicker` `:157-164`) — a
  persona picker must follow the same guard, live in `#botplay-body` next to the
  color radiogroup (`index.html:122-135`), wired in `initBotplay()` (`:562-578`).
- **Persona pref persists via `prefs.js`** (`readUiPrefs`/`writeUiPref`, key
  `chess-training:ui:v1`) mirroring analyzeColor/engineSpeed/theme — NOT the
  session slot. `personaLabel` already round-trips in the session slot
  (`app.js:187`, `:280-291`); a persona **id/rating** needs adding if it must
  survive refresh. Module boundary holds (injected `api`, never imports app.js).

## 4. Opening book — `app/book.py`
- **Membership SET only**: `is_book_move(fen, uci)`→bool (`:207-223`); used to
  skip Stockfish on in-book moves (`main.py:473`). **No weighted move-picker
  exists** — B4's per-persona book is net-new stochastic selection.
- **Import-safe JSON loader idiom to mirror** (`book.py`/`repertoire.py`/
  `traps.py`): module singleton, `os.environ.get(<ENV>, "data/<file>.json")`,
  missing/invalid → one warning + empty, never raise. `data/personas.json`
  should mirror this, loaded in `lifespan` (`main.py:137-154`) after `book.init`.
- Book-move override slots in **before** `bot.candidates(fen, k=1)`
  (`main.py:652`); the `k>1` seam (`bot_engine.py:29-32`) is ready to feed a
  distribution. Selection must be **stochastic** (repeat games diverge) — new to
  the currently-deterministic pipeline; keep it seedable/pure.

## 5. Persistence + data
- Session slot `chess-training:session:v1` embeds `botGame{...personaLabel...}`
  (`app.js:177-201`). UI-pref slot `chess-training:ui:v1` for the selected-persona
  pref. `data/personas.json` committed (catalog), unlike gitignored game data.

## Sharp edges (ranked)
1. **`UCI_Elo` floor 1320 blocks the 800 end** — sub-1320 personas need
   `Skill Level`; the strength MODEL changes, not just the number.
2. **Per-persona strength must survive a watchdog restart** — persona target →
   instance state `start()` re-applies, or it reverts to 1350.
3. **Book is membership-only** — weighted move *selection* is net-new stochastic
   code, intercepting before `candidates()` (`main.py:652`).
4. **Persona threads through the move request** or server state breaks
   statelessness — carry persona per request, reconfigure at request time.
5. **`personaLabel` display round-trips; rating/id do not** — pref via
   `prefs.js`, saved-game persona metadata via `headers_json` (no schema change).
