"""Model NRTL and ETBE pure-component properties against open experimental data.

Data files (CSV, with sources) come from the NIST TRC ThermoML Archive and the papers listed
in REVIEW.md; pass their folder as the first argument.  Low-pressure VLE uses modified Raoult's
law (gamma from the model's NRTL, measured or model vapor pressures); the 323 K isobutene +
ethanol data reach 6 bar, so the fugacity corrections are neglected there too, which is an
approximation of a few percent at most.
"""

import csv
import math
from pathlib import Path
import sys

C = ("iButene", "Ethanol", "nButene", "ETBE")
B = {"iButene": {"Ethanol": 623.5810010, "nButene": 107.526499, "ETBE": 219.73407},
     "Ethanol": {"iButene": 141.9632130, "nButene": 164.57256, "ETBE": 187.104064},
     "nButene": {"iButene": -93.24546420, "Ethanol": 595.5299820, "ETBE": 226.373398},
     "ETBE": {"iButene": -172.59152, "Ethanol": 344.481315, "nButene": -177.88565}}
ALPHA = 0.3
ANTOINE = {"ETBE": (52.67507454, -5820.2, -6.1343, 2.1405E-17, 6), "Ethanol": (61.7910745, -7122.3, -7.1424, 2.8853E-6, 2)}


def psat(c, T):
    a1, a2, a5, a6, a7 = ANTOINE[c]
    return math.exp(a1 + a2 / T + a5 * math.log(T) + a6 * T ** a7) * 100  # kPa


def gammas(x, T):
    """NRTL with tau_ij = b_ij/T and the index order of the model (tau_ji G_ji in the first sum)."""
    comps = list(x)
    tau = {(i, j): (B[i][j] / T if i != j else 0.0) for i in comps for j in comps}
    G = {(i, j): math.exp(-ALPHA * tau[i, j]) for i in comps for j in comps}
    out = {}
    for i in comps:
        s1 = sum(x[j] * tau[j, i] * G[j, i] for j in comps) / sum(x[k] * G[k, i] for k in comps)
        s2 = sum(x[j] * G[i, j] / sum(x[k] * G[k, j] for k in comps)
                 * (tau[i, j] - sum(x[m] * tau[m, j] * G[m, j] for m in comps) / sum(x[k] * G[k, j] for k in comps))
                 for j in comps)
        out[i] = math.exp(s1 + s2)
    return out


def read(path):
    return list(csv.DictReader(open(path)))


def main(folder):
    folder = Path(folder)
    print("== Isobutene (1) + ethanol (2) at 323 K, Ouni et al. (2004): bubble pressure from model NRTL")
    rows = read(folder / "vle_isobutene1_ethanol2_isothermal_323K_Ouni2004.csv")
    p1 = next(float(r["P_kPa"]) for r in rows if float(r["x1_isobutene"]) == 1.0)
    p2 = next(float(r["P_kPa"]) for r in rows if float(r["x1_isobutene"]) == 0.0)
    errors = []
    for r in rows:
        x1, T, p = float(r["x1_isobutene"]), float(r["T_K"]), float(r["P_kPa"])
        if 0 < x1 < 1:
            g = gammas({"iButene": x1, "Ethanol": 1 - x1}, T)
            pc = x1 * g["iButene"] * p1 + (1 - x1) * g["Ethanol"] * p2
            errors.append((x1, p, pc, 100 * (pc - p) / p))
    for x1, p, pc, e in errors[::3]:
        print(f"  x1 {x1:.3f}  P {p:7.1f} kPa  model {pc:7.1f}  ({e:+.1f}%)")
    abs_e = [abs(e[3]) for e in errors]
    print(f"  {len(errors)} points: mean |dev| {sum(abs_e) / len(abs_e):.1f}%, max {max(abs_e):.1f}%")

    print("== ETBE (1) + ethanol (2) azeotrope: model NRTL with model vapor pressures")
    for r in read(folder / "azeotrope_ETBE1_ethanol2_isobaric_NihonUniv.csv"):
        P = float(r["P_kPa"])
        best = None
        for k in range(1, 1000):
            x1 = k / 1000
            lo, hi = 300.0, 380.0
            for _ in range(60):
                T = (lo + hi) / 2
                g = gammas({"ETBE": x1, "Ethanol": 1 - x1}, T)
                pb = x1 * g["ETBE"] * psat("ETBE", T) + (1 - x1) * g["Ethanol"] * psat("Ethanol", T)
                lo, hi = (T, hi) if pb < P else (lo, T)
            if best is None or T < best[1]:
                best = (x1, T)
        print(f"  P {P:6.1f} kPa: data T {float(r['T_az_K']):.2f} K, x_ETBE {float(r['x1_ETBE_az']):.3f};"
              f" model T {best[1]:.2f} K, x_ETBE {best[0]:.3f}")

    print("== ETBE vapor pressure: model extended Antoine vs open data")
    vp = [r for r in read(folder / "pure_vapor_pressure_ETBE_isobutene_ethanol.csv") if r["component"] == "ETBE"]
    dev = [(float(r["T_K"]), 100 * (psat("ETBE", float(r["T_K"])) / float(r["Psat_kPa"]) - 1), r["source"][:28]) for r in vp]
    print(f"  {len(dev)} points {min(d[0] for d in dev):.1f}-{max(d[0] for d in dev):.1f} K: "
          f"mean {sum(d[1] for d in dev) / len(dev):+.2f}%, range {min(d[1] for d in dev):+.2f}% to {max(d[1] for d in dev):+.2f}%")

    print("== ETBE liquid density: Rackett Z_RA fitted to open data at 0.1 MPa (Tc 509.4 K, Pc 29.34 bar)")
    dens = [r for r in read(folder / "ETBE_liquid_density.csv") if abs(float(r["P_kPa"]) - 100) < 10 or r["P_kPa"] in ("", "101.325")]
    mw = 102.17656e-3
    tc, pc, R = 509.4, 29.34e5, 8.314462618
    num = den = 0.0
    pts = []
    for r in dens:
        T, v = float(r["T_K"]), mw / float(r["rho_kg_m3"])
        e = 1 + (1 - T / tc) ** (2 / 7)
        num += e * (math.log(v) - math.log(R * tc / pc))
        den += e * e
        pts.append((T, v, e))
    z = math.exp(num / den)
    err = [100 * (R * tc / pc * z ** e / v - 1) for T, v, e in pts]
    print(f"  {len(pts)} points {min(p[0] for p in pts):.2f}-{max(p[0] for p in pts):.2f} K: Z_RA {z:.5f}, "
          f"max |dev| {max(abs(x) for x in err):.2f}% (Yamada-Gunn from omega 0.316: {0.29056 - 0.08775 * 0.316231:.5f})")

    sig = read(folder / "ETBE_surface_tension.csv")
    s298 = sum(float(r["sigma_mN_m"]) for r in sig) / len(sig)
    rho298 = 1 / (R * tc / pc * z ** (1 + (1 - 298.15 / tc) ** (2 / 7))) / 1e6  # mol/cm^3; vapor density negligible
    print(f"== ETBE parachor from sigma(298.15 K) = {s298:.2f} mN/m: {s298 ** 0.25 / rho298:.1f} (Quayle groups: 290.8)")
    return z, s298 ** 0.25 / rho298


if __name__ == "__main__":
    main(sys.argv[1])
