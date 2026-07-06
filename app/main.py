"""FastAPI app for the Stockfish Analysis Board.

Wires together the engine wrapper (:mod:`app.engine`), the pure classification
logic (:mod:`app.analysis`), and the request/response schemas
(:mod:`app.models`), and serves the static frontend.

Server responsibilities (see docs/design/specs/stockfish-analysis-board.md):

* Authoritative legality check with python-chess on every move.
* Build the single shared ``Analysis`` object the same way for every endpoint.
* For ``/api/move`` run TWO depth-pinned analyses (before + after) so the
  move-quality label is comparable, classified via :func:`app.analysis.classify`.

The server is stateless per request: move history / undo lives client-side.
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

import chess
from fastapi import Depends, FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app import (
    accuracy,
    book,
    coaching,
    insights,
    openings,
    pgn,
    profile,
    repertoire,
    review,
    storage,
    trainer,
    traps,
)
from app.analysis import classify, cp_loss, pov_score_to_white_cp
from app.engine import DEFAULT_DEPTH, AnalysisResult, EngineUnavailable, StockfishEngine
from app.models import (
    Analysis,
    AnalyzeAllResponse,
    AnalyzeRequest,
    AnalyzeResponse,
    AnalyzeStatusResponse,
    BestLine,
    CoverageDict,
    EndgameInsightsResponse,
    EngineRestartResponse,
    EngineStatusResponse,
    GameAccuracySummary,
    GameDetail,
    GameSummary,
    ImportRequest,
    ImportResponse,
    LoadRequest,
    LoadResponse,
    MistakesInsightsResponse,
    MoveRequest,
    MoveResponse,
    NarratedLeak,
    OpeningRequest,
    OpeningsInsightsResponse,
    PlyDetail,
    ProfileResponse,
    RetagRequest,
    RetagResponse,
    ReviewResponse,
    SetColorRequest,
    TrainerBucketCompleteRequest,
    TrainerBucketCompleteResponse,
    TrainerCheckRequest,
    TrainerCheckResponse,
    TrainerPreviewResponse,
    TrainerSessionResponse,
    TrainerStatsResponse,
    TrapsCheckRequest,
)

logger = logging.getLogger("chess_trainer")

BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"
INDEX_HTML = STATIC_DIR / "index.html"
OPENINGS_DIR = BASE_DIR / "data" / "openings"
TRAPS_FILE = BASE_DIR / "data" / "traps.json"
BOOK_FILE = BASE_DIR / "data" / "book.json"
REPERTOIRE_FILE = BASE_DIR / "data" / "repertoire.json"
GAMES_DIR = BASE_DIR / "data" / "games"


# ---------------------------------------------------------------------------
# Lifespan: own exactly one engine instance. Try to start it eagerly so a
# missing binary is reported at boot, but DON'T crash the app if it's absent —
# the frontend + FEN-validation routes still work, and engine routes return 503.
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    engine = StockfishEngine()
    app.state.engine = engine
    if os.environ.get("CHESS_SKIP_ENGINE_AUTOSTART"):
        # Tests set this so each TestClient lifespan doesn't spawn a real Stockfish
        # (they inject fake engines via dependency_overrides). Real-engine tests start
        # their own engine directly and are unaffected. Never set in production.
        logger.info("Engine autostart skipped (CHESS_SKIP_ENGINE_AUTOSTART set).")
    else:
        try:
            engine.start()
            logger.info("Stockfish engine started.")
        except EngineUnavailable as exc:
            logger.warning("Stockfish unavailable at startup: %s", exc)

    # Opening name detection + traps + repertoire (all degrade gracefully if absent).
    openings.init(str(OPENINGS_DIR))
    traps.init(str(TRAPS_FILE))
    repertoire.init(str(REPERTOIRE_FILE))  # needs traps loaded first (trapId leaves)

    # Opening-book fast-path: derive a set of repertoire positions from the lichess
    # lines (scoped by data/book.json) + trap mainlines + curated repertoire lines.
    # Guarded so a malformed line can never crash startup — the API tests run this real
    # lifespan via TestClient. Repertoire lines are full-from-start lines that must
    # bypass the book.json firstMoves filter, so they ride the trap_ucis slot.
    try:
        book.init(
            str(BOOK_FILE),
            lines=openings.iter_lines(),
            trap_ucis=list(traps.iter_mainline_ucis()) + list(repertoire.iter_lines()),
        )
    except Exception as exc:  # pragma: no cover - defensive; book degrades to empty
        logger.warning("Opening book unavailable (continuing without it): %s", exc)

    # Game-review storage: init DB, scan data/games/ for PGN files, reset stuck jobs.
    storage.init()
    _import_games_folder()
    try:
        review.reset_stuck()
    except Exception as exc:
        logger.warning("review: reset_stuck failed at startup: %s", exc)

    try:
        yield
    finally:
        engine.close()


def _import_games_folder() -> None:
    """Scan data/games/ for *.pgn files and import them into storage (deduped).

    Wraps each file in try/except so a bad PGN file never crashes startup.
    """
    if not GAMES_DIR.is_dir():
        return
    now = datetime.now(timezone.utc).isoformat()
    for pgn_path in GAMES_DIR.glob("*.pgn"):
        try:
            text = pgn_path.read_text(encoding="utf-8", errors="replace")
            parsed_games = pgn.parse_games(text)
            for g in parsed_games:
                try:
                    gid = storage.insert_game({
                        "content_hash": g.content_hash,
                        "pgn": g.pgn,
                        "headers_json": None,
                        "white": g.white,
                        "black": g.black,
                        "result": g.result,
                        "eco": g.eco,
                        "opening": g.opening,
                        "date": g.date,
                        "my_color": g.my_color,
                        "source": str(pgn_path.name),
                        "ply_count": g.ply_count,
                        "imported_at": now,
                    })
                    # Write per-ply rows if not already present (backfills dedup re-imports).
                    if not storage.get_plies(gid):
                        storage.write_plies(gid, [
                            {"ply": p.ply, "san": p.san, "uci": p.uci,
                             "fen_before": p.fen_before, "clock_centis": p.clock_centis}
                            for p in g.plies
                        ])
                except Exception as exc:
                    logger.warning("startup import: failed to insert game from %s: %s", pgn_path.name, exc)
        except Exception as exc:
            logger.warning("startup import: failed to read/parse %s: %s", pgn_path.name, exc)


app = FastAPI(title="Stockfish Analysis Board", lifespan=lifespan)


@app.middleware("http")
async def no_store_static(request: Request, call_next):
    """Send ``Cache-Control: no-store`` for ``/static`` and the SPA shell.

    StaticFiles has no headers kwarg, so we set it here — this also covers the
    304 Not-Modified path. Retires the manual ``?v=`` cache-buster in
    static/index.html: stale browser-cached JS has bitten this repo before.
    ``/`` is included so a cached index.html can never pair stale markup with
    fresh JS (a DOM-id mismatch that no ``/static`` header alone prevents).
    """
    response = await call_next(request)
    path = request.url.path
    if path == "/" or path.startswith("/static"):
        response.headers["Cache-Control"] = "no-store"
    return response


def get_engine(request: Request) -> StockfishEngine:
    """Dependency: the app's single engine instance (overridable in tests)."""
    return request.app.state.engine


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _to_best_line(result: AnalysisResult | None) -> BestLine | None:
    """Map a raw engine line to the compact :class:`BestLine` shape (White-POV).

    Returns ``None`` when *result* is ``None`` so callers can pass an absent 2nd
    line / retrospective straight through.
    """
    if result is None:
        return None
    white = result.score.white()
    if white.is_mate():
        eval_cp: int | None = None
        mate: int | None = white.mate()
    else:
        eval_cp = int(white.score())
        mate = None
    pv_san = result.pv_san
    return BestLine(
        moveSan=pv_san[0] if pv_san else None,
        moveUci=result.pv[0].uci() if result.pv else None,
        pvSan=pv_san,
        evalCp=eval_cp,
        mate=mate,
    )


