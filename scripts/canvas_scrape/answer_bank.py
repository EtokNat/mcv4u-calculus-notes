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
        ["4", "3x^2 - 2x", "-2x + 5", "(1/3)x^(-2/3)", "x^3/4", "-3x^-4"],
    ),
    (
        # y=x³-x²-x+1, y'=3x²-2x-1=(3x+1)(x-1)=0 → x=-1/3, x=1.
        # y(-1/3)=32/27; y(1)=0. Points: (-1/3, 32/27), (1, 0).
        _has("y = x^3 - x^2 - x + 1", "tangent is horizontal"),
        ["-1/3", "32/27", "1", "0"],
    ),
    (
        # FC A round-2: Tangent lines to y=x² through external point (1,-3).
        # Tangent at (a,a²): y=2ax-a². Through (1,-3): a²-2a-3=0 → a=3 or a=-1.
        # a=3 → y=6x-9; a=-1 → y=-2x-1.
        _has("tangent to the graph of f(x) = x^2", "pass through point (1, -3)"),
        ["y = 6x - 9", "y = -2x - 1"],
    ),
    (
        # FC A round-2: Falling bolt R(t)=320-5t², R'(t)=-10t, R'(2)=-20.
        _has("construction worker drops a bolt", "R(t) = 320 - 5t^2", "velocity of the bolt at t = 2"),
        ["-20"],
    ),
    (
        # FC A round-2: Six power-rule derivatives.
        # a. 3x^(5/3) → 5x^(2/3)
        # b. 4x^(-1/2) - 6x^(-1) → -2x^(-3/2) + 6x^(-2)
        # c. 6x^(-3) + 2x^(-2) - 3 → -18x^(-4) - 4x^(-3)
        # d. 9x^(-2) + 3x^(1/2) → -18x^(-3) + (3/2)x^(-1/2)
        # e. x^(1/2) + 6x^(3/2) + √2 → (1/2)x^(-1/2) + 9x^(1/2)
        # f. x^(-1) + x^(-1/2) → -x^(-2) - (1/2)x^(-3/2)
        _has("y = 3x^(5/3)", "y = 4x^(-1/2) - 6/x", "y = (1 + sqrt(x))/x"),
        [
            "5x^(2/3)",
            "-2x^(-3/2) + 6x^(-2)",
            "-18x^(-4) - 4x^(-3)",
            "-18x^(-3) + (3/2)x^(-1/2)",
            "(1/2)x^(-1/2) + 9x^(1/2)",
            "-x^(-2) - (1/2)x^(-3/2)",
        ],
    ),
    (
        # FC A round-2: Subway s(t)=t²-(1/3)t³, v(t)=2t-t²=0.5
        # → t² - 2t + 0.5 = 0 → t = 1 ± √2/2.
        _has("subway train", "s(t) = t^2 - (1/3)t^3", "velocity of 0.5 km/min"),
        ["1 - sqrt(2)/2", "1 + sqrt(2)/2"],
    ),
    (
        # FC A: Demand function D(p) = 20/sqrt(p - 1) at (5, 10)
        # D'(p) = -10(p - 1)^(-3/2), D'(5) = -10/8 = -1.25
        _has("demand function", "D(p) = 20/sqrt(p - 1)", "point (5, 10)"),
        ["-1.25"],
    ),
    (
        # FC A: Line ax - 4y + 21 = 0 tangent to y = a/x^2 at x = -2
        # y(-2) = a/4; -2a - 4(a/4) + 21 = 0 -> -3a + 21 = 0 -> a = 7
        _has("ax - 4y + 21 = 0", "y = a/x^2", "x = -2"),
        ["7"],
    ),
    (
        # FC A: Line y = 8x + b tangent to y = 2x^2
        # y' = 4x = 8 -> x = 2, y = 8; 8 = 16 + b -> b = -8
        _has("y = 8x + b", "tangent to the curve y = 2x^2"),
        ["2", "8", "-8"],
    ),
    (
        # FC A: y = -x^3 + 6x^2 slope -12 and slope -15
        # y' = -3x^2 + 12x; -3x^2 + 12x = -12 -> x^2 - 4x - 4 = 0 -> 2 +- 2*sqrt(2)
        # -3x^2 + 12x = -15 -> x^2 - 4x - 5 = 0 -> -1, 5
        _has("y = -x^3 + 6x^2", "slope of -12", "slope of -15"),
        ["2 - 2*sqrt(2)", "2 + 2*sqrt(2)", "-1", "5"],
    ),
    (
        # FC A: tangent to f(x)=sqrt(x+1) parallel to x-6y+4=0 (slope 1/6)
        # f'(x)=1/(2sqrt(x+1))=1/6 -> x=8, y=3 -> x - 6y + 10 = 0
        _has("f(x) = sqrt(x + 1)", "parallel to x - 6y + 4 = 0"),
        ["x - 6y + 10 = 0"],
    ),
    (
        # FC A: tangent to y = 3/cubert(x) parallel to x + 16y + 3 = 0 (slope -1/16)
        # y' = -x^(-4/3) = -1/16 -> x^(4/3) = 16 -> x = -8, 8
        _has("y = 3/cubert(x)", "parallel to the line x + 16y + 3 = 0"),
        ["-8", "8"],
    ),
    (
        # FC A: f'(a) for f(x)=x^3-sqrt(x) at a=4 -> 191/4; f(x)=7-6sqrt(x)+5x^(2/3) at a=64 -> 11/24
        _has("f(x) = x^3 - sqrt(x), a = 4", "5x^(2/3), a = 64"),
        ["191/4", "11/24"],
    ),
    (
        # FC A: find f(a+h) and f(a+h)-f(a) for 6 functions (12 blanks)
        _has("find f(a + h) and f(a + h) - f(a)", "f(x) = 5x - 2", "f(x) = 4 - 2x - x^2"),
        [
            "5a + 5h - 2", "5h",
            "a^2 + 2ah + h^2 + 3a + 3h - 1", "2ah + h^2 + 3h",
            "a^3 + 3a^2h + 3ah^2 + h^3 - 4a - 4h + 1", "3a^2h + 3ah^2 + h^3 - 4h",
            "a^2 + 2ah + h^2 + a + h - 6", "2ah + h^2 + h",
            "-7a - 7h + 4", "-7h",
            "4 - 2a - 2h - a^2 - 2ah - h^2", "-2h - 2ah - h^2",
        ],
    ),
    (
        # FC A: R(x) = 750x - x^2/6 - (2/3)x^3 -> R'(x) = 750 - x/3 - 2x^2, R'(10) = 1640/3
        _has("R(x) = 750x - x^2/6 - (2/3)x^3", "10 refrigerators per month"),
        ["750 - x/3 - 2x^2", "1640/3"],
    ),
    (
        # FC A: piecewise & abs derivatives (14 blanks)
        _has("f(x) = x^2, x < 3; f(x) = x + 6, x >= 3", "f(x) = |3x^2 - 6|", "f(x) = ||x| - 1|"),
        [
            "2x", "1", "does not exist",
            "6x", "-6x", "-sqrt(2)", "sqrt(2)",
            "-1", "1", "-1", "1", "-1", "0", "1",
        ],
    ),
    (
        # FC A: normal to y = x^4 has slope 16 -> tangent slope -1/16 -> 4x^3 = -1/16 -> x = -1/4, y = 1/256
        _has("curve y = x^4", "normal have a slope of 16"),
        ["-1/4", "1/256"],
    ),
    (
        # FC A: tangent to y = x^3 - 6x^2 + 8x at A(3, -3) intersects at B(0, 0)
        _has("y = x^3 - 6x^2 + 8x", "point A(3, -3)", "Point B"),
        ["0", "0"],
    ),
    (
        # FC A: 6 derivatives (4x^2-7x+8, -2x^3+4x^2+5x-6, 5/x^2-3/x^3, sqrt(x)+cubert(x), 7x^-2-3sqrt(x), -4x^-1+5x-1)
        _has("f(x) = 4x^2 - 7x + 8", "f(x) = 5/x^2 - 3/x^3", "f(x) = -4x^-1 + 5x - 1"),
        [
            "8x - 7",
            "-6x^2 + 8x + 5",
            "-10x^-3 + 9x^-4",
            "(1/2)x^(-1/2) + (1/3)x^(-2/3)",
            "-14x^-3 - (3/2)x^(-1/2)",
            "4x^-2 + 5",
        ],
    ),
    (
        # FC A: y = (1/5)x^5 - 10x slope 6 -> x^4 - 10 = 6 -> x = -2, 2 -> (-2, 68/5), (2, -68/5)
        _has("y = (1/5)x^5 - 10x", "have a slope of 6"),
        ["-2", "68/5", "2", "-68/5"],
    ),
    (
        # FC A: tangents from (0, 3) to y = -3x^2 -> (-1, -3), (1, -3)
        _has("point (0, 3)", "y = -3x^2"),
        ["-1", "-3", "1", "-3"],
    ),
    (
        # FC A: cliff 150 m, d(t) = 4.9t^2 -> avg [2,5]=34.3, inst(4)=39.2, hit ground=54.2
        _has("150 m high", "d(t) = 4.9t^2", "2 s to 5 s"),
        ["34.3", "39.2", "54.2"],
    ),
    (
        # FC A: C(x) = (1/3)x^3 + 40x + 700 -> C'(x) = x^2 + 40; MC=76 -> x=6
        _has("C(x) = (1/3)x^3 + 40x + 700", "marginal cost is $76"),
        ["x^2 + 40", "6"],
    ),
    (
        # FC A: y = 5x^2 - 8x + 4 -> dy/dx = 10x - 8
        _has("y = 5x^2 - 8x + 4", "first principles"),
        ["10x - 8"],
    ),
    (
        # FC A: Tank V(t) = 500(1 - t/90)^2 -> V(60)=500/9=55.6, avg[0,60]=-200/27=-7.4, V'(30)=-7.4
        _has("holds 500 L of liquid", "V(t) = 500(1 - t/90)^2"),
        ["55.6", "-7.4", "7.4"],
    ),
    (
        # FC A: y = x^2 + ax + b tangent to y = x^3 at (1, 1) -> a = 1, b = -1
        _has("y = x^2 + ax + b", "tangent to the curve y = x^3", "point (1, 1)"),
        ["1", "-1"],
    ),
    (
        # FC A: Ant colony A(t) = -t^3 + 5t + 750 (in hundreds) -> -3t^2+5, -7000, 75000, 9.3
        _has("ant colony", "A(t) = -t^3 + 5t + 750"),
        ["-3t^2 + 5", "-7000", "75000", "9.3"],
    ),
    # --- Formative Check B, Lessons 2.3 & 2.4 ----------------------------
    (
        # FC B: F(x) = [b(x)][c(x)] -> product rule
        _has("F(x) = [b(x)][c(x)]", "Express F'(x)"),
        ["b'(x)c(x) + b(x)c'(x)"],
    ),
    (
        # FC B: horizontal tangents for y=2(x-29)(x+1) -> (14, -450) and y=(x^2+2x+1)^2 -> (-1, 0)
        _has("tangent to the curve is horizontal", "2(x - 29)(x + 1)", "(x^2 + 2x + 1)(x^2 + 2x + 1)"),
        ["14", "-450", "-1", "0"],
    ),
    (
        # FC B: 75 L gas tank V(t)=75(1-t/24)^2, 60% full -> V'(t) = -5*sqrt(15)/4 ≈ -4.84
        _has("75 L gas tank", "V(t) = 75(1 - t/24)^2", "60% full"),
        ["-4.84"],
    ),
    (
        # FC B: 4x - y + 11 = 0 tangent to y = 16/x^2 - 1 -> dy/dx = -32/x^3, point (-2, 3)
        _has("4x - y + 11 = 0", "y = 16/x^2 - 1"),
        ["-32/x^3", "-2", "3"],
    ),
    (
        # FC B: tangent equations: y=-3x^2+6x+4 at x=1 -> y=7; y=3-2sqrt(x) at x=9 -> y=(-1/3)x; f(3) -> y=-128x+297
        _has("equation of the tangent", "y = -3x^2 + 6x + 4", "y = 3 - 2 sqrt(x)"),
        ["y = 7", "y = (-1/3)x", "y = -128x + 297"],
    ),
    (
        # FC B: when not appropriate to use product rule -> constant, expand
        _has("not appropriate to use the product rule", "one factor is a"),
        ["constant", "expand"],
    ),
    (
        # FC B: dy/dx at given x for 6 products -> 9, -4, -9, -36, 22, 671
        _has("y = (2 + 7x)(x - 3), x = 2", "y = x(5x - 2)(5x + 2), x = 3"),
        ["9", "-4", "-9", "-36", "22", "671"],
    ),
    (
        # FC B: tangent to y = (5x^2 + 9x - 2)(-x^2 + 2x + 3) at (1, 48) -> slope 76 -> y = 76x - 28
        _has("y = (5x^2 + 9x - 2)(-x^2 + 2x + 3)", "at (1, 48)"),
        ["y = 76x - 28"],
    ),
    (
        # FC B: y = x^3 + 2 slope 12 -> 3x^2 = 12 -> (-2, -6), (2, 10)
        _has("y = x^3 + 2", "slope of the tangent is 12"),
        ["-2", "-6", "2", "10"],
    ),
    # --- Formative Check C, Lessons 2.5 & 2.6 ----------------------------
    (
        # FC C: rewrite without quotient rule (10 blanks)
        _has("complete it without using the quotient rule", "f(x) = (x^2 + 3x)/x"),
        [
            "x + 3", "1",
            "3x^(2/3)", "2x^(-1/3)",
            "(1/10)x^-5", "(-1/2)x^-6",
            "4x^2 + 3", "8x",
            "t + 3", "1",
        ],
    ),
    (
        # FC C: quotient rule differentiate & simplify (6 blanks)
        _has("Use the quotient rule to differentiate each function", "h(x) = x/(x + 1)", "y = (x^2 - x + 1)/(x^2 + 3)"),
        [
            "1/(x + 1)^2",
            "13/(t + 5)^2",
            "(2x^4 - 3x^2)/(2x^2 - 1)^2",
            "-2x/(x^2 + 3)^2",
            "(5x^2 + 6x + 5)/(1 - x^2)^2",
            "(x^2 + 4x - 3)/(x^2 + 3)^2",
        ],
    ),
    (
        # FC C: c(t) = 5t/(2t^2 + 7) max at t = sqrt(14)/2 ≈ 1.87
        _has("concentration, c, of a drug", "c(t) = 5t/(2t^2 + 7)"),
        ["1.87"],
    ),
    (
        # FC C: s(t) = t^(1/3) (4t - 5)^(2/3) at t = 8 -> 91/36 (1 blank in DOM)
        _has("s(t) = t^(1/3) (4t - 5)^(2/3)", "t = 8"),
        ["91/36"],
    ),
    (
        # FC C: y = 3u^2 + 2u, u = sqrt(x^2 + 5) at x = -2 -> dy/dx = -40/3
        _has("y = 3u^2 + 2u", "u = sqrt(x^2 + 5)", "x = -2"),
        ["-40/3"],
    ),
    (
        # FC C: P(t) = (t^(1/4) + 3)^3 at t = 16 -> 75/32
        _has("amount of pollution in a certain lake", "P(t) = (t^(1/4) + 3)^3"),
        ["75/32"],
    ),
    (
        # FC C: h = g o f table -> h(-1) = g(1) = -4; h'(-1) = g'(1)*f'(-1) = (-7)(-5) = 35
        _has("Given h = g o f", "evaluate h(-1) and h'(-1)"),
        ["-4", "35"],
    ),
    (
        # FC C: quotient dy/dx at given x -> 13/4, 7/25, 200/841, -7/3
        _has("y = (3x + 2)/(x + 5), x = -3", "y = [(x + 1)(x + 2)]/[(x - 1)(x - 2)], x = 4"),
        ["13/4", "7/25", "200/841", "-7/3"],
    ),
    (
        # FC C: tangent to y = (x^2 - 1)/(3x) at x = 2 -> y = (5/12)x - 1/3
        _has("tangent to the curve y = (x^2 - 1)/(3x)", "x = 2"),
        ["y = (5/12)x - 1/3"],
    ),
    (
        # FC C: horizontal tangents y=(x^2-4)^5 -> -2,0,2 and y=(x^3-x)^2 -> -1, -sqrt(3)/3, 0, sqrt(3)/3, 1
        _has("y = (x^2 - 4)^5", "y = (x^3 - x)^2", "horizontal tangent"),
        ["-2", "0", "2", "-1", "-sqrt(3)/3", "0", "sqrt(3)/3", "1"],
    ),
    (
        # FC C: h'(2) for h(x)=f(g(x)), f(u)=u^2-1, g(2)=3, g'(2)=-1 -> 2(3)(-1) = -6
        _has("Find h'(2)", "h(x) = f(g(x))", "f(u) = u^2 - 1"),
        ["-6"],
    ),
    (
        # FC C: y = 3x/(x - 4) slope -12/25 -> (-1, 3/5), (9, 27/5)
        _has("y = 3x/(x - 4)", "slope of the tangent is -12/25"),
        ["-1", "3/5", "9", "27/5"],
    ),
    (
        # FC C: y = (1 + x^3)^2 and y = 2x^6 same slope -> x = 0 or x = 1
        _has("y = (1 + x^3)^2", "y = 2x^6", "same slope"),
        ["0", "1"],
    ),
    (
        # FC C: 50 000 L tank drained in 30 min at t=10 -> -2222
        _has("50 000 L tank", "V(t) = 50 000 (1 - t/30)^2"),
        ["-2222"],
    ),
    (
        # FC C: chain rule Leibniz notation -> 52, 54, 320, 78
        _has("chain rule, in Leibniz notation", "y = 3u^2 - 5u + 2", "u = sqrt(x), x = 4"),
        ["52", "54", "320", "78"],
    ),
    (
        # FC C: f(x) = sqrt(x) and g(x) = x^2 - 1 -> 0, 0, -1, sqrt(15), sqrt(x^2 - 1), x - 1
        _has("f(x) = sqrt(x) and g(x) = x^2 - 1", "f(g(1))", "g(f(x))"),
        ["0", "0", "-1", "sqrt(15)", "sqrt(x^2 - 1)", "x - 1"],
    ),
    # --- Unit 3 Formative Check A, Sections 3.1a & 3.1b -----------------
    (
        # U3 FC A: s(t) = 4t - 7t^2 + 2t^3 -> v(2)=0, a(2)=10, a=0 at t=7/6 ≈ 1.2
        _has("s(t) = 4t - 7t^2 + 2t^3", "velocity and acceleration at t = 2"),
        ["0", "10", "1.2"],
    ),
    (
        # U3 FC A: s(t) = t^2 - 6t + 8 -> v(t) = 2t - 6, t = 3
        _has("s(t) = t^2 - 6t + 8", "velocity at time t"),
        ["2t - 6", "3"],
    ),
    (
        # U3 FC A: absolute extreme values (12 blanks)
        _has("absolute extreme values", "f(x) = x^3 + 3x^2 + 1", "f(x) = 1/x - 1/x^3"),
        ["21", "2", "1", "0", "25", "3", "0", "-2", "2sqrt(3)/9", "sqrt(3)", "0", "1"],
    ),
    (
        # U3 FC A: cubes total surface area and volume (8 blanks)
        _has("surface area and volume for cubes", "sqrt(5) cm", "2k cm"),
        ["54", "27", "30", "5sqrt(5)", "72", "24sqrt(3)", "24k^2", "8k^3"],
    ),
    (
        # U3 FC A: interval notation (6 blanks)
        _has("interval notation", "{x in R | x > 3}", "{x in R | -4 < x < 4}"),
        ["(3, ∞)", "(-∞, -2]", "(-∞, 0)", "[-5, ∞)", "(-2, 8]", "(-4, 4)"],
    ),
    (
        # U3 FC A: graphing max/min (12 blanks)
        _has("Use graphing technology", "f(x) = x^2 - 5", "f(x) = -2 cos 2x - 5"),
        ["-5", "0", "25", "-5", "7", "5", "-1", "0", "5", "-1", "-3", "-7"],
    ),
    (
        # U3 FC A: swimming pool bacteria N(t) = 30t^2 - 240t + 500 -> min at t=4 is 20
        _has("swimming pool", "N(t) = 30t^2 - 240t + 500"),
        ["20"],
    ),
    (
        # U3 FC A: largest rectangle inscribed in right triangle -> 15, 30
        _has("largest rectangle that can be inscribed in a right triangle", "5 cm and 12 cm"),
        ["15", "30"],
    ),
    (
        # U3 FC A: minimal distance from (-3, 3) to y = (x - 3)^2 -> sqrt(17)
        _has("minimal distance from point (-3, 3)", "y = (x - 3)^2"),
        ["sqrt(17)"],
    ),
    (
        # U3 FC A: golf net open at one end, V=144 -> A = 3xL + x^2 = 432/x + x^2 -> x=6, L=4
        _has("net enclosure for practising golf shots", "144 m^3"),
        ["6", "4"],
    ),
    (
        # U3 FC A: square-based rectangular cardboard box V=1000 -> cube side=10, SA=600
        _has("square-based rectangular cardboard box", "1000 cm^3"),
        ["10", "600"],
    ),
    # --- Unit 3 Formative Check C, Sections 3.4 & mixed ------------------
    (
        # U3 FC C: CD players R(x) = (90 - x)(50 + 5x) -> x = 40, price = $50
        _has("personal CD players", "regular price for each CD player is $90"),
        ["40", "50"],
    ),
    (
        # U3 FC C: cough v(r) = Ar^2(r0 - r) -> r = 2r0/3, v_max = 4Ar0^3/27
        _has("During a cough", "v(r) = Ar^2(r0 - r)"),
        ["2r0/3", "4Ar0^3/27"],
    ),
    (
        # U3 FC C: Ajax to Union Station bus R(k) = (20 + 0.5k)(10000 - 200k) -> k=5, fare=22.5, R=202500
        _has("Ajax and Union Station", "if the fare increases by $0.50"),
        ["22.5", "202500"],
    ),
    (
        # U3 FC C: unit cost U(x) = C(x)/x, C(x) = 625 + 15x + 0.01x^2 -> x = 250
        _has("C(x) = 625 + 15x + 0.01x^2", "unit cost is minimized"),
        ["250"],
    ),
    (
        # U3 FC C: 50-unit apartment building, $850, all occupied, $100 inc -> 10 vacant -> boundary x=0 => $850
        _has("50-unit apartment building", "$850 per month"),
        ["850"],
    ),
    (
        # U3 FC C: basketball arena holds 20 000, 14 000 at $75, -$5 -> +800 => x=-1.25 -> $81.25
        _has("professional basketball team", "holds 20 000 spectators"),
        ["81.25"],
    ),
    (
        # U3 FC C: average cost AC(x) = 0.004x + 40 + 16000/x -> x = 2000
        _has("C(x) = 0.004x^2 + 40x + 16 000", "minimizes the average cost per unit"),
        ["2000"],
    ),
    # --- Unit 4 Formative Check A --------------------------------------
    (
        # U4 FC A: f(x) = x^4 - 32x + 4 -> x=2, inc (2,∞), dec (-∞,2), local min -44
        _has("f(x) = x^4 - 32x + 4", "the local minimum is"),
        ["2", "(2, ∞)", "(-∞, 2)", "-44"],
    ),
    (
        # U4 FC A: inc/dec of 4 functions
        _has("y = 3x^2 - 12x + 7", "y = 4x^3 - 12x^2 + 8", "f(x) = (x^2 - 1)/(x^2 + 3)"),
        [
            "(-∞, 2)", "(2, ∞)",
            "(0, 2)", "(-∞, 0) U (2, ∞)",
            "(-∞, -3) U (-3, ∞)", "none",
            "(-∞, 0)", "(0, ∞)",
        ],
    ),
    (
        # U4 FC A: f'(x) = (x - 1)(x + 2)(x + 3)
        _has("f'(x) = (x - 1)(x + 2)(x + 3)", "Determine where f is increasing"),
        ["(-3, -2) U (1, ∞)", "(-∞, -3) U (-2, 1)"],
    ),
    (
        # U4 FC A: f(x) = x^2 + px + q, extremum f(1) = 5 on [0, 2]
        _has("f(x) = x^2 + px + q", "f(1) = 5 is an extremum"),
        ["-2", "6", "minimum"],
    ),
    (
        # U4 FC A: f(x) = x^3 + bx^2 + c critical point (-2, 6)
        _has("f(x) = x^3 + bx^2 + c", "critical point at (-2, 6)"),
        ["3", "2"],
    ),
    (
        # U4 FC A: f(x) = (2x + 4)/(x^2 - k^2) critical points exist when -2 < k < 2
        _has("f(x) = (2x + 4)/(x^2 - k^2)", "The conditions are"),
        ["-2 < k < 2"],
    ),
    (
        # U4 FC A: g(x) = ax^3 + bx^2 + cx + d max (2, 4), min (0, 0)
        _has("g(x) = ax^3 + bx^2 + cx + d", "local maximum at (2, 4)"),
        ["-1", "3", "0", "0"],
    ),
    (
        # U4 FC A: 6 functions inc/dec
        _has("f(x) = x^3 + 3x^2 + 1", "f(x) = x^5 - 5x^4 + 100", "f(x) = 3x^4 + 4x^3 - 12x^2"),
        [
            "(-∞, -2) U (0, ∞)", "(-2, 0)",
            "(-∞, 0) U (4, ∞)", "(0, 4)",
            "(-∞, -1) U (1, ∞)", "(-1, 0) U (0, 1)",
            "(-1, 3)", "(-∞, -1) U (3, ∞)",
            "(-2, 0) U (1, ∞)", "(-∞, -2) U (0, 1)",
            "(0, ∞)", "(-∞, 0)",
        ],
    ),
    (
        # U4 FC A: points where f'(x) = 0 for 4 functions
        _has("f(x) = x^3 + 6x^2 + 1", "f(x) = sqrt(x^2 + 4)", "f(x) = 5x/(x^2 + 1)"),
        ["(-4, 33)", "(0, 1)", "(0, 2)", "(-2, -125)", "(1/2, 0)", "(9/4, -3087/64)", "(-1, -5/2)", "(1, 5/2)"],
    ),
    (
        # U4 FC A: critical numbers of 6 functions (13 blanks)
        _has("y = -2x^2 + 16x - 31", "y = 3x^5 - 25x^3 + 60x", "y = x/(x^2 + 2)"),
        ["4", "-3", "3", "-sqrt(2)", "0", "sqrt(2)", "-2", "-1", "1", "2", "0", "-sqrt(2)", "sqrt(2)"],
    ),
    (
        # U4 FC A: 6 functions critical points & classify (17 blanks)
        _has("f(x) = -2x^2 + 8x + 13", "f(x) = sqrt(x^2 - 2x + 2)", "f(x) = 3x^4 - 4x^3"),
        [
            "(2, 21)", "local maximum",
            "(-3, 20)", "local maximum", "(3, -16)", "local minimum",
            "(-2, -4)", "local maximum", "(-1, -5)", "local minimum",
            "none",
            "(1, 1)", "local minimum",
            "(0, 0)", "neither", "(1, -1)", "local minimum",
        ],
    ),
    (
        # U4 FC A: f(x) = 3x^4 + ax^3 + bx^2 + cx + d horizontal tangents (-2, -73), (0, -9)
        _has("f(x) = 3x^4 + ax^3 + bx^2 + cx + d", "(-2, -73)"),
        [
            "-4", "-36", "0", "-9",
            "(3, -198)",
            "(-2, -73)", "local minimum", "(0, -9)", "local maximum", "(3, -198)", "local minimum",
        ],
    ),
    (
        # U4 FC A: 4 functions critical numbers, inc/dec, classify (24 blanks)
        _has("f(x) = x^2 - 7x - 18", "f(x) = -2x^3 + 9x^2 + 3", "f(x) = x^5 - 5x"),
        [
            "7/2", "(7/2, ∞)", "(-∞, 7/2)", "minimum",
            "0", "3", "(0, 3)", "(-∞, 0) U (3, ∞)", "minimum", "maximum",
            "-1", "0", "1", "(-1, 0) U (1, ∞)", "(-∞, -1) U (0, 1)", "maximum", "minimum", "minimum",
            "-1", "1", "(-∞, -1) U (1, ∞)", "(-1, 1)", "maximum", "minimum",
        ],
    ),
    (
        # U4 FC A: g(x) = 2x^3 - 3x^2 - 12x + 15 inc/dec
        _has("g(x) = 2x^3 - 3x^2 - 12x + 15", "is increasing and where it is decreasing"),
        ["(-∞, -1) U (2, ∞)", "(-1, 2)"],
    ),
    (
        # U4 FC A: drug concentration C(t) = t/4 + 2t^-2
        _has("C(t) = t/4 + 2t^-2", "concentration of the drug"),
        ["(2^(4/3), ∞)", "(0, 2^(4/3))"],
    ),
    (
        # U4 FC A: x- and y-intercepts of 3 functions (8 blanks)
        _has("Find the x- and y-intercepts of each function below", "y = x^4 - 8x^2", "2x/(x^2 + 9)"),
        ["-2sqrt(2)", "0", "2sqrt(2)", "0", "0", "0", "-3.1", "1"],
    ),
    (
        # U4 FC A: g(x) = 2x^4 - 8x^3 - x^2 + 6x (9 blanks)
        _has("g(x) = 2x^4 - 8x^3 - x^2 + 6x", "critical x-values"),
        ["-1/2", "1/2", "3", "-1/2", "local minimum", "1/2", "local maximum", "3", "local minimum"],
    ),
    (
        # U4 FC A: f(x) = x^3 - kx critical number count
        _has("f(x) = x^3 - kx", "no critical numbers"),
        ["k < 0", "k = 0", "k > 0"],
    ),
    (
        # U4 FC A: f(x) = x^3 + ax^2 + bx + c increases to 18 at x=-3, decreases to -14 at x=1
        _has("increases to a value of 18 at x = -3", "decreases to a value of -14 at x = 1"),
        ["3", "-9", "-9"],
    ),
    (
        # U4 FC A: 3 functions critical points & first deriv test (14 blanks)
        _has("Use the first derivative test to state whether each point", "y = x^4 - 8x^2", "y = x^3 + 3x^2 + 1"),
        [
            "(-2, -16)", "local minimum", "(0, 0)", "local maximum", "(2, -16)", "local minimum",
            "(-3, -1/3)", "local minimum", "(3, 1/3)", "local maximum",
            "(-2, 5)", "local maximum", "(0, 1)", "local minimum",
        ],
    ),
    (
        # U4 FC A: f'(x) = (x + 1)(x - 2)(x + 6)
        _has("f'(x) = (x + 1)(x - 2)(x + 6)", "critical numbers of f"),
        ["-6", "local minimum", "-1", "local maximum", "2", "local minimum"],
    ),
    (
        # U4 FC A: 4 functions critical points & horizontal tangent (21 blanks)
        _has("h(x) = -6x^3 + 18x^2 + 3", "y = (x - 5)^(1/3)", "f(x) = (x^2 - 1)^(1/3)"),
        [
            "(0, 3)", "local minimum", "horizontal", "(2, 27)", "local maximum", "horizontal",
            "(0, 0)", "neither", "horizontal",
            "(5, 0)", "neither", "vertical",
            "(-1, 0)", "neither", "vertical", "(0, -1)", "local minimum", "horizontal", "(1, 0)", "neither", "vertical",
        ],
    ),
    # --- Unit 4 Formative Check B (14518) ------------------------------
    (
        # U4 FC B: second derivative & above/below tangent line (8 blanks)
        _has("f(x) = 2x^3 - 10x + 3", "p(w) = w/sqrt(w^2 + 1)", "s(t) = 2t/(t - 4)"),
        ["24", "above", "4", "above", "-9sqrt(10)/1000", "below", "-2/27", "below"],
    ),
    (
        # U4 FC B: f''(x) graph concave up/down & inflection x=1; 0, 2 (6 blanks)
        _has("concave up before x = 1", "inflection points at x = 0 and x = 2"),
        ["(-∞, 1)", "(1, ∞)", "1", "(-∞, 0) U (2, ∞)", "(0, 2)", "0, 2"],
    ),
    (
        # U4 FC B: g''(x) graph concave up/down & inflection -1, 3; -4.5, 1, 5 (6 blanks)
        _has("concave up on -1 < x < 3", "concave up on -4.5 < x < 1 and x > 5"),
        ["(-1, 3)", "(-∞, -1) U (3, ∞)", "-1, 3", "(-4.5, 1) U (5, ∞)", "(-∞, -4.5) U (1, 5)", "-4.5, 1, 5"],
    ),
    (
        # U4 FC B: discontinuities 6 functions (22 blanks)
        _has("y = x/(x + 5)", "s = 1/(t - 3)^2", "f(x) = 6/((x + 3)(x - 1))"),
        [
            "-5", "∞", "-∞",
            "2", "-∞", "∞",
            "3", "∞",
            "hole at x = 3", "no vertical asymptote",
            "-3", "∞", "-∞", "1", "-∞", "∞",
            "-1", "∞", "-∞", "1", "-∞", "∞",
        ],
    ),
    (
        # U4 FC B: VA and side behaviour 4 functions (18 blanks)
        _has("f(x) = (x - 1)/(x + 2)", "f(x) = 1/(9 - x^2)", "3x^2 - 13x - 10"),
        [
            "-2", "∞", "-∞",
            "-3", "-∞", "∞", "3", "∞", "-∞",
            "-3", "-∞", "∞",
            "-2/3", "∞", "-∞", "5", "∞", "-∞",
        ],
    ),
    (
        # U4 FC B: lim x->+-infinity (8 blanks)
        _has("Evaluate lim x->infinity f(x) and lim x->-infinity f(x)", "(2x + 3)/(x - 1)", "(2x^5 - 3x^2 + 5)/(3x^4 + 5x - 4)"),
        ["2", "2", "5", "5", "-5/2", "-5/2", "∞", "-∞"],
    ),
    (
        # U4 FC B: discontinuities x/(x-5)^2, 5/(x^2+9), (x-2)/(x^2-12x+12) (9 blanks)
        _has("f(x) = x/(x - 5)^2", "f(x) = 5/(x^2 + 9)", "f(x) = (x - 2)/(x^2 - 12x + 12)"),
        [
            "x = 5", "∞",
            "none",
            "x = 6 - 2sqrt(6)", "-∞", "∞", "x = 6 + 2sqrt(6)", "-∞", "∞",
        ],
    ),
    (
        # U4 FC B: critical points via second derivative test (13 blanks)
        _has("y = x^3 - 6x^2 - 15x + 10", "y = 25/(x^2 + 48)", "y = (x - 3)^3 + 8", "Use the second derivative test"),
        ["-1", "18", "5", "-90", "0", "25/48", "-1", "-2", "1", "2", "3", "8", "neither"],
    ),
    (
        # U4 FC B: f(x) = x^3 + (3/2)x^2 - 7x + 5 on [-4, 3] (8 blanks)
        _has("f(x) = x^3 + (3/2)x^2 - 7x + 5", "-4 <= x <= 3"),
        ["(-3 - sqrt(93))/6", "31sqrt(93)/36 + 35/4", "(-3 + sqrt(93))/6", "35/4 - 31sqrt(93)/36", "3", "49/2", "-4", "-7"],
    ),
    (
        # U4 FC B: oblique asymptote approach above/below (4 blanks)
        _has("(3x^2 - 2x - 17)/(x - 3)", "(2x^2 + 9x + 2)/(2x + 3)"),
        ["below", "above", "above", "below"],
    ),
    (
        # U4 FC B: oblique asymptotes in form y = mx + b (2 blanks)
        _has("(2x^2 - 7x + 5)/(2x - 1)", "(4x^3 - x^2 - 15x - 50)/(x^2 - 3x)"),
        ["y = x - 3", "y = 4x + 11"],
    ),
    (
        # U4 FC B: points of inflection (9 blanks)
        _has("Determine the points of inflection for each function in question 2", "y = x^3 - 6x^2 - 15x + 10", "y = (x - 3)^3 + 8"),
        ["2", "-36", "-4", "25/64", "4", "25/64", "none", "3", "8"],
    ),
    (
        # U4 FC B: f(x) = sqrt(x + 1) + b/x inflection at x = 3 -> 27/64 = 0.421875
        _has("f(x) = sqrt(x + 1) + b/x", "inflection at x = 3"),
        ["0.421875"],
    ),
    (
        # U4 FC B: 8 limits as x -> infinity (8 blanks)
        _has("Determine each limit as x -> infinity", "(3 - 2x)/(3x)", "(5x + 4 - 7/(x + 3))"),
        ["-2/3", "1/6", "-3", "0", "∞", "1", "1", "∞"],
    ),
    (
        # U4 FC B: g(x) = (x^2 + 7x + 10)/((x - 3)(x + 2)) (6 blanks)
        _has("g(x) = (x^2 + 7x + 10)/((x - 3)(x + 2))", "hole at x ="),
        ["-2", "x = 3", "-∞", "∞", "y = 1", "x != -2, 3"],
    ),
    (
        # U4 FC B: f(x) = (ax + 5)/(3 - bx), VA x=5, HA y=-3 -> a=9/5, b=3/5
        _has("f(x) = (ax + 5)/(3 - bx)", "vertical asymptote at x = 5"),
        ["9/5", "3/5"],
    ),
    (
        # U4 FC B: lim [f(x) - g(x)] -> -2
        _has("f(x) = (x^2 + 1)/(x + 1)", "g(x) = (x^2 + 2x + 1)/(x + 1)"),
        ["-2"],
    ),
    (
        # U4 FC B: x^4 + 4x and (4w^2 - 3)/w^3 points of inflection (5 blanks)
        _has("f(x) = x^4 + 4x", "g(w) = (4w^2 - 3)/w^3"),
        ["none", "-3sqrt(2)/2", "-10sqrt(2)/9", "3sqrt(2)/2", "10sqrt(2)/9"],
    ),
    (
        # U4 FC B: vertical, horizontal, oblique asymptotes 4 functions (16 blanks)
        _has("f(x) = (3x - 1)/(x + 5)", "g(x) = (x^2 + 3x - 2)/(x - 1)^2", "m(x) = (5x^2 - 3x + 2)/(x - 2)"),
        [
            "x = -5", "∞", "-∞", "y = 3",
            "x = 1", "∞", "y = 1",
            "x = -2", "-∞", "∞", "y = 1",
            "x = 2", "-∞", "∞", "none", "5x + 7",
        ],
    ),
    # --- Unit 4 Formative Check C (14519) ------------------------------
    (
        # U4 FC C: f(x) = 5x/(x - 1)^2 full curve-sketching (15 blanks)
        _has("f(x) = 5x/(x - 1)^2", "f'(x) = -5(x + 1)/(x - 1)^3"),
        [
            "x != 1", "0", "0",
            "x = 1", "∞", "∞",
            "y = 0",
            "(-1, 1)", "(-∞, -1) U (1, ∞)",
            "(-∞, -2)", "(-2, 1) U (1, ∞)",
            "-1", "-1.25", "-2", "-10/9",
        ],
    ),
    (
        # U4 FC C: y = ax^3 + bx^2 + cx + d -> y = (-1/4)x^3 + 3x (4 blanks)
        _has("y = ax^3 + bx^2 + cx + d", "point of inflection at the origin"),
        ["-1/4", "0", "3", "0"],
    ),
    (
        # U4 FC C: f(x) = (2x + 10)/(x^2 - 9) full curve-sketching (12 blanks)
        _has("f(x) = (2x + 10)/(x^2 - 9)", "x-intercept at -5"),
        [
            "x = -3, x = 3",
            "∞", "-∞", "-∞", "∞",
            "-10/9", "-5",
            "-9", "-1/9", "-1", "-1",
            "y = 0",
        ],
    ),
    (
        # U4 FC C: vertical asymptotes of 3 rationals (3 blanks)
        _has("y = x/(x^2 + 4x + 3)", "y = (5x - 4)/(x^2 - 6x + 12)", "y = (3x + 2)/(x^2 - 6x + 9)"),
        ["x = -3, x = -1", "none", "x = 3"],
    ),
    (
        # U4 FC C: g(x) = (ax + b)/((x - 1)(x - 4)) -> a=1, b=0
        _has("g(x) = (ax + b)/((x - 1)(x - 4))", "horizontal tangent at the point (2, -1)"),
        ["1", "0"],
    ),
    (
        # U4 FC C: f(x) = ax^3 + bx^2 + c, extremum (2, 11), inflection (1, 5)
        _has("f(x) = ax^3 + bx^2 + c", "local extremum at (2, 11)"),
        ["-3", "9", "-1"],
    ),
    (
        # U4 FC C: horizontal asymptotes x/sqrt(x^2+1) and sqrt(t^2+4t)-sqrt(t^2+t)
        _has("f(x) = x/sqrt(x^2 + 1)", "g(t) = sqrt(t^2 + 4t) - sqrt(t^2 + t)"),
        ["1", "-1", "3/2", "-3/2"],
    ),
    # --- Unit 5 Formative Check A (14524) ------------------------------
    (
        # U5 FC A: radioactive decay P(t) = 100(1.2)^(-t), half-life to 2dp
        _has("P(t) = 100(1.2)^(-t)", "half-life of the substance"),
        ["3.80"],
    ),
    (
        # U5 FC A: N(t) = 2000[30 + t e^(-t/20)], M(t) = (N+1000)^(1/3)
        _has("N(t) = 2000[30 + te^(-t/20)]", "M(t) = (N + 1000)^(1/3)"),
        ["20", "0.12"],
    ),
    (
        # U5 FC A: C(t) = 10(e^(-2t) - e^(-3t)), max time to 2dp -> ln(3/2) = 0.41
        _has("C(t) = 10(e^(-2t) - e^(-3t))", "highest concentration occur"),
        ["0.41"],
    ),
    (
        # U5 FC A: P(t) = 5000e^(0.02t) at t=0, t=7, t=30
        _has("P(t) = 5000e^(0.02t)", "after a month (30 days)"),
        ["5000", "5751", "9111"],
    ),
    (
        # U5 FC A: P(x) = 10^6[1 + (x-1)e^(-0.001x)] max profit -> 1001 (cap 2000), 500 (cap 500)
        _has("P(x) = 10^6[1 + (x - 1)e^(-0.001x)]", "2000 items per month"),
        ["1001", "500"],
    ),
    (
        # U5 FC A: rumour P(t) = 100(e^(-t) - e^(-4t)) -> max=47.25%, t=0.46 h
        _has("P(t) = 100(e^(-t) - e^(-4t))", "spreading the rumour"),
        ["47.25", "0.46"],
    ),
    (
        # U5 FC A: revenue R(x) = 40x^2 e^(-0.4x) + 30 (x in hundred units) -> x=5 -> 500 units
        _has("R(x) = 40x^2 e^(-0.4x) + 30", "maximum capacity of the plant is 800 units"),
        ["500"],
    ),
    (
        # U5 FC A: atmospheric pressure y = 760e^(-0.125x) at 5, 7, 9 km
        _has("y = 760e^(-0.125x)", "5 km:", "9 km:"),
        ["406.8", "316.8", "246.7"],
    ),
    # --- Unit 5 Formative Check B (14526) ------------------------------
    (
        # U5 FC B: f(x) = sin^2 x on [0, pi] -> max 1, min 0
        _has("f(x) = sin^2 x", "Absolute maximum:"),
        ["1", "0"],
    ),
    (
        # U5 FC B: s = 5 cos(2t + pi/4) -> max disp=5, vel=10, acc=20
        _has("s = 5 cos(2t + pi/4)", "Displacement:"),
        ["5", "10", "20"],
    ),
    (
        # U5 FC B: s = sin t / (3 + cos 2t) at t = pi/4 -> v = 5sqrt(2)/18 = 0.3928
        _has("s = sin t/(3 + cos 2t)", "four decimal places"),
        ["0.3928"],
    ),
    (
        # U5 FC B: 3 sin x = sin x + 1 -> pi/6, 5pi/6; cos x - 1 = -cos x -> pi/3, 5pi/3
        _has("3 sin x = sin x + 1", "cos x - 1 = -cos x"),
        ["pi/6", "5pi/6", "pi/3", "5pi/3"],
    ),
    (
        # U5 FC B: 3^-2, 32^(2/5), 27^(-2/3), (2/3)^-2
        _has("3^-2 =", "32^(2/5) =", "27^(-2/3) ="),
        ["1/9", "4", "1/9", "9/4"],
    ),
    (
        # U5 FC B: y = 2x - tan x on (-pi/2, pi/2) local max at x=pi/4 -> y = pi/2 - 1 = 0.57
        _has("y = 2x - tan x", "y-value of the local maximum point"),
        ["0.57"],
    ),
    (
        # U5 FC B: degrees to radians
        _has("Convert the following angles to radian measure", "360 degrees =", "330 degrees ="),
        ["2pi", "pi/4", "-pi/2", "pi/6", "3pi/2", "-2pi/3", "5pi/4", "11pi/6"],
    ),
    (
        # U5 FC B: f(x) = sin x tan x on [0, 2pi] slope=0 at 0, pi, 2pi
        _has("f(x) = sin x tan x", "slope of the tangent to f(x)"),
        ["0", "pi", "2pi"],
    ),
    # --- Unit 6 Formative Check A (14535) ------------------------------
    (
        # U6 FC A: parallelogram ABCD, |PD| = |DA|
        _has("ABCD is a parallelogram, and |PD| = |DA|", "vector equal to AP"),
        ["DC", "CD", "BC", "DA", "none"],
    ),
    (
        # U6 FC A: T/F vector statements
        _has("If two vectors have the same magnitude, then they are equal", "parallel, then they are either equal or opposite"),
        ["false", "true", "false", "false"],
    ),
    (
        # U6 FC A: airplane 400 km/h south, wind from east 100 km/h
        _has("airplane is headed south at speed 400 km/h", "wind from the east blowing at 100 km/h"),
        ["1236.9", "14.0"],
    ),
    (
        # U6 FC A: Maria paddles 7 km/h, current 4 km/h
        _has("Maria can paddle at the rate of 7 km/h", "speed of 4 km/h"),
        ["11", "3"],
    ),
    (
        # U6 FC A: |x| = |y| = 3, |x + y| = sqrt(17) -> |x - y| = sqrt(19)
        _has("|x| = |y| = 3", "|x + y| = sqrt(17)"),
        ["sqrt(19)"],
    ),
    (
        # U6 FC A: PQR triangle midpoints M, N: PM = a, PN = b -> MN = b - a, QR = 2(b - a)
        _has("M is the midpoint of PQ and N is the midpoint of PR", "PM = a and PN = b"),
        ["b - a", "2(b - a)"],
    ),
    (
        # U6 FC A: noncollinear a, b -> collinear pairs
        _has("vectors a and b are noncollinear", "2a, -3a", "5a, -(3/2)b"),
        ["collinear", "not collinear", "not collinear", "collinear"],
    ),
    (
        # U6 FC A: regular hexagon ABCDEF, AB = a, BC = b -> CD = b - a
        _has("ABCDEF is a regular hexagon", "AB = a and BC = b"),
        ["b - a"],
    ),
    (
        # U6 FC A: opposite vectors
        _has("describe the opposite vector", "due north at 400 km/h", "due west at 25 km/h"),
        ["400 km/h due south", "70 km/h southwest", "30 km/h southeast", "25 km/h due east"],
    ),
    (
        # U6 FC A: unit p, q angle 60 -> |2p - q| = sqrt(3)
        _has("vectors p and q are distinct unit vectors", "angle of 60 degrees", "|2p - q|"),
        ["sqrt(3)"],
    ),
    (
        # U6 FC A: triangle ABC vector equivalents
        _has("Given triangle ABC", "BC + CA =", "-BC + BA ="),
        ["BA", "0", "CB", "CA"],
    ),
    (
        # U6 FC A: perpendicular a, b magnitudes
        _has("vectors a and b are perpendicular to each other", "|2a + 3b| ="),
        ["sqrt(|a|^2 + |b|^2)", "sqrt(|a|^2 + |b|^2)", "sqrt(4|a|^2 + 9|b|^2)"],
    ),
    (
        # U6 FC A: length of x = t y is 4|y| -> t = 4 or t = -4
        _has("length of the vector x = t y is 4|y|"),
        ["4", "-4"],
    ),
    (
        # U6 FC A: |u|=8, |v|=10, 60 deg
        _has("|u| = 8 and |v| = 10", "angle between vectors u and v is 60 degrees"),
        ["2sqrt(21)", "70.9", "(u + v)/(2sqrt(61))", "20sqrt(7)"],
    ),
    (
        # U6 FC A: AB tail (-4, 2) head (-1, 3) (7 blanks)
        _has("tail is at (-4, 2) and whose head is at (-1, 3)"),
        ["sqrt(10)", "-3", "1", "0", "-3", "0", "0"],
    ),
    (
        # U6 FC A: parallelogram ABCD, AB = x, DA = y
        _has("ABCD is a parallelogram. If AB = x and DA = y"),
        ["-y", "x", "-x - y", "x - y"],
    ),
    (
        # U6 FC A: PQ - RQ + RS = PS; PS + RQ - RS - PQ = 0
        _has("PQ - RQ + RS =", "PS + RQ - RS - PQ ="),
        ["PS", "0"],
    ),
    (
        # U6 FC A: pentagon PQRST
        _has("PQRST is a pentagon", "PQ + QR + RT =", "PR - (PT - ST) ="),
        ["PT", "PT", "SR"],
    ),
    (
        # U6 FC A: unit x, y angle 90 -> |2x + y| = sqrt(5), 26.6 deg
        _has("vectors x and y are unit vectors", "angle of 90 degrees"),
        ["sqrt(5)", "26.6"],
    ),
    (
        # U6 FC A: unit AB, AC angle 150 -> |AB + AC| = sqrt(2 - sqrt(3))
        _has("AB and AC are two unit vectors", "angle of 150 degrees"),
        ["sqrt(2 - sqrt(3))"],
    ),
    (
        # U6 FC A: unit x, y angle 30 -> |2x + y| = sqrt(5 + 2sqrt(3)), 9.9 deg
        _has("vectors x and y are unit vectors", "angle of 30 degrees"),
        ["sqrt(5 + 2sqrt(3))", "9.9"],
    ),
    (
        # U6 FC A: |v| = 2 scalar multiples (5 blanks)
        _has("vector v has magnitude 2, i.e., |v| = 2"),
        ["2v", "(1/2)v", "-(2/3)v", "-2v", "(1/2)v"],
    ),
    # --- Unit 6 Formative Check B (14536) ------------------------------
    (
        # U6 FC B: identity elements for +, *, vector +, scalar *
        _has("identity element for the operation *", "For scalar multiplication"),
        ["0", "1", "0", "1"],
    ),
    (
        # U6 FC B: prism F origin corner, FG=a, FI=b, FJ=c
        _has("F is the origin corner", "FG = a, FI = b, and FJ = c"),
        ["a + b + c", "a - b", "-a - b + c", "0", "c - b"],
    ),
    (
        # U6 FC B: OP = (-2, 3, 6), B(4, -2, 8), OP = AB -> A = (6, -5, 2)
        _has("OP = (-2, 3, 6)", "B(4, -2, 8)", "OP = AB"),
        ["6", "-5", "2"],
    ),
    (
        # U6 FC B: A(5, b, c) and B(a, -3, 8) same point
        _has("A(5, b, c)", "B(a, -3, 8)"),
        ["5", "-3", "8", "(5, -3, 8)"],
    ),
    (
        # U6 FC B: A(-3, 4), B(3, -4), C(5, 0) -> |AB|=10, |AC|=4sqrt(5), |BC|=2sqrt(5)
        _has("A(-3, 4), B(3, -4), and C(5, 0)"),
        ["10", "4sqrt(5)", "2sqrt(5)"],
    ),
    (
        # U6 FC B: 3(x, 1) - 5(2, 3y) = (11, 33) and -2(x, x+y) - 3(6, y) = (6, 4)
        _has("3(x, 1) - 5(2, 3y) = (11, 33)", "-2(x, x + y) - 3(6, y) = (6, 4)"),
        ["7", "-2", "-12", "4"],
    ),
    (
        # U6 FC B: parallelogram OA=(3,2,-6), OB=(-6,6,-2)
        _has("OA = (3, 2, -6)", "OB = (-6, 6, -2)"),
        ["(-3, 8, -8)", "(9, -4, -4)", "84.4", "95.6"],
    ),
    (
        # U6 FC B: a=i+j-k, b=2i-j+3k, c=2i+13k -> |(0,7,0)| = 7
        _has("a = i + j - k, b = 2i - j + 3k, and c = 2i + 13k"),
        ["7"],
    ),
    (
        # U6 FC B: 2x + 3y = a and -x + 5y = 6b
        _has("2x + 3y = a and -x + 5y = 6b"),
        ["(5a - 18b)/13", "(a + 12b)/13"],
    ),
    (
        # U6 FC B: ABCDEFGH prism vector addition -> EC, 0
        _has("EG + GH + HD + DC:", "EG + GD + DE:"),
        ["EC", "0"],
    ),
    (
        # U6 FC B: P(-2, 4, -7) box corners (14 blanks)
        _has("point P(-2, 4, -7) is located in R^3", "rectangle DEPF"),
        [
            "(-2, 0, 0)",
            "(-2, 4, 0)",
            "(0, 4, 0)",
            "(0, 0, -7)",
            "(0, 4, -7)",
            "(-2, 0, -7)",
            "(-2, 0, 0)",
            "(-2, 4, 0)",
            "(0, 4, 0)",
            "(0, 0, -7)",
            "(0, 4, -7)",
            "(-2, 0, -7)",
            "7",
            "4",
        ],
    ),
    (
        # U6 FC B: plane containing M(1,0,3), N(4,0,6), P(7,0,9) -> y = 0
        _has("M(1, 0, 3), N(4, 0, 6), and P(7, 0, 9)"),
        ["0"],
    ),
    (
        # U6 FC B: single vectors a, b, c
        _has("2(-2, 3) + (2, 1)", "-3(4, -9) - 9(2, 3)"),
        ["(-2, 7)", "(-30, 0)", "(1, 11)"],
    ),
    (
        # U6 FC B: Triangle ABC A(2,3), B(6,6), C(-4,11)
        _has("A(2, 3), B(6, 6), and C(-4, 11)"),
        ["5", "10", "5sqrt(5)"],
    ),
    (
        # U6 FC B: x=(1,4,-1), y=(1,3,-2), z=(-2,1,0)
        _has("x = (1, 4, -1), y = (1, 3, -2), and z = (-2, 1, 0)"),
        ["(1, -3, 3)", "(-7, -16, 8)", "(-13/2, 2, 3/2)", "(2, 30, -13)"],
    ),
    (
        # U6 FC B: plane A(3,2,-4), B(1,1,-4), C(0,1,-4) -> z = -4
        _has("A(3, 2, -4), B(1, 1, -4), and C(0, 1, -4)"),
        ["-4"],
    ),
    (
        # U6 FC B: Parallelogram OBCA OA=(6,3), OB=(11,-6)
        _has("OA = (6, 3) and OB = (11, -6)"),
        ["(17, -3)", "(-5, 9)", "(6, 3)"],
    ),
    (
        # U6 FC B: a i + 5 j = (-3, b)
        _has("a i + 5 j = (-3, b)"),
        ["-3", "5", "sqrt(34)"],
    ),
    (
        # U6 FC B: OA=(-3,4,12), OB=(2,2,-1)
        _has("OA = (-3, 4, 12) and OB = (2, 2, -1)"),
        ["(-1, 6, 11)", "13", "3", "sqrt(158)", "(5, -2, -13)", "3sqrt(22)"],
    ),
    (
        # U6 FC B: OB = 3i + 4j - 4k -> (3, 4, -4), sqrt(41)
        _has("OB = 3i + 4j - 4k"),
        ["(3, 4, -4)", "sqrt(41)"],
    ),
    (
        # U6 FC B: a=3i-4j+k, b=-2i+3j-k in terms of i, j, k
        _has("a = 3i - 4j + k and b = -2i + 3j - k"),
        ["12i - 17j + 5k", "-7i + 11j - 4k", "-6i + 13j - 7k"],
    ),
    (
        # U6 FC B: component form vectors OA..OF for question 10 points
        _has("A(1, 2, 3), B(-2, 1, 1), C(1, -2, 1), D(1, 1, 1), E(1, -1, 1), and F(1, -1, -1)"),
        ["(1, 2, 3)", "(-2, 1, 1)", "(1, -2, 1)", "(1, 1, 1)", "(1, -1, 1)", "(1, -1, -1)"],
    ),
    (
        # U6 FC B: cube along +x, +y, +z of side length 4 (11 blanks)
        _has("cube has a side length of 4", "starts at (4, 4, 4)"),
        [
            "(0, 0, 0)",
            "(4, 0, 0)",
            "(0, 4, 0)",
            "(0, 0, 4)",
            "(4, 4, 0)",
            "(4, 0, 4)",
            "(0, 4, 4)",
            "(4, 4, 4)",
            "(-4, -4, -4)",
            "(-4, 0, -4)",
            "(4, 4, 0)",
        ],
    ),
    (
        # U6 FC B: unit vector opposite to PQ for OP=(11,19), OQ=(2,-21)
        _has("OP = (11, 19) and OQ = (2, -21)"),
        ["9/41", "40/41"],
    ),
    (
        # U6 FC B: x=2i-j, y=-i+5j
        _has("x = 2i - j and y = -i + 5j", "3x - y ="),
        ["7i - 8j", "3i - 51j", "-29i + 28j"],
    ),
    (
        # U6 FC B: A(-2,3,-5), B(6,7,3) -> AB=(8,4,8), |AB|=12, unit BA=(-2/3,-1/3,-2/3)
        _has("A(-2, 3, -5) and B(6, 7, 3)"),
        ["(8, 4, 8)", "12", "(-2/3, -1/3, -2/3)"],
    ),
    (
        # U6 FC B: 3(a - 2b - 5c) - 3(2a - 4b + 2c) - (a - 3b + 3c)
        _has("3(a - 2b - 5c) - 3(2a - 4b + 2c) - (a - 3b + 3c)"),
        ["-4a + 9b - 24c"],
    ),
    (
        # U6 FC B: P(2, a - c, a) = Q(2, 6, 11)
        _has("P(2, a - c, a) and Q(2, 6, 11)"),
        ["11", "5", "yes"],
    ),
    (
        # U6 FC B: A(-1, 3), B(2, 5) -> AB, BA, |OA|, |OB|, |AB|, |BA|
        _has("For A(-1, 3) and B(2, 5)"),
        ["(3, 2)", "(-3, -2)", "sqrt(10)", "sqrt(29)", "sqrt(13)", "sqrt(13)"],
    ),
    (
        # U6 FC B: a=(-60, 11), b=(-40, -9)
        _has("a = (-60, 11) and b = (-40, -9)"),
        ["61", "41", "2sqrt(2501)", "20sqrt(2)"],
    ),
    (
        # U6 FC B: equidistant from A(2, -1, 3) and B(1, 2, -3)
        _has("equidistant from A(2, -1, 3) and B(1, 2, -3)"),
        ["x - 3y + 6z = 0"],
    ),
    (
        # U6 FC B: x = 2i - j, y = -i + 5j magnitudes
        _has("x = 2i - j and y = -i + 5j", "|2x - 3y| ="),
        ["sqrt(17)", "3sqrt(5)", "13sqrt(2)", "13sqrt(2)"],
    ),
    (
        # U6 FC B: Rectangle ABCD A(2, 3), B(-6, 9), D(8, 11) -> C(0, 17)
        _has("A(2, 3), B(-6, 9), C(x, y), and D(8, 11)"),
        ["0", "17"],
    ),
    (
        # U6 FC B: OA = (-1, 2, 4) -> -i + 2j + 4k, sqrt(21)
        _has("OA = (-1, 2, 4)"),
        ["-i + 2j + 4k", "sqrt(21)"],
    ),
    (
        # U6 FC B: fourth vertex of parallelogram A(-1, 2), B(7, -2), C(2, 8)
        _has("A(-1, 2), B(7, -2), and C(2, 8)"),
        ["(4, -8)", "(-6, 12)", "(10, 4)"],
    ),
    (
        # U6 FC B: unit vector opposite M(2,3,5) to N(8,1,2)
        _has("M(2, 3, 5) to N(8, 1, 2)"),
        ["(-6/7, 2/7, 3/7)"],
    ),
    (
        # U6 FC B: 2x + y - 2z = 0, x=(-1,b,c), y=(a,-2,c), z=(-a,6,c)
        _has("2x + y - 2z = 0", "x = (-1, b, c)"),
        ["2/3", "7", "0"],
    ),
    (
        # U6 FC B: x=2a-3b-4c, y=-2a+3b+3c, z=2a-3b+5c
        _has("x = 2a - 3b - 4c", "y = -2a + 3b + 3c"),
        ["20a - 30b + 8c", "2a - 3b - 3c"],
    ),
    (
        # U6 FC B: P(x, y, 0), Q(x, 0, z), R(0, y, z) planes
        _has("P(x, y, 0), Q(x, 0, z), and R(0, y, z)"),
        ["xy-plane", "xz-plane", "yz-plane"],
    ),
    (
        # U6 FC B: X(-1, 2, 6), Y(5, 5, 12) -> YX=(-6, -3, -6), unit=(-2/3, -1/3, -2/3)
        _has("X(-1, 2, 6) and Y(5, 5, 12)"),
        ["(-6, -3, -6)", "(-2/3, -1/3, -2/3)"],
    ),
    (
        # U6 FC B: trapezoid TXYZ, TX = 2 ZY -> TO = (1/3)TX + (2/3)TZ
        _has("trapezoid TXYZ", "TX = 2 ZY"),
        ["(1/3)TX + (2/3)TZ"],
    ),
    (
        # U6 FC B: parallelepiped OA=(-2,2,5), OB=(0,4,1), OC=(0,5,-1)
        _has("OA = (-2, 2, 5), OB = (0, 4, 1), and OC = (0, 5, -1)"),
        [
            "(0, 0, 0)",
            "(-2, 2, 5)",
            "(0, 4, 1)",
            "(0, 5, -1)",
            "(-2, 6, 6)",
            "(-2, 7, 4)",
            "(0, 9, 0)",
            "(-2, 11, 5)",
        ],
    ),
    (
        # U6 FC B: right triangle A(1,-1,1), B(2,2,2), C(4,-2,1); collinear P,Q,R
        _has("A(1, -1, 1), B(2, 2, 2), and C(4, -2, 1)", "P(1, 2, 3), Q(2, 4, 6)"),
        ["yes", "yes"],
    ),
    (
        # U6 FC B: grid vectors AB, CD, EF, GH + magnitudes
        _has("A(-8, 2) to B(-4, 4)", "G(1, -2) to H(6, -2)"),
        [
            "(4, 2)",
            "(2, 4)",
            "(-6, 4)",
            "(5, 0)",
            "2sqrt(5)",
            "2sqrt(5)",
            "2sqrt(13)",
            "5",
        ],
    ),
    (
        # U6 FC B/C: p = 2i - j + k and q = -i - j + k in unit vector form
        _has("p = 2i - j + k and q = -i - j + k"),
        ["i - 2j + 2k", "3i", "9i + 3j - 3k", "-9i - 3j + 3k"],
    ),
    (
        # U6 FC B: OP = (5, -10, -10) -> |OP| = 15
        _has("OP = (5, -10, -10)"),
        ["15"],
    ),
    (
        # U6 FC B/C: Triangle ABC A(-1,1,1), B(2,0,3), C(3,3,-4)
        _has("A(-1, 1, 1), B(2, 0, 3), and C(3, 3, -4)"),
        ["12.5", "18.1", "(6, 2, -2)"],
    ),
    (
        # U6 FC B: calculate a, b, c system (6 blanks)
        _has("2(a, b, 4) + (1/2)(6, 8, c)", "2(a, a, (1/2)a)"),
        ["-3", "29/2", "10", "4", "5", "-10"],
    ),
    (
        # U6 FC B: 3x - 2y = a, 5x - 3y = b and (2,-1,c)+(a,b,1)-3(2,a,4)=(-3,1,2c)
        _has("3x - 2y = a and 5x - 3y = b", "(2, -1, c) + (a, b, 1)"),
        ["-3a + 2b", "-5a + 3b", "1", "5", "-11"],
    ),
    (
        # U6 FC B: OA = 3i - 4j -> |OA| = 5
        _has("OA = 3i - 4j", "calculate |OA|"),
        ["5"],
    ),
    (
        # U6 FC B: parallelogram OPQR, OP = (-7, 24), OR = (-8, -1)
        _has("OP = (-7, 24) and OR = (-8, -1)"),
        ["80.9", "35.4"],
    ),
    (
        # U6 FC B: A(-2, -6, 3) and B(3, -4, 12)
        _has("A(-2, -6, 3) and B(3, -4, 12)"),
        ["7", "13", "(5, 2, 9)", "sqrt(110)", "(-5, -2, -9)", "sqrt(110)"],
    ),
    (
        # U6 FC B/C: X(-2, 1, 2) and Y(-4, 4, 8)
        _has("X(-2, 1, 2) and Y(-4, 4, 8)"),
        ["(-2, 3, 6)", "7", "(-2/7, 3/7, 6/7)"],
    ),
    # --- Unit 6 Formative Check C (14537) ------------------------------
    (
        # U6 FC C: a=(5,9,14) = 2b + 3c; (-13,36,23) = 11b + 3c
        _has("a = (5, 9, 14)", "b = (-2, 3, 1) and c = (3, 1, 4)"),
        ["2b + 3c", "11", "3"],
    ),
    (
        # U6 FC C: (-3, 14, 7) = 3(-1, 3, 4) - 5(0, -1, 1)
        _has("(-3, 14, 7) = ", "(-1, 3, 4) + ", "(0, -1, 1)"),
        ["3", "-5"],
    ),
    (
        # U6 FC C: 2(a, 3, c) + 3(c, 7, c) = (5, b + c, 15)
        _has("2(a, 3, c) + 3(c, 7, c) = (5, b + c, 15)"),
        ["-2", "24", "3"],
    ),
    (
        # U6 FC C: m(2, 3) + n(3, 5) = (323, 795)
        _has("m(2, 3) + n(3, 5) = (323, 795)"),
        ["-770", "621"],
    ),
    (
        # U6 FC C: point on x-axis equidistant from A(-2, 1, 3) and B(4, -1, 3)
        _has("A(-2, 1, 3) and B(4, -1, 3)", "point on the x-axis equidistant"),
        ["(1, 0, 0)"],
    ),
    (
        # U6 FC C: vectors a and b span R^2, (m - 2)a = (n + 3)b
        _has("vectors a and b span R^2", "(m - 2)a = (n + 3)b"),
        ["2", "-3"],
    ),
    (
        # U6 FC C: (m^2 + 2m - 3)a + (m^2 + m - 6)b = 0 -> m = -3
        _has("(m^2 + 2m - 3)a + (m^2 + m - 6)b = 0"),
        ["-3"],
    ),
    (
        # U6 FC C: a=i-2j, b=j-3k, c=i-3j+2k in component form
        _has("a = i - 2j, b = j - 3k, and c = i - 3j + 2k"),
        ["(14, -43, 40)", "(-7, 21, -14)"],
    ),
    (
        # U6 FC C: |a| = 3, |b| = 5, |a + b| = 7 -> |a - b| = sqrt(19)
        _has("|a| = 3, |b| = 5, and |a + b| = 7"),
        ["sqrt(19)"],
    ),
    (
        # U6 FC C: m = 2i - k and n = -2i + j + 2k
        _has("m = 2i - k and n = -2i + j + 2k"),
        ["sqrt(26)", "sqrt(2)", "sqrt(29)", "5sqrt(5)"],
    ),
    (
        # U6 FC C: a=(1,12,-29), b=(3,1,4), c=(1,2,-3) -> a = -2b + 7c
        _has("a = (1, 12, -29)", "b = (3, 1, 4) and c = (1, 2, -3)"),
        ["-2b + 7c"],
    ),
    (
        # U6 FC C: p(-2, 3) + q(3, -1) = (13, -9)
        _has("p(-2, 3) + q(3, -1) = (13, -9)"),
        ["-2", "3"],
    ),
    (
        # U6 FC C: A(-1,3,4), B(-2,3,-1), C(-5,6,x) coplanar with origin -> x = -7
        _has("A(-1, 3, 4), B(-2, 3, -1), and C(-5, 6, x)"),
        ["-7"],
    ),
    (
        # U6 FC C: A(3,0,4), B(1,2,5), C(2,1,3) -> cos(angle ABC) = sqrt(6)/3
        _has("A(3, 0, 4), B(1, 2, 5), and C(2, 1, 3)"),
        ["sqrt(6)/3"],
    ),
    (
        # U6 FC C: x + y = -i + 2j + 5k and x - y = 3i + 6j - 7k
        _has("x + y = -i + 2j + 5k", "x - y = 3i + 6j - 7k"),
        ["i + 4j - k", "-2i - 2j + 6k"],
    ),
    (
        # U6 FC C: p=(-11,7), q=(-3,1), r=(-1,2) linear combinations
        _has("p = (-11, 7), q = (-3, 1), and r = (-1, 2)"),
        ["3q + 2r", "(1/3)p - (2/3)r", "(1/2)p - (3/2)q"],
    ),
    # --- Unit 7 Formative Check A (14542) ------------------------------
    (
        # U7 FC A: a.b = -12 -> Obtuse
        _has("satisfy a.b = -12", "angle between them must be"),
        {"type": "choice", "choice": "Obtuse"},
    ),
    (
        # U7 FC A: (a + b).(a - b) = |a|^2 - |b|^2
        _has("(a + b).(a - b) simplifies to"),
        {"type": "choice", "choice": "|a|^2 - |b|^2"},
    ),
    (
        # U7 FC A: perpendicular pair -> (2, -1) and (1, 2)
        _has("Which pair of vectors is perpendicular?"),
        {"type": "choice", "choice": "(2, -1) and (1, 2)"},
    ),
    (
        # U7 FC A: angle between u=(1,0,-1) and v=(0,1,1) -> 120 degrees
        _has("angle between u = (1, 0, -1) and v = (0, 1, 1)"),
        {"type": "choice", "choice": "120 degrees"},
    ),
    (
        # U7 FC A: p=(2,k,1) perp to q=(1,-1,3) -> k = 5
        _has("p = (2, k, 1) and q = (1, -1, 3) perpendicular"),
        ["5"],
    ),
    (
        # U7 FC A: distributive property a.(b + c) = a.b + a.c
        _has("a.(b + c) = a.b + a.c"),
        {"type": "choice", "choice": "Correct - the distributive property of the dot product"},
    ),
    (
        # U7 FC A: a=(-1,2,4), b=(3,4,3) -> a.b = 17
        _has("a = (-1, 2, 4) and b = (3, 4, 3)"),
        ["17"],
    ),
    (
        # U7 FC A: |a|=3, |b|=5, 120 deg -> -7.5
        _has("|a| = 3, |b| = 5", "angle between them (tail to tail) is 120 degrees"),
        {"type": "choice", "choice": "-7.5"},
    ),
    # --- Unit 7 Formative Check B (14543) ------------------------------
    (
        # U7 FC B: scalar projection of a=(3,-4) onto b=(1,1) -> -sqrt(2)/2
        _has("scalar projection of a = (3, -4) onto b = (1, 1)"),
        {"type": "choice", "choice": "-sqrt(2)/2"},
    ),
    (
        # U7 FC B: cross product (2,-1,3) x (0,4,-2) = (-10, 4, 8)
        _has("u = (2, -1, 3) and v = (0, 4, -2)", "cross product"),
        {"type": "choice", "choice": "(-10, 4, 8)"},
    ),
    (
        # U7 FC B: vector projection of a=(3,-4) onto b=(1,1) -> (-1/2, -1/2)
        _has("vector projection of a = (3, -4) onto b = (1, 1)"),
        {"type": "choice", "choice": "(-1/2, -1/2)"},
    ),
    (
        # U7 FC B: i x j = k
        _has("value of i x j is"),
        {"type": "choice", "choice": "k"},
    ),
    (
        # U7 FC B: right-hand rule from a toward b -> a x b
        _has("fingers curl from a toward b"),
        {"type": "choice", "choice": "a x b"},
    ),
    (
        # U7 FC B: a x b = (2, -3, 5) -> b x a = (-2, 3, -5)
        _has("a x b = (2, -3, 5)", "b x a equals"),
        {"type": "choice", "choice": "(-2, 3, -5)"},
    ),
    (
        # U7 FC B: |a|=4, |b|=7, 30 deg -> |a x b| = 14
        _has("|a| = 4, |b| = 7", "30 degrees", "|a x b|"),
        ["14"],
    ),
    (
        # U7 FC B: angle between a=(2,3) and b=(5,-1) -> 68 degrees
        _has("a = (2, 3) and b = (5, -1)", "nearest degree"),
        {"type": "choice", "choice": "68 degrees"},
    ),
    # --- Unit 7 Formative Check C (14544) ------------------------------
    (
        # U7 FC C: area of triangle with same two sides as C1 -> 3*sqrt(5) ≈ 6.71
        _has("area of the triangle with the same two sides as C1"),
        {"type": "choice", "choice": "3*sqrt(5) ≈ 6.71"},
    ),
    (
        # U7 FC C: work is -5 J -> opposes the displacement overall
        _has("work is -5 J", "This means"),
        {"type": "choice", "choice": "The force opposes the displacement overall"},
    ),
    (
        # U7 FC C: nonzero p, q with p x q = 0 -> parallel
        _has("Nonzero vectors p and q satisfy p × q = 0"),
        {"type": "choice", "choice": "p and q are parallel"},
    ),
    (
        # U7 FC C: F=(6,2,-1), d=(3,-4,2) -> W = 8
        _has("F = (6, 2, -1) N", "d = (3, -4, 2) m", "work done"),
        ["8"],
    ),
    (
        # U7 FC C: parallelogram area u=(2,-1,3), v=(0,4,-2) -> sqrt(180) ≈ 13.42
        _has("u = (2, -1, 3) and v = (0, 4, -2)", "area of the parallelogram"),
        {"type": "choice", "choice": "sqrt(180) ≈ 13.42"},
    ),
    (
        # U7 FC C: r=(0.5,0,0), F=(0,20,0) -> (0, 0, 10) N·m
        _has("r = (0.5, 0, 0) m", "F = (0, 20, 0) N"),
        {"type": "choice", "choice": "(0, 0, 10) N·m"},
    ),
    (
        # U7 FC C: perpendicular to both u and v -> cross product
        _has("perpendicular to both u = (1, 2, 0) and v = (0, 1, 3)"),
        {"type": "choice", "choice": "The cross product — it returns a vector perpendicular to both"},
    ),
    (
        # U7 FC C: (a + b) × (a - b) = -2(a × b)
        _has("(a + b) × (a - b) equals"),
        {"type": "choice", "choice": "-2(a × b)"},
    ),
    # --- Unit 8 Formative Check A (14549) ------------------------------
    (
        # U8 FC A: equilibrant of a force system
        _has("equilibrant of a force system is"),
        {"type": "choice", "choice": "Equal in magnitude and opposite in direction to the resultant"},
    ),
    (
        # U8 FC A: ferry 1.5 km wide at 12 km/h, current 4 km/h -> 0.5 km downstream after 7.5 min
        _has("ferry crosses a 1.5 km wide river", "current is 4 km/h"),
        {"type": "choice", "choice": "0.5 km downstream after 7.5 min"},
    ),
    (
        # U8 FC A: 6 N east, 8 N north -> 10 N
        _has("6 N due east and 8 N due north"),
        {"type": "choice", "choice": "10 N"},
    ),
    (
        # U8 FC A: 4 kN, 7 kN, 12 kN equilibrium -> No triangle inequality
        _has("4 kN, 7 kN, and 12 kN", "equilibrium"),
        {"type": "choice", "choice": "No — 4 + 7 < 12 violates the triangle inequality"},
    ),
    (
        # U8 FC A: 8 kg crate (78.4 N) on 25 deg ramp -> 78.4*sin(25) ≈ 33.1 N
        _has("8 kg crate (weight 78.4 N) rests on a 25"),
        {"type": "choice", "choice": "≈ 33.1 N"},
    ),
    (
        # U8 FC A: boat 15 km/h, river 5 km/h -> arcsin(5/15) = 19.47 deg
        _has("boat moving at 15 km/h in still water", "river flowing at 5 km/h"),
        ["19.47"],
    ),
    (
        # U8 FC A: 100 N sign, two cables at 60 deg -> 100/(2*sin(60)) = 57.74 N
        _has("100 N sign hangs from two identical cables", "60"),
        ["57.74"],
    ),
    (
        # U8 FC A: plane west 300 km/h, wind from north 40 km/h -> 302.7 km/h, 7.6 south of west
        _has("plane flies due west at 300 km/h", "wind blows from the north at 40 km/h"),
        {"type": "choice", "choice": "≈ 302.7 km/h, 7.6° south of west"},
    ),
]


