"""List the GDP configurations outside the gap box within two stages of the reference.

  python list_configs.py > configs.txt

Writes every (f1, c1, c2, c3, f2, b) with 2 <= f1 <= c1 < c2 < c3 <= f2 <= b <= 21, within
L-infinity distance 2 of (8, 8, 12, 17, 17, 21) in stage positions, and with a gap above 6.
"""
import itertools


def gaps(c):
    f1, c1, c2, c3, f2, b = c
    return (f1 - 2, c1 - f1, c2 - c1 - 1, c3 - c2 - 1, f2 - c3, b - f2)


best = (8, 8, 12, 17, 17, 21)
for c in itertools.product(range(2, 22), repeat=6):
    if 2 <= c[0] <= c[1] < c[2] < c[3] <= c[4] <= c[5] <= 21 \
            and max(abs(a - b) for a, b in zip(c, best)) <= 2 and max(gaps(c)) > 6:
        print(*c)