def _build_analysis(
    result: AnalysisResult,
    quality: str | None = None,
    second_line: AnalysisResult | None = None,
    retro_best: AnalysisResult | None = None,
    retro_second: AnalysisResult | None = None,
) -> Analysis:
    """Construct the shared ``Analysis`` object from a raw engine result.

    ``bestMoveSan`` / ``pvSan`` describe the analyzed (resulting) position;
    ``quality`` is supplied only when a prior move exists. ``second_line`` is the
    2nd-best line for *result*'s position; ``retro_best`` / ``retro_second`` are
    the best / 2nd-best lines for the position BEFORE the move (what the mover
    should have played) — all optional and ``None`` when unavailable.
    """
    white = result.score.white()
    if white.is_mate():
        eval_cp: int | None = None
        mate: int | None = white.mate()
    else:
        eval_cp = int(white.score())
        mate = None

    pv_san = result.pv_san
    best_move_san = pv_san[0] if pv_san else None
    best_move_uci = result.pv[0].uci() if result.pv else None

    return Analysis(
        evalCp=eval_cp,
        mate=mate,
        evalWhitePov=pov_score_to_white_cp(result.score),
        bestMoveSan=best_move_san,
        bestMoveUci=best_move_uci,
        pvSan=pv_san,
        quality=quality,
        secondLine=_to_best_line(second_line),
        retroBest=_to_best_line(retro_best),
        retroSecond=_to_best_line(retro_second),
    )


def _engine_unavailable_response() -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content={
            "detail": (
                "Stockfish engine is not available. Install it "
                "(`brew install stockfish`) or set STOCKFISH_PATH, then restart."
            )
        },
    )


# ---------------------------------------------------------------------------
# API routes
# ---------------------------------------------------------------------------
@app.post("/api/analyze", response_model=AnalyzeResponse)
async def analyze_position(
    req: AnalyzeRequest, engine: StockfishEngine = Depends(get_engine)
):
    """Analyze a position (no prior move → ``quality`` is null)."""
    try:
        chess.Board(req.fen)  # validate
    except ValueError:
        return JSONResponse(status_code=400, content={"detail": "Invalid FEN."})
    try:
        result = await engine.analyze(req.fen)
    except EngineUnavailable:
        return _engine_unavailable_response()
    return AnalyzeResponse(analysis=_build_analysis(result, quality=None))