def lookup(prompt: str, num_blanks: int, slug: str | None = None) -> dict:
    """Return a solver-compatible result from the bank, or a miss.

    Entry values may be:
      - list[str]: fill-in-the-blank / numeric values
      - dict: typed response such as {"type": "choice", "choice": "..."},
        {"type": "multi", "choices": [...]}, {"type": "essay", "text": "..."},
        {"type": "matching", "pairs": {...}}, or {"type": "blanks", "answers": [...]}.
    """
    for pred, entry in ENTRIES:
        try:
            matched = pred(prompt)
        except Exception:
            matched = False
        if not matched:
            continue
        if isinstance(entry, dict):
            etype = entry.get("type", "blanks")
            if etype == "blanks":
                ans = list(entry.get("answers") or [])
                if len(ans) != num_blanks:
                    return {
                        "ok": False,
                        "pattern": "answer_bank",
                        "answers": None,
                        "reason": f"blank_mismatch({len(ans)} vs {num_blanks})",
                    }
                return {
                    "ok": True,
                    "pattern": "answer_bank",
                    "type": "blanks",
                    "answers": ans,
                    "reason": None,
                }
            return {
                "ok": True,
                "pattern": "answer_bank",
                "type": etype,
                "answers": entry,
                "reason": None,
            }
        if len(entry) != num_blanks:
            return {
                "ok": False,
                "pattern": "answer_bank",
                "answers": None,
                "reason": f"blank_mismatch({len(entry)} vs {num_blanks})",
            }
        return {
            "ok": True,
            "pattern": "answer_bank",
            "type": "blanks",
            "answers": list(entry),
            "reason": None,
        }
    return {"ok": False, "pattern": None, "answers": None, "reason": "not_in_bank"}
