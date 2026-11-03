"""Model property correlations (distillation_model.gms) against NIST Chemistry WebBook values.

The NIST values were read on 2026-10-31 from https://webbook.nist.gov/cgi/cbook.cgi?ID=<ID>&Units=SI&Mask=1,2,4
for isobutene (C115117), ethanol (C64175), 1-butene (C106989), and ETBE (C637923).  See REVIEW.md.
"""
import math

C = ("iButene", "Ethanol", "nButene", "ETBE")
# Model constants, copied from distillation_model.gms
A1 = dict(iButene=66.4970745, Ethanol=61.7910745, nButene=40.3230745, ETBE=52.67507454)
A2 = dict(iButene=-4634.1, Ethanol=-7122.3, nButene=-4019.2, ETBE=-5820.2)
A5 = dict(iButene=-8.9575, Ethanol=-7.1424, nButene=-4.5229, ETBE=-6.1343)
A6 = dict(iButene=1.3413E-5, Ethanol=2.8853E-6, nButene=4.8833E-17, ETBE=2.1405E-17)
A7 = dict(iButene=2, Ethanol=2, nButene=6, ETBE=6)
CG = dict(iButene=(0.016052191, 0.000280432, -0.00000010914988, 0.0000000000090979164),
          Ethanol=(0.00901418, 0.000214071, -0.000000083903472, 0.0000000000013732704),
          nButene=(-0.00299356, 0.000353198, -0.00000019904047, 0.000000000044631288),
          ETBE=(-0.014651654, 0.000698631, -0.00000044791741, 0.00000000011636811))
CV = dict(iButene=(32.614, 0.38073, 0, 0), Ethanol=(55.789, 0.31245, 0, 0),
          nButene=(33.774, 0.5107, -0.17304, 0.05181), ETBE=(45.29, 0.27343, 0.21645, -0.11756))
CL = dict(iButene=(0.08768, 0.0002171, -9.15300E-07, 2.2660E-09, 0), Ethanol=(0.10264, -0.00013963, -3.03410E-08, 2.0386E-09, 0),
          nButene=(0.18205, -0.001611, 1.19630E-05, -3.7454E-08, 4.5027E-11), ETBE=(0.11096, 0.00031422, 1.74800E-07, 0, 0))
HF = dict(iButene=-16.9147, Ethanol=-234.963, nButene=-0.125604, ETBE=-313.9)
TC_PUB = dict(iButene=417.9, Ethanol=516.2, nButene=419.6, ETBE=509.4)
TC_SRK = dict(iButene=417.9, Ethanol=514, nButene=419.5, ETBE=509.4)
PC_PUB = dict(iButene=38.98675, Ethanol=60.35675, nButene=39.18675, ETBE=28.32675)
OMEGA = dict(iButene=0.19484, Ethanol=0.643558, nButene=0.184495, ETBE=0.316231)


def psat(c, T):
    return math.exp(A1[c] + A2[c] / T + A5[c] * math.log(T) + A6[c] * T ** A7[c])


def tsat(c, P):
    lo, hi = 150.0, 600.0
    for _ in range(200):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if psat(c, mid) < P else (lo, mid)
    return (lo + hi) / 2


def cpg(c, T):
    a, b, d, e = CG[c]
    return 1000 * (a + b * T + d * T ** 2 + e * T ** 3)


def dhvap(c, T, tc):
    a, b, d, e = CV[c]
    tr = T / tc
    return a * (1 - tr) ** (b + d * tr + e * tr ** 2)


def cpl(c, T):
    return 1000 * sum(k * T ** i for i, k in enumerate(CL[c]))


def antoine(A, B, Cc, T):
    return 10 ** (A - B / (T + Cc))


def pct(model, ref):
    return f"{100 * (model - ref) / ref:+.1f}%"


print("== Critical constants (model published / corrected vs NIST)")
nist_tc = dict(iButene="417.9 ± 0.1", Ethanol="514 ± 7 (513.9 Majer-Svoboda)", nButene="419.5 ± 0.5", ETBE="not on NIST")
nist_pc = dict(iButene=40.00, Ethanol=63.0, nButene=40.2, ETBE=None)
for c in C:
    print(f"  {c:8s} Tc {TC_PUB[c]} / {TC_SRK[c]}  NIST {nist_tc[c]};  Pc {PC_PUB[c]:.3f} (+1.01325 = {PC_PUB[c] + 1.01325:.3f}) NIST {nist_pc[c]}")

print("== Normal boiling point from the model's Antoine vs NIST")
nist_tb = dict(iButene="266.7 ± 0.7", Ethanol="351.5 ± 0.2", nButene="266.8 ± 0.5", ETBE="345.6–346.3")
for c in C:
    print(f"  {c:8s} model {tsat(c, 1.01325):.2f} K  NIST {nist_tb[c]}")