@app.post("/api/load", response_model=LoadResponse)
async def load_fen(req: LoadRequest, engine: StockfishEngine = Depends(get_engine)):
    """Validate a FEN and, if valid, return its analysis (no quality label)."""
    try:
        board = chess.Board(req.fen)
    except ValueError as exc:
        return LoadResponse(valid=False, fen=None, analysis=None, error=f"Invalid FEN: {exc}")
    try:
        result = await engine.analyze(board.fen())
    except EngineUnavailable:
        return _engine_unavailable_response()
    return LoadResponse(
        valid=True,
        fen=board.fen(),
        analysis=_build_analysis(result, quality=None),
        error=None,
    )


@app.post("/api/move", response_model=MoveResponse)
async def make_move(req: MoveRequest, engine: StockfishEngine = Depends(get_engine)):
    """Validate + apply a move, then analyze before/after and label its quality.

    Runs two depth-pinned analyses (before and after the move) so the cpLoss is
    computed from comparable evals. Returns the resulting position's analysis.
    """
    # Parse the position. A bad FEN means we can't validate the move → illegal.
    try:
        board = chess.Board(req.fen)
    except ValueError:
        return MoveResponse(legal=False, fen=None, lastMoveSan=None, analysis=None)

    # Parse + legality-check the move (UCI, possibly with a promotion suffix).
    try:
        move = chess.Move.from_uci(req.move)
    except (ValueError, chess.InvalidMoveError):
        return MoveResponse(legal=False, fen=None, lastMoveSan=None, analysis=None)
    if move not in board.legal_moves:
        return MoveResponse(legal=False, fen=None, lastMoveSan=None, analysis=None)

    mover_is_white = board.turn == chess.WHITE
    last_move_san = board.san(move)  # render SAN BEFORE pushing

    fen_before = board.fen()
    board.push(move)
    fen_after = board.fen()

    # Opening-book fast-path: when the client opts in (play mode) and the move stays
    # in book, return instantly WITHOUT touching the engine. Legality is already
    # checked above, so this only ever short-circuits a valid move.
    if req.useBook and book.is_book_move(fen_before, req.move):
        opening = openings.name_for_fen(fen_after)
        return MoveResponse(
            legal=True,
            fen=fen_after,
            lastMoveSan=last_move_san,
            analysis=None,
            book=True,
            openingName=opening["name"] if opening else None,
            openingEco=opening["eco"] if opening else None,
        )

    # Caller opted out of engine analysis (e.g. skipping the opponent's move):
    # legality is already validated and the move is not in book — return without
    # touching the engine.
    if not req.analyze:
        return MoveResponse(
            legal=True,
            fen=fen_after,
            lastMoveSan=last_move_san,
            analysis=None,
        )

    review.note_interactive_start()
    try:
        # multipv=2 surfaces a 2nd-best line for both positions WITHOUT adding an
        # engine call (still exactly two). before_lines[0] is what the mover should
        # have played (retrospective); after_lines[0] is the current best (unchanged).
        before_lines = await engine.analyze_interactive_multi(fen_before, multipv=2)
        after_lines = await engine.analyze_interactive_multi(fen_after, multipv=2)
    except EngineUnavailable:
        return _engine_unavailable_response()
    finally:
        review.note_interactive_end()

    before, after = before_lines[0], after_lines[0]

    quality = classify(
        pov_score_to_white_cp(before.score),
        pov_score_to_white_cp(after.score),
        mover_is_white,
    )

    return MoveResponse(
        legal=True,
        fen=fen_after,
        lastMoveSan=last_move_san,
        analysis=_build_analysis(
            after,
            quality=quality,
            second_line=after_lines[1] if len(after_lines) > 1 else None,
            retro_best=before_lines[0],
            retro_second=before_lines[1] if len(before_lines) > 1 else None,
        ),
    )


# ---------------------------------------------------------------------------
# Engine control routes
# ---------------------------------------------------------------------------
@app.get("/api/engine/status", response_model=EngineStatusResponse)
async def engine_status(engine: StockfishEngine = Depends(get_engine)):
    """Return the current status of the Stockfish engine."""
    return EngineStatusResponse(running=engine.is_running)


@app.post("/api/engine/restart", response_model=EngineRestartResponse)
async def restart_engine(engine: StockfishEngine = Depends(get_engine)):
    """Force-restart the Stockfish engine.

    Terminates the current engine subprocess (if any) and schedules a fresh
    start for the next analysis request. Does not require the engine to be
    healthy; safe to call when wedged. Always returns status 200 with restarted=True.
    """
    await engine.restart()
    return EngineRestartResponse(restarted=True, running=engine.is_running)


# ---------------------------------------------------------------------------
# Opening trainer (additive; degrade gracefully when data is absent)
# ---------------------------------------------------------------------------
@app.post("/api/opening")
async def opening_info(req: OpeningRequest):
    """Live opening detection (name + ECO) for the current line.

    Server derives all EPDs from baseFen + UCI moves (the client never sends
    EPDs). Always returns a well-formed body; ``current`` is null when no named
    opening matches or when data is absent.
    """
    return {"current": openings.identify(req.baseFen, req.moves)}


# ---------------------------------------------------------------------------
# Repertoire trainer (additive; degrade gracefully when data is absent)
# ---------------------------------------------------------------------------
@app.get("/api/repertoire")
async def get_repertoire():
    """Return the curated repertoire: per-color move trees + grouped catalog.

    Always returns a well-formed body; empty (roots present, no children, empty
    catalog) when data is absent. Never 500.
    """
    return {"tree": repertoire.tree()}


