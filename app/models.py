"""Pydantic v2 request/response schemas for the Stockfish analysis board.

Pure data definitions only — no logic, no engine/`chess` imports. The single
shared :class:`Analysis` object is returned identically by all three endpoints
(`/api/move`, `/api/analyze`, `/api/load`); see
``docs/design/specs/stockfish-analysis-board.md`` (API section).
"""

from typing import Literal

from pydantic import BaseModel, Field

# Move-quality buckets derived from centipawn loss (see spec classification).
Quality = Literal["best", "good", "inaccuracy", "mistake", "blunder"]


class Analysis(BaseModel):
    """The single shared analysis shape returned by every endpoint.

    ``evalCp`` and ``mate`` are the raw display fields (exactly one is set; the
    other is ``None``). ``evalWhitePov`` is the normalized White-POV centipawn
    value used by move-quality classification (mate scores are mapped to cp).
    ``bestMoveSan`` / ``pvSan`` describe the *resulting* position. ``quality``
    is ``None`` unless a prior move exists (e.g. on FEN load / initial position).
    """

    evalCp: int | None = Field(
        description="Raw eval in centipawns from White's POV; None when the "
        "position is a forced mate."
    )
    mate: int | None = Field(
        description="Moves-to-mate (signed, White's POV); None when the eval is "
        "a centipawn score."
    )
    evalWhitePov: int = Field(
        description="Normalized White-POV centipawns used for classification; "
        "mate scores are mate-mapped to cp."
    )
    bestMoveSan: str | None = Field(
        description="Engine's best move for the resulting position, in SAN; None "
        "if unavailable (e.g. terminal position)."
    )
    bestMoveUci: str | None = Field(
        default=None,
        description="Engine's best move in UCI; None if unavailable. Lets the practice "
        "client auto-play the engine opponent after prep ends.",
    )
    pvSan: list[str] = Field(
        default_factory=list,
        description="Principal variation (engine's top line) for the resulting "
        "position, in SAN.",
    )
    quality: Quality | None = Field(
        default=None,
        description="Move-quality label for the move just played; None when there "
        "is no prior move.",
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "evalCp": 80,
                    "mate": None,
                    "evalWhitePov": 80,
                    "bestMoveSan": "Nf3",
                    "pvSan": ["Nf3", "Nc6", "Bb5"],
                    "quality": "good",
                }
            ]
        }
    }


# --- Request models ---------------------------------------------------------


class MoveRequest(BaseModel):
    """Body for ``POST /api/move`` — the move to apply against ``fen``."""

    fen: str = Field(description="Position BEFORE the move, in FEN.")
    move: str = Field(
        description="Move in UCI; may include a promotion suffix, e.g. 'e7e8q'."
    )
    useBook: bool = Field(
        default=False,
        description="When true, opt into the opening-book fast-path: if the move "
        "stays in book the engine is skipped and the response has book=True with "
        "analysis=None. Only the play-mode client sets this; default False keeps "
        "every other caller (e.g. trap practice) on full analysis.",
    )
    analyze: bool = Field(
        default=True,
        description="When false, skip engine analysis (e.g. to skip analysis for "
        "the opponent's move). The move is still validated for legality. "
        "Default True preserves current behavior.",
    )


class AnalyzeRequest(BaseModel):
    """Body for ``POST /api/analyze`` — a position to analyze (no prior move)."""

    fen: str = Field(description="Position to analyze, in FEN.")


class LoadRequest(BaseModel):
    """Body for ``POST /api/load`` — a candidate FEN to validate and load."""

    fen: str = Field(description="Candidate position to validate and load, in FEN.")


class OpeningRequest(BaseModel):
    """Body for ``POST /api/opening`` — the current line (server derives EPDs)."""

    baseFen: str = Field(description="Starting FEN of the line (usually the standard start).")
    moves: list[str] = Field(
        default_factory=list, description="UCI moves applied from baseFen, in order."
    )


class TrapsCheckRequest(BaseModel):
    """Body for ``POST /api/traps/check`` — the current line (server derives EPD)."""

    baseFen: str = Field(description="Starting FEN of the line (usually the standard start).")
    moves: list[str] = Field(
        default_factory=list, description="UCI moves applied from baseFen, in order."
    )


# --- Response models --------------------------------------------------------


