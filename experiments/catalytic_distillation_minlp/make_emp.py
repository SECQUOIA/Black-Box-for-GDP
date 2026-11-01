"""Write the EMP (disjunctive) form of the corrected catalytic distillation column.

  python experiments/catalytic_distillation_minlp/make_emp.py

Reads gdp_models/catalytic_distillation/distillation_model_corrected.gms, where the
stage decisions are parameters that switch equations on and off, and writes
emp_model_corrected.gms.  There the decisions are binary variables and every switched
equation exists for every stage; gdp_models/catalytic_distillation/solve_emp.gms then
declares, for each internal stage, the disjunctions that the parameters encoded:

  par  stage exists: equilibrium, tray hydraulics, height    else vapor passes, no pressure drop
  yc   catalyst: kinetics, catalyst hydraulics, reaction,    else no reaction or catalyst drop
       120 C limit
  yf1  ethanol feed: flow                                     else no flow
  yf2  butenes feed: flow                                     else no flow
  yb   boil-up return: flow                                   else no flow

As in the published MINLP form, property and feed-enthalpy definitions hold on every stage.
The kinetics stay in the catalyst disjunct: on a stage without catalyst, the bounds of the
reaction rate would otherwise restrict the temperature and composition.  par is the stage indicator of the published model, linked to yb by its
linear definition; with CASE=0 every existing stage is an equilibrium stage.  The reflux
stays at stage 2, so yr stays a parameter.

GAMS/JAMS reformulates the disjunctions as Big-M or convex hull, and two rules make both
reformulations valid for this model:

* Every disjunct constraint is linear.  A nonlinear disjunct equation h(x) = 0 becomes a
  definition s*r = h(x) of a residual variable r, which holds on every stage, and the
  disjunct holds r = 0.  The convex hull of JAMS evaluates every disjunct function at
  zero, where 1/rhoL, 1/T, and L**(-0.59) are not defined.
* Every disjunct constraint is scaled by s, an interval bound on h over the bounds that
  the global constraints imply (compute_emp_scales.py writes s to emp_scales.gms).  A
  scaled disjunct constraint lies in [-1, 1] at every feasible point, so the single M = 1
  of JAMS is a valid Big-M for every equation.

The convex hull of JAMS does not accept equalities, so every disjunct equality is written
as an inequality pair, F (<=) and F_ge (>=); Big-M of the pair is Big-M of the equality.
"""

from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
FOLDER = ROOT / "gdp_models/catalytic_distillation"
SOURCE = FOLDER / "distillation_model_corrected.gms"
TARGET = FOLDER / "emp_model_corrected.gms"
INTERNAL = "ord(Net)>1 and ord(Net)<card(Net)"

# Disjunct equations, by indicator and term (True: indicator is 1, False: indicator is 0).
DISJUNCTS = {
    ("par", True): ["Eqfa", "EqhD", "Equhv", "Equnv", "Equl", "Eqhcl", "EqCsbf", "EqDPL", "EqDPS", "EqDPq",
                    "EqDP", "DownFlood", "EntrainFloodV", "EntrainFloodL", "Weep", "Equilibrio10", "eq_hs_stage"],
    ("par", False): ["Equilibrio20", "Equilibrio40", "NoDP", "no_hs_stage"],
    ("yc", True): ["EqKetbe", "EqKrate", "EqKa", "EqRx", "eqLload", "eqFfactor", "EqdPcat", "catflood",
                   "eq_reaction_term", "eq_partial_reaction_term", "EqTcat"],
    ("yc", False): ["no_reaction_term", "no_partial_reaction_term", "NodPcat"],
    ("yf1", True): ["eq_ETin"],
    ("yf1", False): ["no_ETin"],
    ("yf2", True): ["eq_BUTin"],
    ("yf2", False): ["no_BUTin"],
    ("yb", True): ["eq_boilup_flow"],
    ("yb", False): ["no_boilup_flow"],
}
# Nonlinear disjunct equations, which become residual definitions.
LIFTED = ["Eqfa", "EqhD", "Equhv", "Equnv", "Equl", "Eqhcl", "EqCsbf", "EqDPL", "EqDPS", "EqDPq", "DownFlood",
          "EntrainFloodV", "EntrainFloodL", "Weep", "Equilibrio10", "EqKetbe", "EqKrate", "EqKa", "EqRx", "eqLload",
          "eqFfactor", "EqdPcat", "eq_boilup_flow"]