# ---------------------------------------------------------------------------
# Opening traps (additive; degrade gracefully when data is absent)
# ---------------------------------------------------------------------------
@app.get("/api/traps")
async def list_traps():
    """Browse list of all trap summaries (id, name, color, eco, parentOpening, commonness).

    Always returns a well-formed body; empty list when data is absent.
    """
    return {"traps": traps.summaries()}


# IMPORTANT: this POST /api/traps/check route is registered BEFORE the
# GET /api/traps/{trap_id} route so FastAPI never matches the literal path
# "/api/traps/check" as trap_id="check".
@app.post("/api/traps/check")
async def check_traps(req: TrapsCheckRequest):
    """Return trap summaries whose start EPD matches the current position.

    Server derives all EPDs from baseFen + UCI moves (the client never sends
    EPDs). Always returns a well-formed body; empty/degraded when data is absent.
    Never 500.
    """
    try:
        available = traps.available(req.baseFen, req.moves)
    except Exception:
        available = []
    return {"available": available}


@app.get("/api/traps/{trap_id}")
async def get_trap(trap_id: str):
    """Return the full trap object for trap_id, or 404 if unknown."""
    trap = traps.get(trap_id)
    if trap is None:
        return JSONResponse(status_code=404, content={"detail": f"Trap {trap_id!r} not found."})
    return trap


# ---------------------------------------------------------------------------
# Game library + review routes (additive; degrade gracefully when storage absent)
#
# IMPORTANT: literal paths (e.g. /api/games/import) are registered BEFORE
# parameterised paths (/api/games/{game_id}) so FastAPI never matches the
# literal segment as a game_id value.  This mirrors the traps precedent above.
# ---------------------------------------------------------------------------

def _game_summary(row: dict) -> GameSummary:
    """Build a GameSummary from a storage row dict."""
    return GameSummary(
        id=row["id"],
        white=row.get("white"),
        black=row.get("black"),
        result=row.get("result"),
        eco=row.get("eco"),
        opening=row.get("opening"),
        date=row.get("date"),
        my_color=row.get("my_color"),
        ply_count=row.get("ply_count"),
        analysis_status=row.get("analysis_status", "pending"),
        imported_at=row["imported_at"],
    )


# IMPORTANT: all literal /api/games/<word> paths are registered BEFORE
# /api/games/{game_id} so FastAPI never interprets the literal segment as an
# integer game_id.  Order: import → retag-color → analyze-all → {game_id}/*.

@app.post("/api/games/import", response_model=ImportResponse)
async def import_games(req: ImportRequest):
    """Import one or more PGN games from pasted text.

    Parses the PGN, inserts each game (deduped by content_hash), and applies
    the optional ``my_color`` override to every game in the batch.
    Returns imported/duplicate counts and summaries of all games in the batch.
    """
    now = datetime.now(timezone.utc).isoformat()
    try:
        parsed_games = pgn.parse_games(req.pgn)
    except Exception as exc:
        return JSONResponse(status_code=400, content={"detail": f"PGN parse error: {exc}"})

    imported = 0
    duplicates = 0
    summaries: list[GameSummary] = []

    for g in parsed_games:
        # Apply per-request my_color override (Refuter #8).
        my_color = req.my_color if req.my_color is not None else g.my_color
        fields = {
            "content_hash": g.content_hash,
            "pgn": g.pgn,
            "headers_json": None,
            "white": g.white,
            "black": g.black,
            "result": g.result,
            "eco": g.eco,
            "opening": g.opening,
            "date": g.date,
            "my_color": my_color,
            "source": "import",
            "ply_count": g.ply_count,
            "imported_at": now,
        }
        try:
            # Check whether the game already exists before inserting.
            from app.storage import _get_conn  # noqa: PLC0415
            conn = _get_conn()
            existing = conn.execute(
                "SELECT id FROM games WHERE content_hash = ?", (g.content_hash,)
            ).fetchone()
            game_id = storage.insert_game(fields)
            if existing is None:
                imported += 1
            else:
                duplicates += 1
            # Write per-ply rows if not already present (backfills dedup re-imports).
            if not storage.get_plies(game_id):
                storage.write_plies(game_id, [
                    {"ply": p.ply, "san": p.san, "uci": p.uci,
                     "fen_before": p.fen_before, "clock_centis": p.clock_centis}
                    for p in g.plies
                ])
            row = storage.get_game(game_id)
            if row:
                summaries.append(_game_summary(row))
        except Exception as exc:
            logger.warning("import: failed to insert game: %s", exc)

    return ImportResponse(imported=imported, duplicates=duplicates, games=summaries)


@app.get("/api/games", response_model=list[GameSummary])
async def list_games():
    """Return all saved games, most recently imported first."""
    try:
        rows = storage.list_games()
    except Exception:
        return []
    return [_game_summary(r) for r in rows]


# IMPORTANT: these two POST literal routes are registered BEFORE
# /api/games/{game_id} so they are never shadowed by the parameterised route.

