"""SymPy-based solver for MCV4U Formative Check calculus prompts.

Handles the question patterns seen so far:
  1. "product of each radical expression and its corresponding conjugate"
  2. "slope of the line through each pair of points"
  3. "slope of the secant" between x = a and x = b for f(x) = ...
  4. "slope of a line perpendicular to ..."
  5. "slope of the tangent" / "slope of the graph" at (x,y) or x=k, for f(x)=... or y=...
  6. "circulation / rate ..." — same as (5), slope of tangent at given t
  7. Piecewise f(x) = {branch1 if cond1; branch2 if cond2}

Usage:
    from solve_formative import solve_question
    result = solve_question(prompt_text, num_blanks)
    # result = {"ok": True, "answers": ["3", "-5/3", ...], "pattern": "slope_tangent"}
    # or {"ok": False, "reason": "..."}
"""
import re
from sympy import (symbols, sympify, diff, simplify, Rational, sqrt, nsimplify,
                   Symbol, Poly, Expr, S, oo)

x = symbols('x')
t = symbols('t')
p = symbols('p')

# ---------- text normalisation ----------

UNI = {
    '²': '**2', '³': '**3', '⁴': '**4', '⁵': '**5', '⁶': '**6',
    '⁷': '**7', '⁸': '**8', '⁹': '**9', '⁰': '**0', '¹': '**1',
    '×': '*', '·': '*', '÷': '/', '−': '-', '–': '-', '—': '-',
    '≤': '<=', '≥': '>=', '≠': '!=',
}

def unicodify(s: str) -> str:
    for k, v in UNI.items():
        s = s.replace(k, v)
    # √(expr) -> sqrt(expr); √5 -> sqrt(5); √ x -> sqrt(x)
    s = re.sub(r'√\s*\(([^)]+)\)', r'sqrt(\1)', s)
    s = re.sub(r'√\s*([A-Za-z0-9.]+)', r'sqrt(\1)', s)
    return s

def to_sympy_str(s: str) -> str:
    """Prepare an expression string for sympify. Convert '3√5' -> '3*sqrt(5)' etc."""
    s = unicodify(s).strip()
    # Add implicit * between number and sqrt or letter
    s = re.sub(r'(\d)(sqrt)', r'\1*\2', s)
    s = re.sub(r'(\d)([a-zA-Z(])', r'\1*\2', s)
    s = re.sub(r'\)([a-zA-Z0-9(])', r')*\1', s)
    return s

def parse_num(s: str):
    """Parse a numeric value as a SymPy Rational (handles fractions and decimals)."""
    s = unicodify(s).strip()
    s = s.replace('--', '')  # just in case
    try:
        return nsimplify(sympify(s), rational=True)
    except Exception:
        return None

def format_answer(val) -> str:
    """Format a SymPy value as a clean answer string: 'a/b', integer, or decimal fallback."""
    try:
        r = nsimplify(val, rational=True)
        if r.is_Rational:
            if r.q == 1:
                return str(r.p)
            return f"{r.p}/{r.q}"
        # non-rational: try to simplify radicals; else fall back to decimal
        s = simplify(r)
        if s.is_Rational:
            return f"{s.p}/{s.q}" if s.q != 1 else str(s.p)
        return str(s)
    except Exception:
        return str(val)

# ---------- subpart splitting ----------

SUBPART_RE = re.compile(r'(?:^|\n)\s*([a-h])\.\s+(.*?)(?=(?:\n\s*[a-h]\.)|(?:\nQuestion Blank)|(?:\nAnswer\s*$)|\Z)',
                        re.DOTALL)

def split_sub_parts(prompt: str):
    """Return list of (label, body) for 'a. ... b. ...' sub-parts.
    If no sub-parts detected, returns [('', prompt)]."""
    parts = SUBPART_RE.findall(prompt)
    if parts:
        return [(lbl, body.strip()) for lbl, body in parts]
    return [('', prompt)]

# ---------- pattern solvers ----------