class MoveResponse(BaseModel):
    """Response for ``POST /api/move``.

    On an illegal move, ``legal`` is False and every other field is ``None``.
    On a legal move, ``fen`` is the position after the move and ``analysis``
    describes that resulting position.
    """

    legal: bool = Field(description="Whether the submitted move was legal.")
    fen: str | None = Field(
        default=None, description="Position AFTER the move, in FEN; None if illegal."
    )
    lastMoveSan: str | None = Field(
        default=None, description="The applied move in SAN; None if illegal."
    )
    analysis: Analysis | None = Field(
        default=None,
        description="Analysis of the resulting position; None if illegal, or None "
        "when book=True (no engine ran).",
    )
    book: bool = Field(
        default=False,
        description="True when the book fast-path handled this move (engine skipped, "
        "analysis is None). Always False unless the request set useBook.",
    )
    openingName: str | None = Field(
        default=None,
        description="Opening name of the resulting position; set only on book "
        "responses when the position is a named line, else None.",
    )
    openingEco: str | None = Field(
        default=None,
        description="ECO code of the resulting position; set only on book responses "
        "alongside openingName, else None.",
    )


class AnalyzeResponse(BaseModel):
    """Response for ``POST /api/analyze`` — analysis of the given position."""

    analysis: Analysis = Field(
        description="Analysis of the position; quality is None (no prior move)."
    )


class LoadResponse(BaseModel):
    """Response for ``POST /api/load``.

    On a valid FEN, ``valid`` is True with ``fen`` and ``analysis`` set and
    ``error`` None. On an invalid FEN, ``valid`` is False with ``error`` set
    and ``fen`` / ``analysis`` None.
    """

    valid: bool = Field(description="Whether the submitted FEN was valid.")
    fen: str | None = Field(
        default=None, description="Loaded position in FEN; None if invalid."
    )
    analysis: Analysis | None = Field(
        default=None,
        description="Analysis of the loaded position; None if invalid.",
    )
    error: str | None = Field(
        default=None, description="Validation error message; None if valid."
    )


# ---------------------------------------------------------------------------
# Games / review / profile models (additive — T7)
# ---------------------------------------------------------------------------


class ImportRequest(BaseModel):
    """Body for ``POST /api/games/import`` — paste PGN text, optional color override."""

    pgn: str = Field(max_length=5_000_000, description="Raw PGN text containing one or more games.")
    my_color: str | None = Field(
        default=None,
        description=(
            "Override the inferred player color for every game in this import batch. "
            "Accepted values: 'white', 'black', or null to use the CHESS_USERNAME inference."
        ),
    )


class GameSummary(BaseModel):
    """One row from the games table — lightweight, for list views."""

    id: int = Field(description="Database row ID.")
    white: str | None = Field(default=None, description="White player name.")
    black: str | None = Field(default=None, description="Black player name.")
    result: str | None = Field(default=None, description="PGN result string.")
    eco: str | None = Field(default=None, description="ECO code.")
    opening: str | None = Field(default=None, description="Opening name.")
    date: str | None = Field(default=None, description="PGN Date header.")
    my_color: str | None = Field(default=None, description="Player color ('white'/'black'/None).")
    ply_count: int | None = Field(default=None, description="Total half-moves in the game.")
    analysis_status: str = Field(
        description="Analysis status: 'pending'|'analyzing'|'done'|'failed'."
    )
    imported_at: str = Field(description="ISO timestamp of import.")


class PlyDetail(BaseModel):
    """One half-move with eval data — for the replay UI."""

    ply: int = Field(description="1-based ply number.")
    san: str | None = Field(default=None, description="Move in SAN.")
    uci: str | None = Field(default=None, description="Move in UCI.")
    fen_before: str | None = Field(default=None, description="FEN of the board before this move.")
    eval_cp_white: int | None = Field(default=None, description="Eval in centipawns, White POV.")
    mate_white: int | None = Field(default=None, description="Mate-in-N, White POV.")
    win_prob: float | None = Field(default=None, description="Win probability for the side to move.")
    is_user_move: bool = Field(default=False, description="True when this ply was made by the user.")
    clock_centis: int | None = Field(default=None, description="Remaining clock in centiseconds.")


class GameDetail(BaseModel):
    """Full game record including per-ply data for replay."""

    id: int
    white: str | None = None
    black: str | None = None
    result: str | None = None
    eco: str | None = None
    opening: str | None = None
    date: str | None = None
    my_color: str | None = None
    ply_count: int | None = None
    analysis_status: str
    imported_at: str
    pgn: str = Field(description="Raw PGN text.")
    plies: list[PlyDetail] = Field(
        default_factory=list,
        description="Per-ply data for replay; empty until analysis completes.",
    )


class ImportResponse(BaseModel):
    """Response for ``POST /api/games/import``."""

    imported: int = Field(description="Number of new games persisted.")
    duplicates: int = Field(description="Number of games skipped as duplicates.")
    games: list[GameSummary] = Field(
        description="Summaries of all games in the import batch (new + duplicates)."
    )