@app.post("/api/games/retag-color", response_model=RetagResponse)
async def retag_color(req: RetagRequest):
    """Bulk-tag my_color on games whose White/Black name matches any alias.

    Accepts a comma-separated list of usernames in ``username``.  Matching is
    case-insensitive and trimmed (same logic as import-time inference).  Each
    matching game has its ``analysis_status`` reset to 'pending' so that the
    next bulk-analyze pass recomputes leaks under the correct color.

    Returns the number of updated games and fresh coverage counts.
    """
    aliases = [a.strip() for a in req.username.split(",") if a.strip()]
    try:
        updated = storage.retag_colors_by_aliases(aliases)
        cov = storage.coverage()
    except Exception as exc:
        return JSONResponse(status_code=500, content={"detail": str(exc)})
    return RetagResponse(
        updated=updated,
        coverage=CoverageDict(**cov),
    )


@app.post("/api/games/analyze-all", response_model=AnalyzeAllResponse)
async def analyze_all_games(engine: StockfishEngine = Depends(get_engine)):
    """Start a single background task that analyzes all 'pending' games sequentially.

    If a bulk-analyze task is already running, returns immediately (no-op).
    Returns the count of pending games at the time of the call.
    """
    try:
        pending_count = storage.coverage().get("pending", 0)
    except Exception:
        pending_count = 0

    review.start_analyze_all(engine, depth=review.BACKGROUND_DEPTH)
    return AnalyzeAllResponse(pending=pending_count)


@app.get("/api/games/{game_id}", response_model=GameDetail)
async def get_game(game_id: int):
    """Return a single saved game with per-ply data, or 404 if not found."""
    try:
        row = storage.get_game(game_id)
    except Exception:
        row = None
    if row is None:
        return JSONResponse(status_code=404, content={"detail": f"Game {game_id} not found."})

    try:
        ply_rows = storage.get_plies(game_id)
    except Exception:
        ply_rows = []

    plies = [
        PlyDetail(
            ply=p["ply"],
            san=p.get("san"),
            uci=p.get("uci"),
            fen_before=p.get("fen_before"),
            eval_cp_white=p.get("eval_cp_white"),
            mate_white=p.get("mate_white"),
            win_prob=p.get("win_prob"),
            is_user_move=bool(p.get("is_user_move", 0)),
            clock_centis=p.get("clock_centis"),
        )
        for p in ply_rows
    ]

    return GameDetail(
        id=row["id"],
        white=row.get("white"),
        black=row.get("black"),
        result=row.get("result"),
        eco=row.get("eco"),
        opening=row.get("opening"),
        date=row.get("date"),
        my_color=row.get("my_color"),
        ply_count=row.get("ply_count"),
        analysis_status=row.get("analysis_status", "pending"),
        imported_at=row["imported_at"],
        pgn=row.get("pgn", ""),
        plies=plies,
    )


@app.patch("/api/games/{game_id}", response_model=GameSummary)
async def patch_game(game_id: int, req: SetColorRequest):
    """Set or clear ``my_color`` on a single game.

    Resetting the color invalidates previously computed leaks, so
    ``analysis_status`` is automatically reset to 'pending'.  Returns the
    updated game summary, or 404 if the game does not exist.
    """
    try:
        changed = storage.set_my_color(game_id, req.my_color)
    except ValueError as exc:
        return JSONResponse(status_code=422, content={"detail": str(exc)})
    except Exception as exc:
        return JSONResponse(status_code=500, content={"detail": str(exc)})
    if not changed:
        return JSONResponse(status_code=404, content={"detail": f"Game {game_id} not found."})
    row = storage.get_game(game_id)
    if row is None:
        return JSONResponse(status_code=404, content={"detail": f"Game {game_id} not found."})
    return _game_summary(row)


@app.post("/api/games/{game_id}/analyze", response_model=AnalyzeStatusResponse)
async def analyze_game_route(
    game_id: int, engine: StockfishEngine = Depends(get_engine)
):
    """Start background analysis for a saved game.

    Returns an accepted response. The job status can be polled via
    GET /api/games/{game_id}/status. Engine failures are handled inside the
    background task (status moves to 'failed') rather than at route level.
    """
    try:
        row = storage.get_game(game_id)
    except Exception:
        row = None
    if row is None:
        return JSONResponse(status_code=404, content={"detail": f"Game {game_id} not found."})

    review.start_analysis(game_id, engine, depth=review.BACKGROUND_DEPTH)

    # Re-fetch status after starting (it should be 'analyzing' now).
    try:
        row = storage.get_game(game_id)
        status = row.get("analysis_status", "analyzing") if row else "analyzing"
    except Exception:
        status = "analyzing"

    return AnalyzeStatusResponse(game_id=game_id, analysis_status=status)


@app.get("/api/games/{game_id}/status", response_model=AnalyzeStatusResponse)
async def get_game_status(game_id: int):
    """Return the analysis status for a game."""
    try:
        row = storage.get_game(game_id)
    except Exception:
        row = None
    if row is None:
        return JSONResponse(status_code=404, content={"detail": f"Game {game_id} not found."})
    return AnalyzeStatusResponse(
        game_id=game_id,
        analysis_status=row.get("analysis_status", "pending"),
    )