def solve_conjugate_products(parts):
    """For a two-term expression a ± b, product with conjugate = a² - b².
    Split on the LAST top-level + or - (depth 0), square each half, subtract."""
    out = []
    for lbl, body in parts:
        body = re.split(r'Question Blank', body)[0].strip()
        s = unicodify(body).strip()
        # Find the rightmost top-level '+' or '-' (depth 0) that is NOT a unary sign
        depth = 0
        split_i = -1
        for i, ch in enumerate(s):
            if ch == '(': depth += 1
            elif ch == ')': depth -= 1
            elif ch in '+-' and depth == 0 and i > 0:
                # Skip if preceded by operator or whitespace-after-operator → unary
                prev = s[i-1]
                if prev in '+-*/(' or (prev == ' ' and i >= 2 and s[i-2] in '+-*/('):
                    continue
                split_i = i
        if split_i < 0:
            out.append("ERR:no_split")
            continue
        try:
            left = sympify(to_sympy_str(s[:split_i].strip()))
            right = sympify(to_sympy_str(s[split_i+1:].strip()))
            product = simplify(left**2 - right**2)
            out.append(format_answer(product))
        except Exception as ex:
            out.append(f"ERR:{ex}")
    return out

def solve_slope_between_points(parts):
    """(x1,y1),(x2,y2) -> (y2-y1)/(x2-x1)"""
    out = []
    pt_re = re.compile(r'\(\s*([^,()]+?)\s*,\s*([^,()]+?)\s*\)\s*,\s*\(\s*([^,()]+?)\s*,\s*([^,()]+?)\s*\)')
    for lbl, body in parts:
        m = pt_re.search(body)
        if not m:
            out.append(f"ERR:no_point_pair")
            continue
        try:
            x1,y1,x2,y2 = [parse_num(g) for g in m.groups()]
            slope = (y2 - y1) / (x2 - x1)
            out.append(format_answer(slope))
        except Exception as ex:
            out.append(f"ERR:{ex}")
    return out

def solve_perpendicular(parts):
    """Given line y=mx+b or Ax+By+C=0, return -1/m."""
    out = []
    for lbl, body in parts:
        body = re.split(r'Question Blank', body)[0].strip()
        s = unicodify(body)
        # Case 1: y = mx + b  or  f(x) = mx + b
        m1 = re.search(r'(?:y|f\s*\(\s*x\s*\))\s*=\s*([^=\n]+)', s)
        if m1:
            rhs = to_sympy_str(m1.group(1))
            try:
                e = sympify(rhs)
                m = diff(e, x)  # for a line y = mx+b, diff gives slope
                if m == 0:
                    out.append("undefined")
                else:
                    out.append(format_answer(-1/m))
                continue
            except Exception as ex:
                pass
        # Case 2: Ax + By + C = 0
        m2 = re.search(r'([+-]?\s*\d*\.?\d*)\s*x\s*([+-]\s*\d*\.?\d*)\s*y\s*([+-]\s*\d+\.?\d*)?\s*=\s*0', s)
        if m2:
            try:
                a_str = (m2.group(1) or '1').replace(' ','')
                b_str = m2.group(2).replace(' ','')
                a = parse_num(a_str if a_str not in ('','+','-') else a_str+'1')
                b = parse_num(b_str if b_str not in ('','+','-') else b_str+'1')
                slope = -a/b  # slope of line
                perp = -1/slope
                out.append(format_answer(perp))
                continue
            except Exception as ex:
                out.append(f"ERR:{ex}")
                continue
        out.append("ERR:no_line_eq")
    return out

def extract_function(body: str):
    """Pull RHS of 'y = ...', 'f(x) = ...', 'C(t) = ...', 'D(p) = ...' (returns sympy expr and the variable).
    Stops on comma, period-space, newline, or the words 'at' / 'for' / 'when'."""
    s = unicodify(body)
    for var_name, sym in [('x', x), ('t', t), ('p', p)]:
        pat = re.compile(
            rf'(?:y|f\s*\(\s*{var_name}\s*\)|[A-Z]\s*\(\s*{var_name}\s*\))\s*=\s*(.+?)'
            rf'(?:,|\.(?:\s|$)|\n|;|\s+at\s+|\s+for\s+|\s+when\s+|\s+where\s+|\s+and\s+|$)',
            re.IGNORECASE,
        )
        m = pat.search(s)
        if m:
            raw = m.group(1).strip()
            # Clean trailing partial tokens
            raw = raw.rstrip('.,;')
            try:
                e = sympify(to_sympy_str(raw))
                return e, sym, var_name
            except Exception:
                continue
    return None, None, None