FAMILIES = [name for names in DISJUNCTS.values() for name in names]
# Mixture mass densities [kg/m3] in the hydraulic correlations, replaced by bounded variables.
MASS_DENSITIES = {"rhoL(N,j,Net)*sum(comp,MW(comp)*x(N,j,comp,Net)/100)/1000": "rhoLm(N,j,Net)",
                  "rhoV(N,j,Net)*sum(comp,MW(comp)*y(N,j,comp,Net)/100)/1000": "rhoVm(N,j,Net)"}


def disjunct_equation(s, name, lifted):
    """Rewrite equation `name` as scaled linear constraints; return the text and its relation."""
    m = re.search(rf"^{name}(\([^)]*\))(\$\(.*?\))?\.\.(.*?);", s, flags=re.M | re.S)
    assert m, name
    dom, cond, body = m.group(1), m.group(2) or "", m.group(3)
    parts = re.split(r"(=[elg]=)", body, flags=re.I)
    assert len(parts) == 3, name
    lhs, op, rhs = parts[0].strip(), parts[1].lower(), parts[2].strip()
    expr = f"({lhs})-({rhs})"
    if lifted:
        for mixture, density in MASS_DENSITIES.items():
            starts = [i for i in range(len(expr)) if expr.startswith(mixture, i)]
            assert all(expr[i - 1] == "(" for i in starts), name
            expr = expr.replace(mixture, density)
    new = (f'parameter s_{name}{dom} "scale of {name}";\n'
           f"s_{name}{dom}=1;\n")
    if lifted:
        new += (f'variable r_{name}{dom} "scaled residual of {name}";\n'
                f'equation def_{name}{dom} "residual of {name}, on every stage";\n'
                f"def_{name}{dom}{cond}.. s_{name}{dom}*r_{name}{dom}=e={expr};\n")
        term = f"r_{name}{dom}"
    else:
        term = f"({expr})/s_{name}{dom}"
    if op == "=e=":
        new += (f"{name}{dom}{cond}.. {term}=l=0;\n"
                f"equation {name}_ge{dom};\n"
                f"{name}_ge{dom}{cond}.. {term}=g=0;")
    else:
        new += f"{name}{dom}{cond}.. {term}{op}0;"
    return s[:m.start()] + new + s[m.end():], op


