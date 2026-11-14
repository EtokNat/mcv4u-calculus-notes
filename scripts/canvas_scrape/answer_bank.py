"""Hand-crafted answer lookup for Canvas New Quiz prompts.

Rationale: SymPy pattern-matching is brittle. For a finite randomized question
pool, the cheapest reliable path is to solve each unique prompt once by hand
and store it here. The solver (solve_formative.solve_question) consults this
bank first; falls back to pattern code only on misses.

Each ENTRY = (predicate, answers)
  predicate(prompt) -> bool, applied to normalized prompt text
  answers: list[str], one per blank, formatted as the quiz expects

Order matters — first True predicate wins.
"""
import re


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip()


def _has(*needles: str):
    def pred(p: str) -> bool:
        np = _norm(p)
        return all(n in np for n in needles)
    return pred


# --- Entries ---------------------------------------------------------------
ENTRIES = [
    # Formative Check B, Sections 1.3 & 1.4 -------------------------------
    (
        # Q1: Evaluate three limits by direct substitution
        _has("Evaluate each limit", "lim(x\u2192-1) (9 - x\u00b2)"),
        ["8", "2", "2"],
    ),
    (
        # Q2: f(x) = mx + b given two limit values
        _has("f(x) = mx + b", "lim(x\u21921) f(x) = -2", "lim(x\u2192-1) f(x) = 4"),
        ["-3", "1"],
    ),
    (
        # Q3: Removable discontinuity, limit = 1
        _has("Determine lim(x\u21924) f(x)", "{1, if x \u2260 4; -1, if x = 4}"),
        ["1"],
    ),
    (
        # Q4: Sequence limits
        _has("appropriate limit of each sequence", "0.7, 0.72, 0.727"),
        ["8/11", "\u03c0"],
    ),
    (
        # Q5: Related rates, sphere area at r=10, sphere volume at r=5
        _has(
            "surface area of a spherical balloon",
            "radius reaches 10",
            "volume of a spherical balloon",
            "radius reaches 5",
        ),
        ["80\u03c0", "100\u03c0"],
    ),
    (
        # Q6: Baseball salary rate of change in 2005 (x = 23 years since 1982)
        _has("S(x) = 246 + 64x - 8.9x\u00b2 + 0.95x\u00b3", "1982", "2005"),
        ["1162.25"],
    ),
    (
        # Q7: Alternate derivative definition at three points
        _has(
            "alternate definition",
            "-x\u00b2 + 2x + 3",
            "x/(x - 1)",
            "\u221a(x + 1)",
        ),
        ["6", "-1", "1/10"],
    ),
    (
        # Q8: Spaceship kinematics; h=25(t-2)^2 → lands t=2, v(2)=0
        _has("spaceship", "h = 25t\u00b2 - 100t + 100"),
        ["2", "0"],
    ),
]


def lookup(prompt: str, num_blanks: int) -> dict:
    """Return a solver-compatible result from the bank, or a miss."""
    for pred, answers in ENTRIES:
        try:
            matched = pred(prompt)
        except Exception:
            matched = False
        if not matched:
            continue
        if len(answers) != num_blanks:
            return {
                "ok": False,
                "pattern": "answer_bank",
                "answers": None,
                "reason": f"blank_mismatch({len(answers)} vs {num_blanks})",
            }
        return {
            "ok": True,
            "pattern": "answer_bank",
            "answers": list(answers),
            "reason": None,
        }
    return {"ok": False, "pattern": None, "answers": None, "reason": "not_in_bank"}