@app.get("/api/games/{game_id}/review", response_model=ReviewResponse)
async def get_game_review(game_id: int):
    """Return narrated leaks + per-ply evals for the foresight UI."""
    try:
        row = storage.get_game(game_id)
    except Exception:
        row = None
    if row is None:
        return JSONResponse(status_code=404, content={"detail": f"Game {game_id} not found."})

    status = row.get("analysis_status", "pending")

    try:
        leak_rows = storage.get_leaks(game_id)
    except Exception:
        leak_rows = []

    try:
        ply_rows = storage.get_plies(game_id)
    except Exception:
        ply_rows = []

    narrator = coaching.get_narrator()
    narrated: list[NarratedLeak] = []
    for lk in leak_rows:
        try:
            narration = narrator.narrate_leak(lk)
        except Exception:
            narration = {"threat": None, "hanging": None, "plan": None, "summary": ""}
        narrated.append(NarratedLeak(
            id=lk.get("id") if isinstance(lk, dict) else getattr(lk, "id", None),
            ply=lk["ply"] if isinstance(lk, dict) else lk.ply,
            lead_in_ply=lk.get("lead_in_ply") if isinstance(lk, dict) else lk.lead_in_ply,
            severity=lk["severity"] if isinstance(lk, dict) else lk.severity,
            category=lk["category"] if isinstance(lk, dict) else lk.category,
            phase=lk["phase"] if isinstance(lk, dict) else lk.phase,
            win_prob_before=lk["win_prob_before"] if isinstance(lk, dict) else lk.win_prob_before,
            win_prob_after=lk["win_prob_after"] if isinstance(lk, dict) else lk.win_prob_after,
            win_prob_drop=lk["win_prob_drop"] if isinstance(lk, dict) else lk.win_prob_drop,
            best_san=lk.get("best_san") if isinstance(lk, dict) else lk.best_san,
            best_uci=lk.get("best_uci") if isinstance(lk, dict) else lk.best_uci,
            threat_uci=lk.get("threat_uci") if isinstance(lk, dict) else lk.threat_uci,
            threat_motif=lk.get("threat_motif") if isinstance(lk, dict) else lk.threat_motif,
            hung_square=lk.get("hung_square") if isinstance(lk, dict) else lk.hung_square,
            narration=narration,
        ))

    plies = [
        PlyDetail(
            ply=p["ply"],
            san=p.get("san"),
            uci=p.get("uci"),
            fen_before=p.get("fen_before"),
            eval_cp_white=p.get("eval_cp_white"),
            mate_white=p.get("mate_white"),
            win_prob=p.get("win_prob"),
            is_user_move=bool(p.get("is_user_move", 0)),
            clock_centis=p.get("clock_centis"),
        )
        for p in ply_rows
    ]

    summary = None
    if status == "done":
        summary = GameAccuracySummary(**accuracy.summarize(ply_rows, row.get("my_color")))

    return ReviewResponse(game_id=game_id, analysis_status=status, leaks=narrated, plies=plies, summary=summary)


@app.delete("/api/games/{game_id}")
async def delete_game(game_id: int):
    """Cancel any running analysis and delete the game + its plies/leaks."""
    review.cancel_analysis(game_id)
    try:
        deleted = storage.delete_game(game_id)
    except Exception as exc:
        return JSONResponse(status_code=500, content={"detail": str(exc)})
    if not deleted:
        return JSONResponse(status_code=404, content={"detail": f"Game {game_id} not found."})
    return {"deleted": game_id}


# ---------------------------------------------------------------------------
# Profile (additive)
# ---------------------------------------------------------------------------

@app.get("/api/profile", response_model=ProfileResponse)
async def get_profile():
    """Return the cross-game tendency profile for the user."""
    try:
        data = profile.build_profile()
    except RuntimeError:
        # Storage not initialised (edge case in tests or first boot before init).
        return ProfileResponse(
            games_analyzed=0,
            games_total=0,
            games_tagged=0,
            top_leaks=[],
            by_phase={"opening": 0, "middlegame": 0, "endgame": 0},
            by_opening=[],
            by_color={"white": 0, "black": 0},
            hope_chess_rate=0.0,
            trend=[],
        )
    # Merge coverage counts into the profile payload.
    try:
        cov = storage.coverage()
        data["games_total"] = cov.get("total", 0)
        data["games_tagged"] = cov.get("tagged", 0)
    except Exception:
        data.setdefault("games_total", 0)
        data.setdefault("games_tagged", 0)
    return ProfileResponse(**data)


# ---------------------------------------------------------------------------
# Insights (additive; namespaced for /api/insights/{openings,mistakes,endgames})
# ---------------------------------------------------------------------------

@app.get("/api/insights/openings", response_model=OpeningsInsightsResponse)
async def get_insights_openings():
    """Return the Openings insights read-model (win%, repertoire adherence, theory)."""
    try:
        data = insights.build_openings_insights()
    except RuntimeError:
        # Storage not initialised (edge case in tests or first boot before init).
        empty_metric = {"value": None, "n": 0, "sufficient": False}
        data = {
            "coverage": {
                "total": 0, "tagged": 0, "analyzed": 0, "pending": 0,
                "qualified": 0, "on_repertoire": 0, "off_repertoire": 0,
            },
            "win_rates": {"families": [], "lines": []},
            "adherence": {
                "n": 0, "avg_followed_prep_depth": empty_metric,
                "lines": [], "games": [],
            },
            "theory": {
                "n": 0, "avg_book_exit_ply": empty_metric,
                "avg_opening_accuracy": empty_metric,
                "games": [],
                "note": (
                    "'In book' means the line has a name in the openings database "
                    "— named theory is not the same as moves endorsed by masters."
                ),
            },
        }
    return OpeningsInsightsResponse(**data)