class NarratedLeak(BaseModel):
    """One leak with coach narration, for the foresight UI."""

    id: int | None = Field(default=None)
    ply: int
    lead_in_ply: int | None = Field(default=None)
    severity: str
    category: str
    phase: str
    win_prob_before: float
    win_prob_after: float
    win_prob_drop: float
    best_san: str | None = Field(default=None)
    best_uci: str | None = Field(default=None)
    threat_uci: str | None = Field(default=None)
    threat_motif: str | None = Field(default=None)
    hung_square: str | None = Field(default=None)
    narration: dict = Field(
        description="DecodeChess-style bucketed foresight text from the narrator."
    )


class GameAccuracySummary(BaseModel):
    """Estimated per-side Accuracy % + Elo for a reviewed game."""

    white_accuracy: float | None = None
    black_accuracy: float | None = None
    white_elo: int | None = None
    black_elo: int | None = None
    white_moves: int = 0
    black_moves: int = 0
    my_color: str | None = None


class ReviewResponse(BaseModel):
    """Response for ``GET /api/games/{game_id}/review``."""

    game_id: int
    analysis_status: str
    leaks: list[NarratedLeak] = Field(default_factory=list)
    plies: list[PlyDetail] = Field(
        default_factory=list,
        description="Per-ply evals for the foresight eval graph.",
    )
    summary: GameAccuracySummary | None = None


class AnalyzeStatusResponse(BaseModel):
    """Response for ``GET /api/games/{game_id}/status``."""

    game_id: int
    analysis_status: str


class ProfileResponse(BaseModel):
    """Response for ``GET /api/profile``."""

    games_analyzed: int
    games_total: int = Field(
        default=0,
        description="Total number of games in the library.",
    )
    games_tagged: int = Field(
        default=0,
        description="Number of games with my_color set (tagged).",
    )
    top_leaks: list[dict] = Field(
        default_factory=list,
        description="Top leak categories with count and coach cluster name.",
    )
    by_phase: dict = Field(default_factory=dict)
    by_opening: list[dict] = Field(default_factory=list)
    by_color: dict = Field(default_factory=dict)
    hope_chess_rate: float
    trend: list[dict] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Insights — Openings slice (additive; app/insights.py::build_openings_insights)
# ---------------------------------------------------------------------------


class InsightsGatedMetric(BaseModel):
    """An aggregate wrapped with its sample size (the honesty gate, T0.3).

    ``sufficient`` is False when ``n`` is below the min-sample threshold (5);
    the UI mutes those instead of hiding or overselling them.
    """

    value: float | None = Field(description="The aggregate value, or None with n=0.")
    n: int = Field(description="Sample size backing this aggregate.")
    sufficient: bool = Field(description="True when n meets the min-sample threshold.")


class InsightsCoverage(BaseModel):
    """How many games feed the Openings insights, and how they were routed."""

    total: int = Field(description="Total number of game rows.")
    tagged: int = Field(description="Games with my_color set.")
    analyzed: int = Field(description="Games with analysis_status='done'.")
    pending: int = Field(description="Games with analysis_status='pending'.")
    qualified: int = Field(
        description="Games with my_color set AND analysis_status='done' — the "
        "population every Openings section is computed from."
    )
    on_repertoire: int = Field(
        description="Qualified games that matched the user's prepared repertoire "
        "for at least one ply (feed the adherence section)."
    )
    off_repertoire: int = Field(
        description="Qualified games that never matched the repertoire (feed the "
        "theory fallback section)."
    )


class InsightsFamilyWinRecord(BaseModel):
    """Win-rate row grouped by opening family (name before the first ':')."""

    opening: str = Field(description="Family display name (or ECO/'Unknown' fallback).")
    color: str = Field(description="User's color for these games ('white'/'black').")
    wins: int
    draws: int
    losses: int
    n: int = Field(description="wins + draws + losses.")
    score: float = Field(description="(wins + 0.5*draws) / n, from the user's perspective.")
    sufficient: bool = Field(description="True when n >= the min-sample threshold.")


class InsightsLineWinRecord(InsightsFamilyWinRecord):
    """Win-rate row grouped by full opening/line name; also carries its family."""

    family: str = Field(description="The opening family this line belongs to.")


class InsightsWinRates(BaseModel):
    """Win% by opening, grouped both by family (default view) and by full line."""

    families: list[InsightsFamilyWinRecord] = Field(default_factory=list)
    lines: list[InsightsLineWinRecord] = Field(default_factory=list)


