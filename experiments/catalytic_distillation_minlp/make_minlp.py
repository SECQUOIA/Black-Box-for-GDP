"""Write the MINLP form of the corrected catalytic distillation column.

  python experiments/catalytic_distillation_minlp/make_minlp.py

Reads gdp_models/catalytic_distillation/distillation_model_corrected.gms, where the
stage decisions are parameters that switch equations on and off, and writes
minlp_model_corrected.gms, where they are binary variables.  The construction follows
the published MINLP form (SECQUOIA/dsda-gdp, dsda-minlp-cd-column) and is exact for
binary values:

- property, kinetic, and feed-enthalpy equations hold on every stage;
- switched pairs become products, e.g. ETin = yf1*FE and boilup_flow = yb*BR*L;
- equilibrium and stage-existence relations are multiplied by ye and par, which are
  variables defined by the published linear expressions;
- the catalyst temperature limit holds through a big-M term with Temp.up.

The reflux stage is fixed at stage 2 in both forms, so yr stays a parameter.
"""

from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
FOLDER = ROOT / "gdp_models/catalytic_distillation"
SOURCE = FOLDER / "distillation_model_corrected.gms"
TARGET = FOLDER / "minlp_model_corrected.gms"
INTERNAL = "ord(Net)>1 and ord(Net)<card(Net)"