def solve_tangent_at(parts):
    """Compute f'(x_eval) for each sub-part."""
    out = []
    for lbl, body in parts:
        body = re.split(r'Question Blank', body)[0].strip()
        e, sym, vname = extract_function(body)
        if e is None:
            out.append("ERR:no_function")
            continue
        xv = None
        # Point form "(a, b)" — pick first coord as x
        m_pt = re.search(r'\(\s*(-?\d[^,()]*)\s*,\s*-?\d[^,()]*\s*\)', body)
        if m_pt:
            xv = parse_num(m_pt.group(1))
        if xv is None:
            # Look for "<var> = <num>" anywhere; filter out "f(var) = ..." patterns
            for m in re.finditer(rf'(?<![a-zA-Z(]){vname}\s*=\s*(-?\d+(?:\.\d+)?(?:/\d+)?)', body):
                xv = parse_num(m.group(1))
                if xv is not None:
                    break
        if xv is None:
            out.append("ERR:no_eval_point")
            continue
        try:
            d = diff(e, sym)
            val = d.subs(sym, xv)
            out.append(format_answer(val))
        except Exception as ex:
            out.append(f"ERR:{ex}")
    return out

def solve_tangent_parallel_line(parts, prompt):
    """Find (x, y) on curve f(x) = ... where tangent is parallel to line y = mx + b (or y = mx).
    Returns [x_val, y_val] — matches the typical 2-blank layout."""
    e, sym, vname = extract_function(prompt)
    if e is None:
        return ["ERR:no_function" for _ in parts]
    # Extract line slope
    m_line = re.search(r'parallel to the line\s+y\s*=\s*([^.\n]+?)(?:[.\n]|$)', prompt)
    if not m_line:
        return ["ERR:no_line" for _ in parts]
    try:
        line_expr = sympify(to_sympy_str(m_line.group(1).strip()))
        slope = diff(line_expr, sym)
    except Exception as ex:
        return [f"ERR:{ex}" for _ in parts]
    try:
        d = diff(e, sym)
        from sympy import solve as sym_solve
        x_sols = sym_solve(d - slope, sym)
        if not x_sols:
            return ["ERR:no_solution" for _ in parts]
        xv = x_sols[0]
        yv = e.subs(sym, xv)
        return [format_answer(xv), format_answer(yv)]
    except Exception as ex:
        return [f"ERR:{ex}" for _ in parts]

def solve_secant(parts, prompt):
    """Secant slope on f(x) between x=a and x=b."""
    e, sym, vname = extract_function(prompt)
    if e is None:
        return ["ERR:no_function" for _ in parts]
    m = re.search(rf'{vname}\s*=\s*([^\s,]+)\s+and\s+{vname}\s*=\s*([^\s,.]+)', prompt)
    if not m:
        return ["ERR:no_two_x_values" for _ in parts]
    a = parse_num(m.group(1))
    b = parse_num(m.group(2))
    try:
        fa = e.subs(sym, a)
        fb = e.subs(sym, b)
        slope = (fb - fa) / (b - a)
        return [format_answer(slope)]
    except Exception as ex:
        return [f"ERR:{ex}"]