@app.get("/api/insights/mistakes", response_model=MistakesInsightsResponse)
async def get_insights_mistakes():
    """Return the Mistakes insights read-model (clusters, foreseeable, time-trouble, capitalization)."""
    try:
        data = insights.build_mistakes_insights()
    except RuntimeError:
        # Storage not initialised (edge case in tests or first boot before init).
        empty_metric = {"value": None, "n": 0, "sufficient": False}
        data = {
            "coverage": {
                "total": 0, "tagged": 0, "analyzed": 0, "pending": 0, "qualified": 0,
            },
            "clusters": {
                "n_leaks": 0, "items": [],
                "suppressed": {"cells": 0, "leaks": 0, "gate": insights.CLUSTER_GATE},
            },
            "foreseeable": {
                "rate": empty_metric,
                "dominant_motif": None,
                "note": (
                    "Foreseeable uses a narrow definition — it counts only warning "
                    "signs visible at least two plies before the mistake. One-ply "
                    "warnings cannot be distinguished from the pipeline's "
                    "display-timing default, so the true rate is likely higher."
                ),
            },
            "time_trouble": {
                "clocked_games": 0, "unclocked_games": 0,
                "baseline_rate": empty_metric,
                # Mirror the real builder: all 4 buckets are always present,
                # just zeroed out (labels sourced from insights._CLOCK_BUCKETS).
                "buckets": [
                    {"bucket": label, "moves": 0, "leaks": 0, "rate": None,
                     "sufficient": False}
                    for label, _, _ in insights._CLOCK_BUCKETS
                ],
                "note": "0 of 0 analyzed games have no clock data and are excluded.",
            },
            "capitalization": {
                "winning_games": 0, "converted": 0,
                "rate": empty_metric,
                "note": (
                    "A game counts as 'winning' when your win probability stayed "
                    "at or above 80% for at least 4 consecutive plies — single-ply "
                    "eval spikes do not count."
                ),
            },
        }
    return MistakesInsightsResponse(**data)


@app.get("/api/insights/endgames", response_model=EndgameInsightsResponse)
async def get_insights_endgames():
    """Return the Endgames insights read-model (per-signature accuracy + conversion)."""
    try:
        data = insights.build_endgame_insights()
    except RuntimeError:
        # Storage not initialised (edge case in tests or first boot before init).
        data = {
            "coverage": {
                "total": 0, "tagged": 0, "analyzed": 0, "pending": 0,
                "qualified": 0, "reached_endgame": 0,
            },
            "types": [],
            "weakest": None,
            "note": (
                "0 of 0 qualified games never reach a stable endgame phase and "
                "are excluded from every count below. 0 game(s) that do reach "
                "one have fewer than 4 scored moves in the endgame suffix — too "
                "short to be meaningful — and are excluded from the accuracy "
                "average only; they still count toward games and conversion."
            ),
        }
    return EndgameInsightsResponse(**data)


# ---------------------------------------------------------------------------
# Blunder trainer (spaced repetition over your own mistakes)
# ---------------------------------------------------------------------------

# Verdict window for /api/trainer/check (spec: eval-window solving).
SOLVED_ALT_MAX_CP_LOSS = 50  # attempted move within 50cp of best → solved_alt
WINNING_MOVER_CP = 300       # both evals >= +300 mover-POV (still winning) → solved_alt


@app.get("/api/trainer/session", response_model=TrainerPreviewResponse)
async def get_trainer_session():
    """Idempotent peek at bucket/due status (no engine, no cursor movement).

    Safe to call on every Train-section render — serving is a separate POST.
    """
    return TrainerPreviewResponse(buckets=trainer.preview_due_buckets())


@app.post("/api/trainer/session/start", response_model=TrainerSessionResponse)
async def start_trainer_session():
    """Serve today's session and advance rotation cursors (no engine).

    MUTATING: called exactly once per Start click — every call burns rotation.
    """
    return TrainerSessionResponse(**trainer.assemble_session())