print("== Vapor pressure vs NIST Antoine within its range (bar)")
checks = [("iButene", (3.64709, 799.055, -46.615), [230, 250, 266, 273]),
          ("nButene", (4.24696, 1099.207, -8.256), [220, 240, 260, 269]),
          ("Ethanol", (5.24677, 1598.673, -46.424), [300, 320, 340, 360]),
          ("Ethanol", (4.92531, 1432.526, -61.819), [370, 400, 422, 440, 480])]
for c, (A, B, Cc), Ts in checks:
    print("  " + c + ": " + ", ".join(f"{T} K {psat(c, T):.4g} vs {antoine(A, B, Cc, T):.4g} ({pct(psat(c, T), antoine(A, B, Cc, T))})" for T in Ts))
print(f"  Ethanol T at 9.5 bar: model {tsat('Ethanol', 9.5):.2f} K, NIST Ambrose 1975 {1432.526 / (4.92531 - math.log10(9.5)) + 61.819:.2f} K")

print("== Ideal-gas Cp (J/mol/K) vs NIST (TRC tables; experimental where noted)")
nist_cpg = dict(iButene=[(298.15, 88.09), (312.15, 91.67), (353.15, 100.25), (400, 109.79)],
                Ethanol=[(298.15, 65.21), (350.01, 73.15), (380, 77.46), (400.08, 80.40)],
                nButene=[(298.15, 85.56), (313.55, 89.58), (363.25, 101.21), (400, 108.48)],
                ETBE=[(300, 149.33), (400, 193.03)])
for c in C:
    print("  " + c + ": " + ", ".join(f"{T} K {cpg(c, T):.1f} vs {v} ({pct(cpg(c, T), v)})" for T, v in nist_cpg[c]))

print("== Heat of vaporization (kJ/mol) vs NIST")
def majer(A, alpha, beta, tc, T):
    tr = T / tc
    return A * math.exp(-alpha * tr) * (1 - tr) ** beta
for c, tc_key in (("published Tc", TC_PUB), ("corrected Tc", TC_SRK)):
    print(f"  [{c}]")
    print("   Ethanol: " + ", ".join(f"{T} K {dhvap('Ethanol', T, tc_key['Ethanol']):.2f} vs {majer(50.43, -0.4475, 0.4989, 513.9, T):.2f} ({pct(dhvap('Ethanol', T, tc_key['Ethanol']), majer(50.43, -0.4475, 0.4989, 513.9, T))})" for T in (298.15, 351.5, 400, 420)))
    print("   nButene: " + ", ".join(f"{T} K {dhvap('nButene', T, tc_key['nButene']):.2f} vs {majer(32.51, 0.0052, 0.38, 419.6, T):.2f} ({pct(dhvap('nButene', T, tc_key['nButene']), majer(32.51, 0.0052, 0.38, 419.6, T))})" for T in (266.9, 300, 340, 370)))
    print("   iButene: " + ", ".join(f"{T} K {dhvap('iButene', T, tc_key['iButene']):.2f} vs {v}" for T, v in ((258, 22.8), (264, 23.1))))
    print("   ETBE:    " + ", ".join(f"{T} K {dhvap('ETBE', T, tc_key['ETBE']):.2f} vs {v}" for T, v in ((299, 33.5), (321, 32.2), (328, 32.1), (345.6, 29.76), (355, 31.2))))

print("== Liquid Cp (J/mol/K) vs NIST")
for c, T, v in (("iButene", 266.26, "121.3"), ("nButene", 298.15, "128.96 (Takeda 1991), 118 (Chao 1983)"),
                ("Ethanol", 298.15, "110.5–115.9, mostly ~112.3"), ("ETBE", 298, "218 (Evans and Edlund 1936)")):
    print(f"  {c:8s} {T} K model {cpl(c, T):.1f} vs {v}")

print("== Gas enthalpy of formation (kJ/mol) vs NIST")
nist_hf = dict(iButene="-17.9 ± 1.1", Ethanol="-234 ± 2", nButene="-0.63 ± 0.79", ETBE="-314 ± 2 (Iborra 1989), -317.8 (Sharonov 1995)")
for c in C:
    print(f"  {c:8s} model {HF[c]} vs {nist_hf[c]}")
dH_gas = HF["ETBE"] - HF["iButene"] - HF["Ethanol"]
print(f"  Reaction, gas phase from model Hform: {dH_gas:.1f} kJ/mol (NIST -62 ± 2, Iborra 1989)")

print("== Acentric factor: model value vs value implied by the model's own Antoine and absolute Pc")
pc_abs = {c: PC_PUB[c] + 1.01325 for c in C}
for c in C:
    w = -math.log10(psat(c, 0.7 * TC_SRK[c]) / pc_abs[c]) - 1
    print(f"  {c:8s} model {OMEGA[c]:.4f}, from Antoine {w:.4f}")
w_eth = -math.log10(antoine(5.24677, 1598.673, -46.424, 0.7 * 513.9) / 61.37) - 1
print(f"  Ethanol from NIST Antoine (Ambrose and Sprake 1970) and Pc 61.37: {w_eth:.4f}")