def solve_piecewise(parts, prompt):
    """Piecewise f(x) = {branch1 if cond1; branch2 if cond2}, evaluate slope at each sub-point."""
    m = re.search(r'\{([^}]+)\}', prompt)
    if not m:
        return ["ERR:no_piecewise_braces" for _ in parts]
    inner = unicodify(m.group(1))
    # Split on ';' (preferred) or on 'if'-followed clauses; keep only pieces containing 'if'
    pieces = [p.strip() for p in inner.split(';')]
    if len(pieces) == 1:
        # fallback: split on ', ' before a digit/letter but not inside parens
        pieces = re.split(r',\s*(?=[-\d])', inner)
    branches = []
    for b in pieces:
        bm = re.match(r'(.+?)\s*,?\s*if\s+(.+?)\s*$', b.strip())
        if not bm:
            continue
        rhs = bm.group(1).strip().rstrip(',')
        try:
            expr = sympify(to_sympy_str(rhs))
        except Exception:
            continue
        cond_str = bm.group(2).replace(' ', '')
        branches.append((expr, cond_str))
    out = []
    for lbl, body in parts:
        # Extract point (a, b) or P(a, b)
        m_pt = re.search(r'P?\s*\(\s*([^,()]+?)\s*,\s*[^,()]+?\s*\)', body)
        if not m_pt:
            m_xv = re.search(r'x\s*=\s*([^\s,;)]+)', body)
            if not m_xv:
                out.append("ERR:no_eval_point")
                continue
            xv = parse_num(m_xv.group(1))
        else:
            xv = parse_num(m_pt.group(1))
        if xv is None:
            out.append("ERR:bad_point")
            continue
        # Pick branch by evaluating condition
        chosen = None
        for expr, cond in branches:
            cm = re.match(r'x(<=|>=|<|>|=)(-?[\d/.]+)', cond)
            if not cm:
                continue
            op, rhs = cm.group(1), parse_num(cm.group(2))
            if rhs is None: continue
            try:
                xv_f = float(xv); rhs_f = float(rhs)
            except Exception:
                continue
            if   op == '<=' and xv_f <= rhs_f: chosen = expr; break
            elif op == '>=' and xv_f >= rhs_f: chosen = expr; break
            elif op == '<'  and xv_f <  rhs_f: chosen = expr; break
            elif op == '>'  and xv_f >  rhs_f: chosen = expr; break
            elif op == '='  and xv_f == rhs_f: chosen = expr; break
        if chosen is None:
            # pick last branch as fallback
            if branches: chosen = branches[-1][0]
            else:
                out.append("ERR:no_branch")
                continue
        try:
            d = diff(chosen, x)
            out.append(format_answer(d.subs(x, xv)))
        except Exception as ex:
            out.append(f"ERR:{ex}")
    return out

# ---------- top-level dispatch ----------

PATTERNS = [
    ("radical_conjugate",     r'product.+radical.+conjugate'),
    ("slope_pair_points",     r'slope of the line through.+pair.+points'),
    ("slope_secant",          r'slope of the secant'),
    ("slope_perpendicular",   r'slope of a line perpendicular'),
    ("tangent_parallel_line", r'tangent is parallel to the line'),
    ("slope_piecewise",       r'slope of the graph of f\(x\)\s*=\s*\{'),
    ("slope_tangent",         r'slope of the (?:tangent|graph)'),
    ("rate_of_change",        r'circulation|rate|how fast|projected'),
]

def classify(prompt: str):
    low = prompt.lower()
    for name, pat in PATTERNS:
        if re.search(pat, low):
            return name
    return None

def solve_question(prompt: str, num_blanks: int):
    pattern = classify(prompt)
    parts = split_sub_parts(prompt)
    if not pattern:
        return {"ok": False, "pattern": None, "reason": "no_pattern_match",
                "prompt_head": prompt[:200]}
    try:
        if pattern == "radical_conjugate":
            answers = solve_conjugate_products(parts)
        elif pattern == "slope_pair_points":
            answers = solve_slope_between_points(parts)
        elif pattern == "slope_secant":
            answers = solve_secant(parts, prompt)
        elif pattern == "slope_perpendicular":
            answers = solve_perpendicular(parts)
        elif pattern == "tangent_parallel_line":
            answers = solve_tangent_parallel_line(parts, prompt)
        elif pattern == "slope_piecewise":
            answers = solve_piecewise(parts, prompt)
        elif pattern in ("slope_tangent", "rate_of_change"):
            answers = solve_tangent_at(parts)
        else:
            return {"ok": False, "pattern": pattern, "reason": "unroutable"}
        # Pad/truncate to num_blanks if needed
        if len(answers) != num_blanks:
            return {"ok": False, "pattern": pattern, "reason": f"count_mismatch ({len(answers)} vs {num_blanks})",
                    "answers": answers}
        return {"ok": True, "pattern": pattern, "answers": answers}
    except Exception as ex:
        return {"ok": False, "pattern": pattern, "reason": f"exc:{ex}"}

