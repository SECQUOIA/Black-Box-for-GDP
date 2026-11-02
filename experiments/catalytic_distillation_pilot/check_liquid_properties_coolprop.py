"""Model liquid density and surface tension against CoolProp reference equations of state.

Needs CoolProp (checked with 8.0.0): isobutene, 1-butene, and ethanol; ETBE is not in CoolProp.  See REVIEW.md.
"""
import CoolProp.CoolProp as CP

R1 = dict(iButene=1.1446, Ethanol=1.6288, nButene=1.0877)
R2 = dict(iButene=0.2724, Ethanol=0.27469, nButene=0.26454)
R3 = dict(iButene=0.28172, Ethanol=0.23178, nButene=0.2843)
TC = dict(iButene=417.9, Ethanol=514.0, nButene=419.5)
S = dict(iButene=(0.05544, 1.2453, 0, 0), nButene=(0.055945, 1.2402, 0, 0))
FLUID = dict(iButene="Isobutene", nButene="1-Butene", Ethanol="Ethanol")


def rho_published(c, T):
    return R1[c] / R2[c] ** 2 * 1000  # exponent C4r = 0 makes (1 - T/Tc)**0 = 1


def rho_corrected(c, T):
    return R1[c] / R2[c] ** (1 + (1 - T / TC[c]) ** R3[c]) * 1000


def sigma_published(c, T):
    if c == "Ethanol":
        a, b, d = 0.03764, -2.157e-5, 1.025e-7  # DIPPR 106 form with polynomial coefficients
        return a * (1 - T / TC[c]) ** (b + d * T / TC[c])
    a, b, d, e = S[c]
    return a * (1 - T / TC[c]) ** (b + d * T / TC[c] + e * (T / TC[c]) ** 2)


def sigma_corrected(c, T):
    if c == "Ethanol":
        return 0.03764 - 2.157e-5 * T - 1.025e-7 * T ** 2
    return sigma_published(c, T)


for c in ("iButene", "nButene", "Ethanol"):
    print(f"== {c} ({FLUID[c]})")
    print("  T [K]  rho_ref  published  corrected | sigma_ref  published  corrected")
    for T in (300, 320, 340, 360, 380, 400, 410):
        if T >= TC[c] - 1:
            continue
        rr = CP.PropsSI("Dmolar", "T", T, "Q", 0, FLUID[c])
        sr = CP.PropsSI("surface_tension", "T", T, "Q", 0, FLUID[c])
        rp, rc = rho_published(c, T), rho_corrected(c, T)
        sp, sc = sigma_published(c, T), sigma_corrected(c, T)
        print(f"  {T:5d} {rr:8.0f} {rp:8.0f} ({100*(rp-rr)/rr:+5.1f}%) {rc:8.0f} ({100*(rc-rr)/rr:+5.1f}%) |"
              f" {sr:.5f} {sp:.5f} ({100*(sp-sr)/sr:+6.1f}%) {sc:.5f} ({100*(sc-sr)/sr:+6.1f}%)")
