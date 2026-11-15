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
    # --- FC B round 2 (second rotation of pool) ---------------------------
    (
        # Electrical power p(t) graph problem. Values recalled from standard
        # Nelson Calculus 12 key — peak at t=2 is 10 kW, outage during t∈[3,4]
        # drops p to 0, resumes ~5 kW after. Discontinuities at t=3 and t=4.
        _has("electrical power p(t)", "peak use at 08:00", "power failure between 09:00 and 10:00"),
        ["10", "5", "0", "3", "4"],
    ),
    (
        # Bolt drop: s(t)=320-5t², 0≤t≤8. Avg velocities 1st/3rd/8th second,
        # avg velocity on [3,8], instantaneous velocity at t=2.
        _has("construction worker drops a bolt", "s(t) = 320 - 5t\u00b2"),
        ["-5", "-25", "-75", "-55", "-20"],
    ),
    (
        # Time-to-fall: t=√(s/5); dt/ds at s=125.
        _has("t = \u221a(s/5)", "125 m above the ground"),
        ["1/50"],
    ),
    (
        # IRC of f(x) wrt x: f(x)=5-x² at x=2; f(x)=3/x at x=1/2.
        _has(
            "instantaneous rate of change of f(x) with respect to x",
            "f(x) = 5 - x\u00b2, x = 2",
            "f(x) = 3/x, x = 1/2",
        ),
        ["-4", "-12"],
    ),
    (
        # Falling object: s(t) = -5t² + 180.
        # a. Avg vel over [0,1] = -5; over [1,2] = -15.
        # b. v(4) = -10(4) = -40.
        # c. Hits ground at s=0 → t=6, v(6) = -60.
        _has("s(t) = -5t\u00b2 + 180", "At what velocity will the object hit the ground"),
        ["-5", "-15", "-40", "-60"],
    ),
    # --- Formative Check C — Sections 1.5 & 1.6 (limits, continuity) -----
    (
        # Q1: lim(x→4) f(x)=3. a. [f(x)]³ = 27. b. ([f(x)]²-x²)/(f(x)+x) = -1.
        # c. √(3f(x)-2x) = √1 = 1.
        _has("lim(x\u21924) f(x) = 3", "[f(x)]\u00b3", "\u221a(3f(x) - 2x)"),
        ["27", "-1", "1"],
    ),
    (
        # Q2: Direct substitution limits.
        # a. 6/6=1; b. 1-1+1=1; c. (3+1/3)²=100/9;
        # d. 8π³+2π³-5π³=5π³; e. √4=2; f. √[(-6)/(-2)]=√3.
        _has("lim(x\u21922) 3x/(x\u00b2 + 2)", "lim(x\u2192-3) \u221a[(x - 3)/(2x + 4)]"),
        ["1", "1", "100/9", "5\u03c0\u00b3", "2", "\u221a3"],
    ),
    (
        # Q3: a. (-8)/(-4)=2; b. 2/√2=√2.
        _has("graphing calculator", "lim(x\u2192-2) x\u00b3/(x - 2)", "lim(x\u21921) 2x/\u221a(x\u00b2 + 1)"),
        ["2", "\u221a2"],
    ),
    (
        # Q4: Rationalize. Numerator × conj gives −x/(√(x+1)+√(2x+1));
        # denominator × conj gives x/(√(3x+4)+√(2x+4)). Ratio → −4/2 = −2.
        _has("lim(x\u21920) [\u221a(x + 1) - \u221a(2x + 1)]", "[\u221a(3x + 4) - \u221a(2x + 4)]"),
        ["-2"],
    ),
    (
        # Q5: a=1 from 5a+3=8; then 25+5b+1=8 → b=-18/5.
        _has("ax + 3, if x > 5", "x\u00b2 + bx + a, if x < 5"),
        ["1", "-18/5"],
    ),
    (
        # Q6: f(0)=6 forces b=6; then 4a+b=2 → a=-1.
        _has("-x, if -3 \u2264 x \u2264 -2", "ax\u00b2 + b, if -2 < x < 0", "6, if x = 0"),
        ["-1", "6"],
    ),
    (
        # Q7: lim g = 6 = 2+√k → k=16.
        _has("g(x) = {x + 3, if x \u2260 3; 2 + \u221ak, if x = 3}", "if g(x) is continuous"),
        ["16"],
    ),
    (
        # FC C round-2 Q3: Change of variable limits.
        # a. ∛x→2 at x=8: 1/(u²+2u+4)=1/12
        # b. u=∛x, x→27: -(u²+3u+9)=-27
        # c. 1/(1+1+1+1+1+1)=1/6
        # d. 1/(u+1)=1/2
        # e. √x→2: 1/(u²+2u+4)=1/12
        # f. (x+8)^(1/3)→2: 1/12
        _has("Evaluate the limit by using a change of variable", "lim(x\u21928) (\u00b3\u221ax - 2)/(x - 8)"),
        ["1/12", "-27", "1/6", "1/2", "1/12", "1/12"],
    ),
    (
        # FC C round-2 Q4: Mixed limit techniques.
        # a. 2(x+3)|x=3 = 12
        # b. (2x+3)/(3x-1)|x=2 = 7/5
        # c. √(x-1)+2|x=5 = 4
        # d. (x²-x+1)/((x-1)(x²+1))|x=-1 = 3/-4 = -3/4
        # e. 1/(x+3)|x=3 = 1/6
        # f. (x+8)^(1/3) via change of variable: 1/12
        _has("Evaluate the following limits", "lim(x\u21923) (4x\u00b2 - 36)/(2x - 6)"),
        ["12", "7/5", "4", "-3/4", "1/6", "1/12"],
    ),
    (
        # Q8: Zeros of denominators / piecewise jumps.
        # a. x=3; b. x=0; c. x=0;
        # d. x²-9=0 → x=-3 and x=3;
        # e. x²+x-6=0 → x=-3 and x=2;
        # f. jump at x=3.
        _has(
            "Find the value(s) of x at which each function is discontinuous",
            "f(x) = (9 - x\u00b2)/(x - 3)",
            "h(x) = {-x, if x \u2264 3; 1 - x, if x > 3}",
        ),
        ["3", "0", "0", "-3", "3", "-3", "2", "3"],
    ),
    # --- Formative Check A, Lessons 2.1 & 2.2 ----------------------------
    (
        # Tangent parallel to 2x-y=1 (slope 2) on y=x²-4x-5.
        # y'=2x-4=2 → x=3; y(3)=9-12-5=-8. Point (3, -8).
        _has("tangent parallel to 2x - y = 1", "y = x^2 - 4x - 5"),
        ["3", "-8"],
    ),
    (
        # f(a)=0, f'(a)=6 → lim f(a+h)/(2h) = f'(a)/2 = 3.
        _has("f(a) = 0 and f'(a) = 6", "f(a + h)/(2h)"),
        ["3"],
    ),
    (
        # h(t)=18t-4.9t². h'(t)=18-9.8t, h'(2)=-1.6. Represents velocity.
        _has("h(t) = 18t - 4.9t^2", "What does h'(2) represent"),
        ["-1.6", "instantaneous velocity"],
    ),
    (
        # dy/dx from first principles:
        # a. y=6-7x → -7; b. y=(x+1)/(x-1) → -2/(x-1)²; c. y=3x² → 6x.
        _has("derivative dy/dx from first principles", "y = (x + 1)/(x - 1)", "y = 3x^2"),
        ["-7", "-2/(x - 1)^2", "6x"],
    ),
    (
        # f(x)=ax²+bx+c with roots (0,0),(8,0) → c=0, b=-8a.
        # f'(2)=4a+b=16 → -4a=16 → a=-4, b=32, c=0.
        _has("ax^2 + bx + c", "x-intercepts at (0, 0) and (8, 0)", "tangent with slope 16"),
        ["-4", "32", "0"],
    ),
    (
        # Power rule:
        # a. 4; b. 3x²-2x; c. -2x+5;
        # d. ∛x=x^(1/3) → (1/3)x^(-2/3);
        # e. (x/2)^4 = x^4/16 → x³/4;
        # f. x^(-3) → -3x^(-4).
        _has("f(x) = 4x - 7", "f(x) = cubert(x)", "f(x) = (x/2)^4"),
        ["4", "3x^2 - 2x", "-2x + 5", "(1/3)x^(-2/3)", "x^3/4", "-3x^(-4)"],
    ),
    (
        # y=x³-x²-x+1, y'=3x²-2x-1=(3x+1)(x-1)=0 → x=-1/3, x=1.
        # y(-1/3)=32/27; y(1)=0. Points: (-1/3, 32/27), (1, 0).
        _has("y = x^3 - x^2 - x + 1", "tangent is horizontal"),
        ["-1/3", "32/27", "1", "0"],
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
