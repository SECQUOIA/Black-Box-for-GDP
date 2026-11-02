"""Fit the catalytic distillation property correlations to open reference equations of state.

Isobutene and 1-butene: Lemmon and Ihmels (2005), Fluid Phase Equilib. 228-229, 173-187.
Ethanol: Schroeder, Penoncello, and Schmidt (2014), J. Phys. Chem. Ref. Data 43, 043102.
Surface tension: Mulero, Cachadina, and Parra (2012), J. Phys. Chem. Ref. Data 41, 043105.
All evaluated with CoolProp (checked with 8.0.0).  The fitted forms are those of the model:
extended Antoine, ideal-gas Cp polynomial, DIPPR 106 heat of vaporization, liquid Cp
polynomial, plus the Rackett parameter Z_RA and the Macleod-Sugden parachor used by the
mixture liquid density and surface tension.  Prints GAMS parameter rows and fit errors, and
compares the current (Aspen-derived) coefficients with the reference equations.
"""

import json
import math
import sys

import CoolProp.CoolProp as CP
import numpy as np

FLUIDS = {"iButene": "Isobutene", "nButene": "1-Butene", "Ethanol": "Ethanol"}
R = 8.314462618
# Current model coefficients, for the comparison only.
OLD_ANTOINE = {"iButene": (66.4970745, -4634.1, -8.9575, 1.3413E-5, 2),
               "nButene": (40.3230745, -4019.2, -4.5229, 4.8833E-17, 6),
               "Ethanol": (61.7910745, -7122.3, -7.1424, 2.8853E-6, 2)}


def lstsq(A, b):
    coef, *_ = np.linalg.lstsq(A, b, rcond=None)
    return coef


def fit(component):
    f = FLUIDS[component]
    tc, pc = CP.PropsSI("Tcrit", f), CP.PropsSI("pcrit", f) / 1e5
    vc = 1 / CP.PropsSI("rhomolar_critical", f)
    out = dict(Tc=tc, Pc=pc, omega=CP.PropsSI("acentric", f), MW=CP.PropsSI("molar_mass", f) * 1000, Vc_m3_mol=vc)
    t_sat = np.linspace(230, tc - 0.5, 300)
    p_sat = np.array([CP.PropsSI("P", "T", t, "Q", 0, f) for t in t_sat]) / 1e5

    # Extended Antoine ln P[bar] = C1 + C2/T + C5 ln T + C6 T^C7, choosing C7 from {1, 2, 6}.
    best = None
    for c7 in (1, 2, 6):
        A = np.c_[np.ones_like(t_sat), 1 / t_sat, np.log(t_sat), t_sat ** c7]
        coef = lstsq(A, np.log(p_sat))
        err = np.max(np.abs(np.exp(A @ coef) / p_sat - 1))
        if best is None or err < best[2]:
            best = (coef, c7, err)
    (c1, c2, c5, c6), c7, err = best
    out["antoine"] = dict(C1a=c1, C2a=c2, C5a=c5, C6a=c6, C7a=c7, max_rel_error=err)
    op = (t_sat >= 300) & (t_sat <= 416)
    a1, a2, a5, a6, a7 = OLD_ANTOINE[component]
    old = np.exp(a1 + a2 / t_sat + a5 * np.log(t_sat) + a6 * t_sat ** a7)
    out["current_antoine_error_300_416K"] = dict(min=float(np.min(old[op] / p_sat[op] - 1)), max=float(np.max(old[op] / p_sat[op] - 1)))

    # Ideal-gas Cp [kJ/(mol K)] = C1c + C2c T + C3c T^2 + C4c T^3, 250-600 K.
    t_ig = np.linspace(250, 600, 200)
    cp0 = np.array([CP.PropsSI("Cp0molar", "T", t, "P", 1e3, f) for t in t_ig]) / 1000
    coef = lstsq(np.c_[np.ones_like(t_ig), t_ig, t_ig ** 2, t_ig ** 3], cp0)
    out["cp_ig"] = dict(zip(("C1c", "C2c", "C3c", "C4c"), coef),
                        max_rel_error=float(np.max(np.abs(np.polyval(coef[::-1], t_ig) / cp0 - 1))))

    # Heat of vaporization [kJ/mol] = C1v (1 - Tr)^(C2v + C3v Tr + C4v Tr^2), 230 K to 0.99 Tc.
    t_v = np.linspace(230, 0.99 * tc, 200)
    dh = np.array([CP.PropsSI("Hmolar", "T", t, "Q", 1, f) - CP.PropsSI("Hmolar", "T", t, "Q", 0, f) for t in t_v]) / 1000
    tr = t_v / tc
    L = np.log(1 - tr)
    coef = lstsq(np.c_[np.ones_like(tr), L, tr * L, tr ** 2 * L], np.log(dh))
    pred = np.exp(coef[0]) * (1 - tr) ** (coef[1] + coef[2] * tr + coef[3] * tr ** 2)
    out["dhvap"] = dict(C1v=math.exp(coef[0]), C2v=coef[1], C3v=coef[2], C4v=coef[3],
                        max_rel_error=float(np.max(np.abs(pred / dh - 1))))

    # Saturated-liquid Cp [kJ/(mol K)] = C1l + C2l T + C3l T^2 + C4l T^3, 230 K to 0.9 Tc.
    t_l = np.linspace(230, 0.9 * tc, 200)
    cpl = np.array([CP.PropsSI("Cpmolar", "T", t, "Q", 0, f) for t in t_l]) / 1000
    coef = lstsq(np.c_[np.ones_like(t_l), t_l, t_l ** 2, t_l ** 3], cpl)
    out["cp_liquid"] = dict(zip(("C1l", "C2l", "C3l", "C4l"), coef),
                            max_rel_error=float(np.max(np.abs(np.polyval(coef[::-1], t_l) / cpl - 1))))

    # Rackett: V_sat = R Tc/Pc Z_RA^(1 + (1 - Tr)^(2/7)), 250 K to 0.95 Tc.
    t_r = np.linspace(250, 0.95 * tc, 200)
    v = 1 / np.array([CP.PropsSI("Dmolar", "T", t, "Q", 0, f) for t in t_r])
    expo = 1 + (1 - t_r / tc) ** (2 / 7)
    ln_z = float(np.sum(expo * (np.log(v) - np.log(R * tc / (pc * 1e5)))) / np.sum(expo ** 2))
    pred = R * tc / (pc * 1e5) * math.exp(ln_z) ** expo
    out["rackett"] = dict(Z_RA=math.exp(ln_z), max_rel_error=float(np.max(np.abs(pred / v - 1))))

    # Macleod-Sugden: sigma[mN/m]^(1/4) = P (rhoL - rhoV) [mol/cm^3], 250 K to 0.95 Tc.
    sig = np.array([CP.PropsSI("surface_tension", "T", t, "Q", 0, f) for t in t_r]) * 1000
    drho = np.array([CP.PropsSI("Dmolar", "T", t, "Q", 0, f) - CP.PropsSI("Dmolar", "T", t, "Q", 1, f) for t in t_r]) / 1e6
    par = float(np.sum(sig ** 0.25 * drho) / np.sum(drho ** 2))
    pred = (par * drho) ** 4
    out["parachor"] = dict(P=par, max_rel_error_to_380K=float(np.max(np.abs(pred / sig - 1)[t_r <= 380])),
                           max_rel_error=float(np.max(np.abs(pred / sig - 1))))
    return out


if __name__ == "__main__":
    results = {c: fit(c) for c in FLUIDS}
    json.dump(results, sys.stdout, indent=1, default=float)
    print()