class InsightsAdherenceLine(BaseModel):
    """Per-prepared-line aggregate adherence."""

    line_id: str
    name: str = Field(description="Human-readable line name from the repertoire catalog.")
    color: str | None = Field(
        default=None, description="'white'/'black'; None if the line_id is unknown."
    )
    n: int = Field(description="Number of games credited to this line.")
    avg_followed_prep_depth: float = Field(
        description="Average number of plies the user's moves matched this line's prep."
    )
    deviations: int = Field(description="Number of games where the user left prep first.")
    sufficient: bool = Field(description="True when n >= the min-sample threshold.")


class InsightsAdherenceGame(BaseModel):
    """One on-repertoire game's prep-following detail, for UI deep-links."""

    game_id: int
    followed_prep_depth: int = Field(description="Plies the user's moves matched prep.")
    deviation_ply: int | None = Field(
        default=None, description="1-based ply where the user left prep; None if none."
    )
    deviation_move: str | None = Field(
        default=None, description="SAN of the move the user played instead of prep."
    )
    prepared_san: str | None = Field(
        default=None, description="SAN of the prepared move the user deviated from."
    )
    line_ids: list[str] = Field(
        default_factory=list,
        description="Prepared line(s) still consistent with the deepest matched node.",
    )


class InsightsAdherence(BaseModel):
    """Repertoire-adherence section (on-repertoire games only)."""

    n: int = Field(description="Number of on-repertoire games.")
    avg_followed_prep_depth: InsightsGatedMetric
    lines: list[InsightsAdherenceLine] = Field(default_factory=list)
    games: list[InsightsAdherenceGame] = Field(
        default_factory=list,
        description="Uncapped per-game list, kept for UI deep-links (openGameAtPly).",
    )


class InsightsTheoryGame(BaseModel):
    """One off-repertoire game's named-theory detail, for UI deep-links."""

    game_id: int
    book_exit_ply: int = Field(
        description="Last ply of the initial in-book run; 0 if never in book."
    )
    opening_accuracy: float | None = Field(
        default=None, description="Accuracy % restricted to opening-phase plies; "
        "None when it could not be computed."
    )


class InsightsTheory(BaseModel):
    """Named-theory fallback section for off-repertoire games."""

    n: int = Field(description="Number of off-repertoire games.")
    avg_book_exit_ply: InsightsGatedMetric
    avg_opening_accuracy: InsightsGatedMetric = Field(
        description="Gated on the count of games with a *computable* accuracy, "
        "which can be less than theory.n."
    )
    games: list[InsightsTheoryGame] = Field(
        default_factory=list,
        description="Uncapped per-game list, kept for UI deep-links (openGameAtPly).",
    )
    note: str = Field(description="Caveat: named theory is not the same as endorsed moves.")


class OpeningsInsightsResponse(BaseModel):
    """Response for ``GET /api/insights/openings``."""

    coverage: InsightsCoverage
    win_rates: InsightsWinRates
    adherence: InsightsAdherence
    theory: InsightsTheory


# ---------------------------------------------------------------------------
# Color-tagging + bulk-analyze models (additive)
# ---------------------------------------------------------------------------


class SetColorRequest(BaseModel):
    """Body for ``PATCH /api/games/{game_id}`` — set or clear my_color."""

    my_color: str | None = Field(
        default=None,
        description=(
            "Player color to tag this game with. "
            "Accepted values: 'white', 'black', or null to clear."
        ),
    )


class RetagRequest(BaseModel):
    """Body for ``POST /api/games/retag-color`` — bulk-tag by username aliases."""

    username: str = Field(
        description=(
            "Comma-separated list of username aliases to match against White/Black. "
            "Case-insensitive; trimmed. E.g. 'alice,Alice2'."
        )
    )


class CoverageDict(BaseModel):
    """Breakdown of how many games are tagged / analyzed."""

    total: int
    tagged: int
    analyzed: int
    pending: int


class RetagResponse(BaseModel):
    """Response for ``POST /api/games/retag-color``."""

    updated: int = Field(description="Number of games whose my_color was updated.")
    coverage: CoverageDict = Field(description="Fresh coverage counts after the retag.")


class AnalyzeAllResponse(BaseModel):
    """Response for ``POST /api/games/analyze-all``."""

    pending: int = Field(
        description="Number of games with analysis_status='pending' at the time the task was started."
    )


# ---------------------------------------------------------------------------
# Engine control models (additive)
# ---------------------------------------------------------------------------


class EngineStatusResponse(BaseModel):
    """Response for ``GET /api/engine/status``."""

    running: bool = Field(description="Whether the Stockfish subprocess is currently running.")


class EngineRestartResponse(BaseModel):
    """Response for ``POST /api/engine/restart``."""

    restarted: bool = Field(description="Whether the engine restart was attempted (always True).")
    running: bool = Field(description="Whether the Stockfish subprocess is running after the restart.")