@app.post("/api/trainer/check", response_model=TrainerCheckResponse)
async def check_trainer_move(
    req: TrainerCheckRequest, engine: StockfishEngine = Depends(get_engine)
):
    """Check an attempted solution against the engine (eval-window verdict).

    The puzzle position is rebuilt server-side from game_plies — a client FEN
    is never trusted. Verdict: engine best at check depth → 'solved'; within
    the eval window → 'solved_alt'; else 'failed' (with narration). The
    attempt is recorded under the natural key. ``offline=true`` skips the
    engine entirely (exact match vs the stored leak best_uci, check_depth=0).
    """
    # Resolve the natural key against the LIVE pool — the qualification gate,
    # bucket fallback, and server-side fen_before all come from trainer sourcing.
    key = trainer.natural_key(req.game_id, req.ply, req.bucket)
    pool = trainer.get_live_pool()
    puzzle = next((p for p in pool.get(req.bucket, []) if p["key"] == key), None)
    if puzzle is None:
        return JSONResponse(
            status_code=404, content={"detail": f"No live puzzle for key '{key}'."}
        )

    board = chess.Board(puzzle["fen_before"])

    # Parse + legality-check the attempted move (mirror /api/move's shape).
    try:
        move = chess.Move.from_uci(req.attempted_uci)
    except (ValueError, chess.InvalidMoveError):
        return TrainerCheckResponse(legal=False)
    if move not in board.legal_moves:
        return TrainerCheckResponse(legal=False)

    mover_is_white = board.turn == chess.WHITE
    attempted_san = board.san(move)  # render SAN BEFORE pushing
    fen_before = board.fen()
    board.push(move)
    fen_after = board.fen()

    # The live leaks row for this ply (one leak per ply) — narration source.
    leak_row = next(
        (lk for lk in storage.get_leaks(req.game_id) if lk["ply"] == req.ply), None
    )

    # Offline fallback: exact match against the stored (background-depth)
    # best_uci, recorded with the check_depth=0 sentinel. No engine touched.
    if req.offline:
        verdict = "solved" if req.attempted_uci == puzzle["best_uci"] else "failed"
        narration = None
        if verdict == "failed" and leak_row is not None:
            narration = coaching.get_narrator().narrate_leak(leak_row)
        storage.record_trainer_attempt(
            req.game_id, req.ply, req.bucket, req.attempted_uci,
            verdict, None, 0,
        )
        return TrainerCheckResponse(
            legal=True,
            verdict=verdict,
            attempted_san=attempted_san,
            best_san=puzzle["best_san"],
            best_uci=puzzle["best_uci"],
            cp_loss=None,
            check_depth=0,
            offline=True,
            narration=narration,
        )

    # Two-call before/after pattern (exactly like /api/move): the attempted
    # move needs its REAL eval — a single multipv call cannot score a move
    # outside the top-K lines.
    review.note_interactive_start()
    try:
        before_lines = await engine.analyze_interactive_multi(fen_before, multipv=1)
        after_lines = await engine.analyze_interactive_multi(fen_after, multipv=1)
    except EngineUnavailable:
        return _engine_unavailable_response()
    finally:
        review.note_interactive_end()

    before, after = before_lines[0], after_lines[0]

    # All evals are normalized ONLY via pov_score_to_white_cp; the mover-sign
    # rule lives in analysis.cp_loss alone (never inline the flip).
    before_white_cp = pov_score_to_white_cp(before.score)
    after_white_cp = pov_score_to_white_cp(after.score)
    loss = cp_loss(before_white_cp, after_white_cp, mover_is_white)

    engine_best_uci = before.pv[0].uci() if before.pv else None
    engine_best_san = before.pv_san[0] if before.pv_san else None

    if req.attempted_uci == engine_best_uci:
        verdict = "solved"
    else:
        # Mover-POV framing of the SAME White-POV numbers (sign only): the
        # mover's advantage is the White-POV eval negated for a Black mover.
        before_mover_cp = before_white_cp if mover_is_white else -before_white_cp
        after_mover_cp = after_white_cp if mover_is_white else -after_white_cp
        still_winning = (
            before_mover_cp >= WINNING_MOVER_CP and after_mover_cp >= WINNING_MOVER_CP
        )
        verdict = "solved_alt" if loss <= SOLVED_ALT_MAX_CP_LOSS or still_winning else "failed"

    narration = None
    if verdict == "failed" and leak_row is not None:
        narration = coaching.get_narrator().narrate_leak(leak_row)

    storage.record_trainer_attempt(
        req.game_id, req.ply, req.bucket, req.attempted_uci,
        verdict, loss, DEFAULT_DEPTH,
    )
    return TrainerCheckResponse(
        legal=True,
        verdict=verdict,
        attempted_san=attempted_san,
        # Check-time engine is authoritative; stored leak best is only a hint.
        best_san=engine_best_san or puzzle["best_san"],
        best_uci=engine_best_uci or puzzle["best_uci"],
        cp_loss=loss,
        check_depth=DEFAULT_DEPTH,
        narration=narration,
    )


@app.get("/api/trainer/stats", response_model=TrainerStatsResponse)
async def get_trainer_stats():
    """Trainer boxes + attempt aggregates for the Train section (no engine)."""
    stats = storage.get_attempt_stats()
    return TrainerStatsResponse(
        boxes=storage.get_trainer_boxes(),
        per_bucket=stats["per_bucket"],
        all_attempts=stats["all_attempts"],
    )


@app.post("/api/trainer/bucket-complete", response_model=TrainerBucketCompleteResponse)
async def complete_trainer_bucket(req: TrainerBucketCompleteRequest):
    """Close out a finished bucket review: apply the Leitner box transition."""
    # motif is deliberately unvalidated (single-user trust model): an unknown
    # motif just creates a box row that box hygiene resets on next assembly.
    new_box = trainer.complete_bucket_review(req.motif, list(req.outcomes))
    return TrainerBucketCompleteResponse(motif=req.motif, box=new_box)


# ---------------------------------------------------------------------------
# Static frontend (mounted last so /api/* takes precedence)
# ---------------------------------------------------------------------------
@app.get("/")
async def index():
    """Serve the board UI (404 until the frontend ticket T6 lands)."""
    if INDEX_HTML.is_file():
        return FileResponse(INDEX_HTML)
    return JSONResponse(
        status_code=404,
        content={"detail": "Frontend not built yet (static/index.html missing)."},
    )


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
