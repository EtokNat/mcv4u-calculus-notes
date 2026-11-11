"""Lesson 4 — stacked panel showing f(x)=x^3-3x alongside f'(x)=3x^2-3 and f''(x)=6x.

The point of this graphic is to let a student see the structural links:
- extrema of f at x = ±1  <->  zeros of f'
- inflection of f at x = 0  <->  minimum of f'  <->  zero of f''
- concavity of f           <->  sign of f''
"""
import numpy as np
import matplotlib.pyplot as plt

x = np.linspace(-2.2, 2.2, 400)
f = x**3 - 3*x
fp = 3*x**2 - 3
fpp = 6*x

fig, axes = plt.subplots(3, 1, figsize=(6.4, 7.2), sharex=True)

# f(x)
ax = axes[0]
ax.plot(x, f, color='#0b4f8c', linewidth=2.5)
ax.axhline(0, color='#888', linewidth=0.6)
ax.axvline(0, color='#888', linewidth=0.6)
ax.scatter([-1, 1], [2, -2], color='#c88a1a', zorder=5, s=55)
ax.annotate('local max (-1, 2)', (-1, 2), xytext=(-2.0, 3.2), fontsize=9,
            arrowprops=dict(arrowstyle='->', color='#c88a1a'))
ax.annotate('local min (1, -2)', (1, -2), xytext=(0.15, -4.2), fontsize=9,
            arrowprops=dict(arrowstyle='->', color='#c88a1a'))
ax.scatter([0], [0], color='#2f8a42', zorder=5, s=55)
ax.annotate('inflection (0, 0)', (0, 0), xytext=(0.5, 1.1), fontsize=9,
            arrowprops=dict(arrowstyle='->', color='#2f8a42'))
ax.set_ylabel(r'$f(x) = x^3 - 3x$', fontsize=11)
ax.set_ylim(-5, 5)
ax.grid(alpha=0.25)

# f'(x)
ax = axes[1]
ax.plot(x, fp, color='#a3310f', linewidth=2.5)
ax.axhline(0, color='#888', linewidth=0.6)
ax.axvline(0, color='#888', linewidth=0.6)
ax.scatter([-1, 1], [0, 0], color='#c88a1a', zorder=5, s=55)
ax.annotate("f' = 0 at x = -1", (-1, 0), xytext=(-2.1, 3.5), fontsize=9,
            arrowprops=dict(arrowstyle='->', color='#c88a1a'))
ax.annotate("f' = 0 at x = 1", (1, 0), xytext=(0.5, 3.5), fontsize=9,
            arrowprops=dict(arrowstyle='->', color='#c88a1a'))
ax.scatter([0], [-3], color='#2f8a42', zorder=5, s=55)
ax.annotate("min of f'  (x = 0)", (0, -3), xytext=(0.3, -2.3), fontsize=9,
            arrowprops=dict(arrowstyle='->', color='#2f8a42'))
ax.set_ylabel(r"$f'(x) = 3x^2 - 3$", fontsize=11)
ax.set_ylim(-5, 10)
ax.grid(alpha=0.25)

# f''(x)
ax = axes[2]
ax.plot(x, fpp, color='#1b5a28', linewidth=2.5)
ax.axhline(0, color='#888', linewidth=0.6)
ax.axvline(0, color='#888', linewidth=0.6)
ax.scatter([0], [0], color='#2f8a42', zorder=5, s=55)
ax.annotate("f'' = 0 at x = 0", (0, 0), xytext=(0.3, 4.5), fontsize=9,
            arrowprops=dict(arrowstyle='->', color='#2f8a42'))
ax.fill_between(x, fpp, 0, where=(x < 0), alpha=0.15, color='red',
                label='concave down')
ax.fill_between(x, fpp, 0, where=(x > 0), alpha=0.15, color='green',
                label='concave up')
ax.set_ylabel(r"$f''(x) = 6x$", fontsize=11)
ax.set_xlabel('x')
ax.set_ylim(-14, 14)
ax.legend(loc='lower right', fontsize=8)
ax.grid(alpha=0.25)

plt.suptitle(r'$f$, $f\,\prime$, $f\,\prime\prime$ — the structural links',
             fontsize=12, y=0.995)
plt.tight_layout()
plt.savefig('/storage/emulated/0/gis-sat/slides/img/l4_cubic_stack.png',
            dpi=140, bbox_inches='tight', facecolor='white')
print("Saved l4_cubic_stack.png")

# Verification pass — print landmark values for eyeballing
print()
print("Verification values:")
print(f"  f(-1) = {(-1)**3 - 3*(-1)}  (should be 2)")
print(f"  f(1)  = {1**3 - 3*1}  (should be -2)")
print(f"  f(0)  = {0**3 - 3*0}  (should be 0)")
print(f"  f'(-1) = {3*1 - 3}  (should be 0)")
print(f"  f'(1)  = {3*1 - 3}  (should be 0)")
print(f"  f'(0)  = {3*0 - 3}  (should be -3)")
print(f"  f''(0) = {6*0}  (should be 0)")
print(f"  f''(-1) = {6*(-1)}  (should be -6, so concave down)")
print(f"  f''(1)  = {6*1}  (should be 6, so concave up)")