def build(text):
    s = text.replace("\r\n", "\n")

    def sub(old, new, count=1):
        nonlocal s
        n = s.count(old)
        assert n == count, (n, old[:120])
        s = s.replace(old, new)

    def sub_re(pattern, new, count):
        nonlocal s
        s, n = re.subn(pattern, new, s, flags=re.I)
        assert n == count, (n, pattern[:120])

    s = ("* EMP form of distillation_model_corrected.gms, written by\n"
         "* experiments/catalytic_distillation_minlp/make_emp.py; do not edit by hand.\n"
         "* The stage decisions are binary variables; solve_emp.gms declares the disjunctions,\n"
         "* and emp_scales.gms holds the scales s of the disjunct constraints.\n" + s)

    # Decisions become binary variables; par is linked to yb by the published definition.
    sub('parameter yc(Net) "1 if the stage holds catalyst";', 'binary variable yc(Net) "1 if the stage holds catalyst";')
    sub('parameter yb(Net) "1 if the boil-up returns to the stage";',
        'binary variable yb(Net) "1 if the boil-up returns to the stage";')
    sub('parameter par(Net) "1 if the stage physically exists";\npar(\'1\')=1;\npar(Net)$(ord(Net) eq card(Net))=1;',
        'binary variable par(Net) "1 if the stage physically exists";\npar.fx(\'1\')=1;\n'
        'par.fx(Net)$(ord(Net) eq card(Net))=1;')
    sub('parameter ye(Net) "1 if the stage is an equilibrium stage";\n', "")
    sub('parameter yf1(Net) "1 if the ethanol feed enters the stage";',
        'binary variable yf1(Net) "1 if the ethanol feed enters the stage";')
    sub('parameter yf2(Net) "1 if the butenes feed enters the stage";',
        'binary variable yf2(Net) "1 if the butenes feed enters the stage";\n'
        '* The condenser and the reboiler hold no feed, catalyst, or boil-up return.\n'
        'yf1.fx(Net)$(ord(Net) eq 1 or ord(Net) eq card(Net))=0;\n'
        'yf2.fx(Net)$(ord(Net) eq 1 or ord(Net) eq card(Net))=0;\n'
        'yc.fx(Net)$(ord(Net) eq 1 or ord(Net) eq card(Net))=0;\n'
        'yb.fx(Net)$(ord(Net) eq 1 or ord(Net) eq card(Net))=0;\n'
        'equation def_par(Net) "Stages from the reflux down to the boil-up stage exist";\n'
        f'def_par(Net)$({INTERNAL}).. par(Net)=e=(sum(Net1$((ord(Net1) ge 2) and (ord(Net1) le ord(Net))),yr(Net1)))'
        '+(yb(Net))-(sum(Net1$((ord(Net1) ge 2) and (ord(Net1) le ord(Net))),yb(Net1)));')

    # Every switched equation exists; the disjunctions decide where it binds.
    sub_re(r"\$\(par\(net\) eq 1\)\.\.", "..", 25)
    sub("no_hs_stage(net)$(par(Net) eq 0)..", f"no_hs_stage(net)$({INTERNAL})..")
    sub_re(r" and yc\(net\) eq 1\)", ")", 7)
    sub_re(r" and yc\(net\) eq 0\)", ")", 1)
    sub_re(r" and yf2\(net\) eq 1\)", ")", 1)
    sub_re(r" and yf1\(net\) eq 1\)", ")", 1)
    sub_re(r" and par\(net\) eq 1\)", ")", 15)
    sub_re(r" and par\(net\) eq 0\)", ")", 1)
    sub_re(r" and ye\(net\) eq 1\)", ")", 1)
    sub_re(r" and \(1-ye\(Net\)\) eq 1\)", ")", 2)
    sub("0=e=(1-ye(Net))*(V('1','1',Net)-V('1','1',Net+1)-boilup_flow(net,net1));",
        "0=e=V('1','1',Net)-V('1','1',Net+1)-boilup_flow(net,net1);")
    for name, y in [("eq_ETin", "yf1"), ("eq_BUTin", "yf2"), ("eq_reaction_term", "yc")]:
        sub(f"{name}(net)$({y}(net) eq 1)..", f"{name}(net)$({INTERNAL})..")
    sub("eq_partial_reaction_term(net,comp)$(yc(net) eq 1)..", f"eq_partial_reaction_term(net,comp)$({INTERNAL})..")
    for name, y in [("no_ETin", "yf1"), ("no_BUTin", "yf2"), ("no_reaction_term", "yc")]:
        sub(f"{name}(net)$({y}(net) eq 0)..", f"{name}(net)..")
    sub("no_partial_reaction_term(net,comp)$(yc(net) eq 0)..", "no_partial_reaction_term(net,comp)..")
    sub("eq_boilup_flow(net,net1)$(ord(net1) eq card(net1) and yb(net) eq 1)..",
        f"eq_boilup_flow(net,net1)$(ord(net1) eq card(net1) and {INTERNAL})..")
    sub("no_boilup_flow(net,net1)$(ord(net1) eq card(net1) and yb(net) eq 0)..", "no_boilup_flow(net,net1)$(ord(net1) eq card(net1))..")
    sub("EqTcat(Net)$(yc(Net) eq 1)..", f"EqTcat(Net)$({INTERNAL})..")
    sub("catflood(N,j,net)$(yc(net) eq 1)..", f"catflood(N,j,net)$({INTERNAL})..")
    # EntrainFloodL ends without a semicolon in the source, which GAMS accepts before a declaration.
    sub("=l=0\n*Weeping", "=l=0;\n*Weeping")

    # The initial configuration becomes the starting point of the binaries.
    for name in ["yb", "yc", "yf1", "yf2"]:
        sub(f"\n{name}(Net)=0;", f"\n{name}.l(Net)=0;")
    for stage, name in [("9", "yb"), ("3", "yf1"), ("8", "yf2"), ("4", "yc"), ("5", "yc"), ("6", "yc")]:
        sub(f"\n{name}('{stage}')=1;", f"\n{name}.l('{stage}')=1;")
    sub("par(Net)$((ord(Net) ne card(Net)) and (ord(Net) ne 1))=(sum(Net1$((ord(Net1) ge 2) and (ord(Net1) le ord(Net))),yr(Net1)))+(yb(Net))-(sum(Net1$((ord(Net1) ge 2) and (ord(Net1) le ord(Net))),yb(Net1)));",
        "par.l(Net)$((ord(Net) ne card(Net)) and (ord(Net) ne 1))=(sum(Net1$((ord(Net1) ge 2) and (ord(Net1) le ord(Net))),yr(Net1)))+(yb.l(Net))-(sum(Net1$((ord(Net1) ge 2) and (ord(Net1) le ord(Net))),yb.l(Net1)));")
    sub("ye(Net)$((ord(Net) ne card(Net)) and (ord(Net) ne 1))=par(Net)*(1-yc(Net))*CASE+par(Net)*(1-CASE);\n", "")

    leftover = re.findall(r"\b(?:par|ye|yc|yb|yf1|yf2)\(net\)\)? eq [01]", s, flags=re.I)
    assert not leftover, leftover

    # Mass densities: the source bounds allow a vapor denser than the liquid, where the flooding and
    # weeping correlations are unbounded, so the densities get bounds that keep the liquid denser.
    sub("*Catalyst characteristics\n",
        'positive variables rhoLm(N,j,Net) "Liquid mass density [kg/m3]", rhoVm(N,j,Net) "Vapor mass density [kg/m3]";\n'
        "equations def_rhoLm(N,j,Net), def_rhoVm(N,j,Net);\n"
        f"def_rhoLm(N,j,Net)$({INTERNAL}).. rhoLm(N,j,Net)=e={next(iter(MASS_DENSITIES))};\n"
        f"def_rhoVm(N,j,Net)$({INTERNAL}).. rhoVm(N,j,Net)=e={list(MASS_DENSITIES)[1]};\n"
        "rhoLm.lo(N,j,Net)=200;\n"
        "rhoVm.lo(N,j,Net)=5;\n"
        "rhoVm.up(N,j,Net)=150;\n"
        "*Catalyst characteristics\n")

    # Disjunct constraints: linear, scaled, and equalities as inequality pairs.
    for name in FAMILIES:
        s, _ = disjunct_equation(s, name, name in LIFTED)

    # Bounds implied by the disjunctions, so that the convex hull bounds every disaggregated variable.
    sub("model DSDA /all/;",
        "* Bounds implied by the disjunctions and by EqHwmin.\n"
        "ETin.up(Net)=FE;\n"
        "BUTin.up(Net)=FB;\n"
        "boilup_flow.up(Net,Net1)$(ord(Net1) eq card(Net1))=BR.up('1','1')*L.up('1','1',Net1);\n"
        "reaction_term.lo(Net)=min(0,sum(comp,Nu(comp))*mcat*Rx.lo('1','1',Net),sum(comp,Nu(comp))*mcat*Rx.up('1','1',Net));\n"
        "reaction_term.up(Net)=max(0,sum(comp,Nu(comp))*mcat*Rx.lo('1','1',Net),sum(comp,Nu(comp))*mcat*Rx.up('1','1',Net));\n"
        "partial_reaction_term.lo(Net,comp)=min(0,Nu(comp)*mcat*Rx.lo('1','1',Net),Nu(comp)*mcat*Rx.up('1','1',Net));\n"
        "partial_reaction_term.up(Net,comp)=max(0,Nu(comp)*mcat*Rx.lo('1','1',Net),Nu(comp)*mcat*Rx.up('1','1',Net));\n"
        "HS.up=hw.up/0.05;\n"
        "hs_stage.up(Net)=HS.up;\n"
        "model DSDA /all/;")
    return s


if __name__ == "__main__":
    TARGET.write_text(build(SOURCE.read_text()))
    print(f"wrote {TARGET.relative_to(ROOT)}")