def build(text):
    s = text.replace("\r\n", "\n")

    def sub(old, new, count=1):
        nonlocal s
        n = s.count(old)
        assert n == count, (n, old[:120])
        s = s.replace(old, new)

    def sub_re(pattern, new, count=1):
        nonlocal s
        s, n = re.subn(pattern, new, s, flags=re.I)
        assert n == count, (n, pattern[:120])

    # Header.
    s = ("* MINLP form of distillation_model_corrected.gms, written by\n"
         "* experiments/catalytic_distillation_minlp/make_minlp.py; do not edit by hand.\n"
         "* The stage decisions yf1, yc, yf2, and yb are binary variables, and par and ye are\n"
         "* variables defined by the linear expressions of the published MINLP form.\n" + s)

    # Discrete decisions become variables.
    sub('parameter yc(Net) "1 if the stage holds catalyst";', 'binary variable yc(Net) "1 if the stage holds catalyst";')
    sub('parameter yb(Net) "1 if the boil-up returns to the stage";',
        'binary variable yb(Net) "1 if the boil-up returns to the stage";')
    sub('parameter par(Net) "1 if the stage physically exists";\npar(\'1\')=1;\npar(Net)$(ord(Net) eq card(Net))=1;',
        'positive variable par(Net) "1 if the stage physically exists";\npar.up(Net)=1;\npar.fx(\'1\')=1;\n'
        'par.fx(Net)$(ord(Net) eq card(Net))=1;')
    sub('parameter ye(Net) "1 if the stage is an equilibrium stage";',
        'positive variable ye(Net) "1 if the stage is an equilibrium stage";\nye.up(Net)=1;\n'
        'ye.fx(Net)$(ord(Net) eq 1 or ord(Net) eq card(Net))=1;')
    sub('parameter yf1(Net) "1 if the ethanol feed enters the stage";',
        'binary variable yf1(Net) "1 if the ethanol feed enters the stage";')
    sub('parameter yf2(Net) "1 if the butenes feed enters the stage";',
        'binary variable yf2(Net) "1 if the butenes feed enters the stage";\n'
        '* The condenser and the reboiler hold no feed, catalyst, or boil-up return.\n'
        'yf1.fx(Net)$(ord(Net) eq 1 or ord(Net) eq card(Net))=0;\n'
        'yf2.fx(Net)$(ord(Net) eq 1 or ord(Net) eq card(Net))=0;\n'
        'yc.fx(Net)$(ord(Net) eq 1 or ord(Net) eq card(Net))=0;\n'
        'yb.fx(Net)$(ord(Net) eq 1 or ord(Net) eq card(Net))=0;\n'
        'equations def_par(Net) "Stages from the reflux down to the boil-up stage exist",\n'
        '          def_ye(Net) "Existing stages are equilibrium stages (CASE=0)";\n'
        f'def_par(Net)$({INTERNAL}).. par(Net)=e=(sum(Net1$((ord(Net1) ge 2) and (ord(Net1) le ord(Net))),yr(Net1)))'
        '+(yb(Net))-(sum(Net1$((ord(Net1) ge 2) and (ord(Net1) le ord(Net))),yb(Net1)));\n'
        f'def_ye(Net)$({INTERNAL}).. ye(Net)=e=par(Net)*(1-yc(Net))*CASE+par(Net)*(1-CASE);')

    # Stage height counts existing stages only.
    sub("eq_hs_stage(net)$(par(Net) eq 1)..hs_Stage(net)=e=HS;", "eq_hs_stage(net)..hs_Stage(net)=e=par(Net)*HS;")
    sub("no_hs_stage(net)$(par(Net) eq 0)..hs_Stage(net)=e=0;\n", "")
    sub("equation eq_hs_stage(net),no_hs_stage(net);", "equation eq_hs_stage(net);")

    # Property equations hold on every stage.
    s, n = re.subn(r"\$\(par\(net\) eq 1\)\.\.", "..", s, flags=re.I)
    assert n == 24, n
    # Kinetics and feed enthalpies hold on every internal stage.
    for name, y in [("EqKetbe", "yc"), ("EqKrate", "yc"), ("EqKa", "yc"), ("EqRx", "yc"),
                    ("EqHFB", "yf2"), ("EqHFE", "yf1")]:
        sub_re(rf"({name}\(N,j,Net\)\$\(\(ord\(Net\) ne card\(Net\)\) and \(ord\(Net\) ne 1\)) and {y}\(net\) eq 1\)",
               r"\1)")

    # Switched pairs become products.
    sub("eq_ETin(net)$(yf1(net) eq 1)..ETin(net)=e=FE;", "eq_ETin(net)..ETin(net)=e=yf1(net)*FE;")
    sub("eq_BUTin(net)$(yf2(net) eq 1)..BUTin(net)=e=FB;", "eq_BUTin(net)..BUTin(net)=e=yf2(net)*FB;")
    sub("eq_boilup_flow(net,net1)$(ord(net1) eq card(net1) and yb(net) eq 1)..boilup_flow(net,net1)=e=BR('1','1')*L('1','1',Net1);",
        "eq_boilup_flow(net,net1)$(ord(net1) eq card(net1))..boilup_flow(net,net1)=e=yb(net)*BR('1','1')*L('1','1',Net1);")
    sub("eq_reaction_term(net)$(yc(net) eq 1)..reaction_term(net)=e=(sum(comp,Nu(comp))*mcat*Rx('1','1',Net));",
        "eq_reaction_term(net)..reaction_term(net)=e=yc(net)*(sum(comp,Nu(comp))*mcat*Rx('1','1',Net));")
    sub("eq_partial_reaction_term(net,comp)$(yc(net) eq 1)..partial_reaction_term(net,comp)=e=(Nu(comp)*mcat*Rx('1','1',Net));",
        "eq_partial_reaction_term(net,comp)..partial_reaction_term(net,comp)=e=yc(net)*(Nu(comp)*mcat*Rx('1','1',Net));")
    for line in ["no_ETin(net)$(yf1(net) eq 0)..ETin(net)=e=0;\n", "no_BUTin(net)$(yf2(net) eq 0)..BUTin(net)=e=0;\n",
                 "no_boilup_flow(net,net1)$(ord(net1) eq card(net1) and yb(net) eq 0)..boilup_flow(net,net1)=e=0;\n",
                 "no_reaction_term(net)$(yc(net) eq 0)..reaction_term(net)=e=0;\n",
                 "no_partial_reaction_term(net,comp)$(yc(net) eq 0)..partial_reaction_term(net,comp)=e=0;\n"]:
        sub(line, "")
    sub("equations no_ETin(net),no_BUTin(net),no_reflux_flow(net),no_boilup_flow(net,net1),no_reaction_term(net);",
        "equations no_reflux_flow(net);")
    sub("equation eq_partial_reaction_term(net,comp),no_partial_reaction_term(net,comp);",
        "equation eq_partial_reaction_term(net,comp);")

    # Equilibrium relations hold on equilibrium stages (ye) and pass-through relations elsewhere.
    sub_re(r"Equilibrio10\(comp,Net\)\$\(ord\(Net\)>1 and ord\(Net\)<card\(Net\) and ye\(net\) eq 1\)\.\.0=e=\(",
           f"Equilibrio10(comp,Net)$({INTERNAL})..0=e=ye(Net)*(")
    sub_re(r"(Equilibrio20\(comp,Net\)\$\(.*? eq 1) and \(1-ye\(Net\)\) eq 1\)\.\.0=e=\(", r"\1)..0=e=(1-ye(Net))*(")
    sub_re(r"(Equilibrio30\(comp,Net\)\$\(.*? eq 1) and \(1-ye\(Net\)\) eq 1\)\.\.0=e=\(", r"\1)..0=e=(1-ye(Net))*(")

    # Catalyst temperature limit with a big-M term.
    sub("EqTcat(Net)$(yc(Net) eq 1).. Temp('1','1',Net) =l= Tcatmax;",
        f"EqTcat(Net)$({INTERNAL}).. Temp('1','1',Net) =l= Tcatmax+(Temp.up('1','1',Net)-Tcatmax)*(1-yc(Net));")

    # Hydraulic definitions on existing stages: par*(lhs) = par*(rhs), as in the published MINLP form.
    for name in ["Eqfa", "EqhD", "Equhv", "Equnv", "Equl", "Eqhcl", "EqCsbf", "EqDPL", "EqDPS", "EqDPq"]:
        pattern = rf"({name}\(N,j,Net\)\$\(ord\(Net\)>1 and ord\(Net\)<card\(Net\)) and par\(net\) eq 1\)\.\. *(.*?)=e=(.*?);\n"
        m = re.search(pattern, s, flags=re.I | re.S)
        assert m, name
        s = s[:m.start()] + f"{m.group(1)}).. par(Net)*({m.group(2).strip()})=e=par(Net)*({m.group(3).strip()});\n" + s[m.end():]
    # Catalyst hydraulics are defined on every internal stage; the pressure drop is multiplied by yc.
    for name in ["eqLload", "eqFfactor"]:
        sub_re(rf"({name}\(N,j,Net\)\$\(ord\(Net\)>1 and ord\(Net\)<card\(Net\)) and yc\(net\) eq 1\)", r"\1)")
    sub_re(r"EqdPcat\(N,j,net\)\$\(ord\(Net\)>1 and ord\(Net\)<card\(Net\) and yc\(net\) eq 1\)\.\.dPcat\(N,j,net\)=e=",
           f"EqdPcat(N,j,net)$({INTERNAL})..dPcat(N,j,net)=e=yc(net)*")
    sub("NodPcat(N,j,net)$(ord(Net)>1 and ord(Net)<card(Net) and yc(net) eq 0)..dPcat(N,j,net)=e=0;\n", "")
    sub("EqDP(N,j,Net)$(ord(Net)>1 and ord(Net)<card(Net) and par(net) eq 1).. (DP(N,j,Net))=e=(DPS(N,j,Net)+DPL(N,j,Net))+dPcat(N,j,net);",
        f"EqDP(N,j,Net)$({INTERNAL}).. (DP(N,j,Net))=e=par(Net)*((DPS(N,j,Net)+DPL(N,j,Net))+dPcat(N,j,net));")
    sub("NoDP(N,j,Net)$(ord(Net)>1 and ord(Net)<card(Net) and par(net) eq 0)..DP(N,j,Net)=e=0;\n", "")
    sub("EqDP(N,j,Net),NoDP(N,j,Net),EqDPR(N,j,Net),EqdPcat(N,j,net),NodPcat(N,j,net),",
        "EqDP(N,j,Net),EqDPR(N,j,Net),EqdPcat(N,j,net),")
    # Flooding and weeping bind only on existing stages.
    sub_re(r"(DownFlood\(N,j,Net\)\$\(ord\(Net\)>1 and ord\(Net\)<card\(Net\)) and par\(net\) eq 1\)\.\.0=g=\(",
           r"\1)..0=g=par(Net)*(")
    for name in ["EntrainFloodV", "EntrainFloodL"]:
        # EntrainFloodL ends without a semicolon in the source, which GAMS accepts before a declaration.
        pattern = rf"({name}\(N,j,Net\)\$\(ord\(Net\)>1 and ord\(Net\)<card\(Net\)) and par\(net\) eq 1\)\.\.(.*?)=l=0;?\n"
        m = re.search(pattern, s, flags=re.I | re.S)
        assert m, name
        s = s[:m.start()] + f"{m.group(1)}).. par(Net)*({m.group(2).strip()})=l=0;\n" + s[m.end():]
    sub_re(r"(Weep\(N,j,Net\)\$\(ord\(Net\)>1 and ord\(Net\)<card\(Net\)) and par\(net\) eq 1\)\.\. 0=g=\(",
           r"\1).. 0=g=par(Net)*(")
    sub("catflood(N,j,net)$(yc(net) eq 1)..", f"catflood(N,j,net)$({INTERNAL})..")

    # The initial configuration becomes the starting point of the binaries.
    for name in ["yb", "yc", "yf1", "yf2"]:
        sub(f"\n{name}(Net)=0;", f"\n{name}.l(Net)=0;")
    for stage, name in [("9", "yb"), ("3", "yf1"), ("8", "yf2"), ("4", "yc"), ("5", "yc"), ("6", "yc")]:
        sub(f"\n{name}('{stage}')=1;", f"\n{name}.l('{stage}')=1;")
    sub("par(Net)$((ord(Net) ne card(Net)) and (ord(Net) ne 1))=(sum(Net1$((ord(Net1) ge 2) and (ord(Net1) le ord(Net))),yr(Net1)))+(yb(Net))-(sum(Net1$((ord(Net1) ge 2) and (ord(Net1) le ord(Net))),yb(Net1)));",
        "par.l(Net)$((ord(Net) ne card(Net)) and (ord(Net) ne 1))=(sum(Net1$((ord(Net1) ge 2) and (ord(Net1) le ord(Net))),yr(Net1)))+(yb.l(Net))-(sum(Net1$((ord(Net1) ge 2) and (ord(Net1) le ord(Net))),yb.l(Net1)));")
    sub("ye(Net)$((ord(Net) ne card(Net)) and (ord(Net) ne 1))=par(Net)*(1-yc(Net))*CASE+par(Net)*(1-CASE);",
        "ye.l(Net)$((ord(Net) ne card(Net)) and (ord(Net) ne 1))=par.l(Net)*(1-yc.l(Net))*CASE+par.l(Net)*(1-CASE);")

    leftover = re.findall(r"\b(?:par|ye|yc|yb|yf1|yf2)\(net\) eq [01]", s, flags=re.I)
    assert not leftover, leftover
    return s


if __name__ == "__main__":
    TARGET.write_text(build(SOURCE.read_text()))
    print(f"wrote {TARGET.relative_to(ROOT)}")