if __name__ == "__main__":
    # Self-test using the questions we captured
    tests = [
        ("Calculate the product of each radical expression and its corresponding conjugate.\n\na. √5 - √2 \nQuestion Blank 1 of 4\n\nb. 3√5 + 2√2 \nQuestion Blank 2 of 4\n\nc. 9 + 2√5 \nQuestion Blank 3 of 4\n\nd. 3√5 - 2√10 \nQuestion Blank 4 of 4", 4, ["3","37","61","5"]),
        ("Consider the graph of the function f(x) = 5x² - 8x. Calculate the slope of the secant that joins the points on the graph given by x = -2 and x = 1.", 1, ["-13"]),
        ("Determine the slope of the tangent to each curve at the given point.\n\na. y = x² - 3x, (2, -2) \nQuestion Blank 1 of 6\n\nb. f(x) = 4/x, (-2, -2) \nQuestion Blank 2 of 6\n\nc. y = 3x³, (1, 3) \nQuestion Blank 3 of 6\n\nd. y = √(x - 7), (16, 3) \nQuestion Blank 4 of 6\n\ne. y = √(25 - x²), (3, 4) \nQuestion Blank 5 of 6\n\nf. y = (4 + x)/(x - 2), (8, 2) \nQuestion Blank 6 of 6", 6, ["1","-1","9","1/6","-3/4","-1/6"]),
        ("Calculate the slope of the graph of f(x) = {4 - x², if x ≤ 1; 2x + 1, if x > 1} at each of the following points:\n\na. P(-1, 3) \nQuestion Blank 1 of 2\n\nb. P(2, 5) \nQuestion Blank 2 of 2", 2, ["2","2"]),
        ("Determine the slope of the tangent at x = 4 for f(x) = x/(x² - 15).", 1, ["-31"]),
        ("It is projected that, t years from now, the circulation of a local newspaper will be C(t) = 100t² + 400t + 5000. Find how fast the circulation is increasing after 6 months. Hint: Find the slope of the tangent when t = 0.5.", 1, ["500"]),
        ("Calculate the slope of the tangent to each curve at the given point or value of x.\n\na. f(x) = x² + 3x - 5, (-3, -5) \nQuestion Blank 1 of 4\n\nb. y = 1/x, x = 1/3 \nQuestion Blank 2 of 4\n\nc. y = 4/(x - 2), (6, 1) \nQuestion Blank 3 of 4\n\nd. f(x) = √(x + 4), x = 5 \nQuestion Blank 4 of 4", 4, ["-3","-9","-1/4","1/6"]),
        ("Determine the slope of the tangent to each curve at the given value of x.\n\na. y = 3x², x = -2 \nQuestion Blank 1 of 3\n\nb. y = x² - x, x = 3 \nQuestion Blank 2 of 3\n\nc. y = x³, x = -2 \nQuestion Blank 3 of 3", 3, ["-12","5","12"]),
        ("Find the coordinates of the point on the curve f(x) = 3x² - 4x where the tangent is parallel to the line y = 8x.\n\nx = \nQuestion Blank 1 of 2\n\ny = \nQuestion Blank 2 of 2", 2, ["2","4"]),
    ]
    for prompt, n, expected in tests:
        r = solve_question(prompt, n)
        got = r.get("answers")
        ok = got == expected
        mark = "OK " if ok else "BAD"
        print(f"[{mark}] pattern={r.get('pattern')} expected={expected} got={got}")
        if not r.get("ok"):
            print(f"       reason: {r.get('reason')}")
