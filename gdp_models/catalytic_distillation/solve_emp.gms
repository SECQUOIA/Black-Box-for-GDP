* Solve the disjunctive (EMP) form of the corrected column (emp_model_corrected.gms) through GAMS/JAMS.
*
* Usage: gams solve_emp.gms --reform=bigm --solver=dicopt [--reslim=3600] [--init=init]
*                            [--out=result.txt] [--gdx=solution.gdx]
*        gams solve_emp.gms --reform=chull --solver=sbb --f1=7 --c1=8 --c2=11 --c3=16 --f2=16 --b=20 [...]
*
* --reform is bigm or chull (Big-M or convex hull reformulation by JAMS).  For each internal stage,
* the disjunctions are those encoded by the parameters of distillation_model_corrected.gms:
*   par  stage exists: equilibrium, tray hydraulics, height    else vapor passes, no pressure drop
*   yc   catalyst: kinetics, catalyst hydraulics, reaction,    else no reaction or catalyst drop
*        120 C limit
*   yf1, yf2  feed enters the stage: flow                      else no flow
*   yb   boil-up returns to the stage: flow                    else no flow
* Every disjunct constraint is linear and scaled by emp_scales.gms to lie in [-1, 1] at every
* feasible point, so M = 1 is a valid Big-M; disjunct equalities are the pairs F and F_ge (see
* experiments/catalytic_distillation_minlp/make_emp.py).  For the convex hull, --big bounds the
* disaggregated variables that have no bound of their own and must exceed every variable bound.
* Every equation goes on its own line of the EMP file, whose lines are limited to 1,020 characters.
* With --f1 ... --b, the binaries are fixed to that configuration, which checks the reformulation
* against the GDP form of solve_configuration.gms.

$if not set model  $set model  emp_model_corrected.gms
$setnames "%model%" modelpath modelname modelext
$if not set scales $set scales %modelpath%emp_scales.gms
$if not set reform $set reform bigm
$if not set solver $set solver dicopt
$ifthen.reform %reform%==chull
$  if not set big  $set big    1e5
$else.reform
$  if not set big  $set big    1
$endif.reform
$if not set eps    $set eps    1e-4
$if not set reslim $set reslim 3600
$if not set init   $set init   init
$if not set out    $set out    emp_result.txt

$include "%model%"
$include "%scales%"

execute_loadpoint "%init%";
yb.l(Net) = 0;
yc.l(Net) = 0;
yf1.l(Net) = 0;
yf2.l(Net) = 0;
$ifthen set f1
yf1.l('%f1%') = 1;
yc.l('%c1%') = 1;
yc.l('%c2%') = 1;
yc.l('%c3%') = 1;
yf2.l('%f2%') = 1;
yb.l('%b%') = 1;
yf1.fx(Net) = yf1.l(Net);
yc.fx(Net) = yc.l(Net);
yf2.fx(Net) = yf2.l(Net);
yb.fx(Net) = yb.l(Net);
$else
yf1.l('3') = 1;
yc.l('4') = 1;
yc.l('5') = 1;
yc.l('6') = 1;
yf2.l('8') = 1;
yb.l('9') = 1;
$endif
par.l(Net)$((ord(Net) ne card(Net)) and (ord(Net) ne 1)) = (sum(Net1$((ord(Net1) ge 2) and (ord(Net1) le ord(Net))), yr(Net1))) + (yb.l(Net)) - (sum(Net1$((ord(Net1) ge 2) and (ord(Net1) le ord(Net))), yb.l(Net1)));
rhoLm.l(N,j,Net) = rhoL.l(N,j,Net)*sum(comp, MW(comp)*x.l(N,j,comp,Net)/100)/1000;
rhoVm.l(N,j,Net) = rhoV.l(N,j,Net)*sum(comp, MW(comp)*y.l(N,j,comp,Net)/100)/1000;

set inner(Net) "internal stages, where the stage decisions are made";
inner(Net) = ord(Net) > 1 and ord(Net) < card(Net);
set last(Net) "reboiler stage";
last(Net) = ord(Net) eq card(Net);
alias (comp, compB);

file emp / '%emp.info%' /;
emp.pw = 1000;
put emp;
$ifthen %reform%==chull
put 'default chull %big% %eps%' /;
$else
put 'default bigm %big%' /;
$endif
loop(inner(Net),
* Stage exists: equilibrium, tray hydraulics, flooding, weeping, and stage height.
   put 'disjunction ' par(Net);
   loop((N,j), put / ' ' Eqfa(N,j,Net) / ' ' Eqfa_ge(N,j,Net) / ' ' EqhD(N,j,Net) / ' ' EqhD_ge(N,j,Net)
                   / ' ' Equhv(N,j,Net) / ' ' Equhv_ge(N,j,Net) / ' ' Equnv(N,j,Net) / ' ' Equnv_ge(N,j,Net)
                   / ' ' Equl(N,j,Net) / ' ' Equl_ge(N,j,Net) / ' ' Eqhcl(N,j,Net) / ' ' Eqhcl_ge(N,j,Net)
                   / ' ' EqCsbf(N,j,Net) / ' ' EqCsbf_ge(N,j,Net) / ' ' EqDPL(N,j,Net) / ' ' EqDPL_ge(N,j,Net)
                   / ' ' EqDPS(N,j,Net) / ' ' EqDPS_ge(N,j,Net) / ' ' EqDPq(N,j,Net) / ' ' EqDPq_ge(N,j,Net)
                   / ' ' EqDP(N,j,Net) / ' ' EqDP_ge(N,j,Net) / ' ' DownFlood(N,j,Net) / ' ' EntrainFloodV(N,j,Net)
                   / ' ' EntrainFloodL(N,j,Net) / ' ' Weep(N,j,Net));
   loop(comp, put / ' ' Equilibrio10(comp,Net) / ' ' Equilibrio10_ge(comp,Net));
   put / ' ' eq_hs_stage(Net) / ' ' eq_hs_stage_ge(Net) / ' else';
   loop(comp$(ord(comp) ne 1), put / ' ' Equilibrio20(comp,Net) / ' ' Equilibrio20_ge(comp,Net));
   loop(last, put / ' ' Equilibrio40(Net,last) / ' ' Equilibrio40_ge(Net,last));
   loop((N,j), put / ' ' NoDP(N,j,Net) / ' ' NoDP_ge(N,j,Net));
   put / ' ' no_hs_stage(Net) / ' ' no_hs_stage_ge(Net) /;
* Catalyst on the stage: kinetics, catalyst hydraulics, reaction, and temperature limit.
   put 'disjunction ' yc(Net);
   loop((N,j), put / ' ' EqKetbe(N,j,Net) / ' ' EqKetbe_ge(N,j,Net) / ' ' EqKrate(N,j,Net) / ' ' EqKrate_ge(N,j,Net)
                   / ' ' EqKa(N,j,Net) / ' ' EqKa_ge(N,j,Net) / ' ' EqRx(N,j,Net) / ' ' EqRx_ge(N,j,Net)
                   / ' ' eqLload(N,j,Net) / ' ' eqLload_ge(N,j,Net) / ' ' eqFfactor(N,j,Net) / ' ' eqFfactor_ge(N,j,Net)
                   / ' ' EqdPcat(N,j,Net) / ' ' EqdPcat_ge(N,j,Net) / ' ' catflood(N,j,Net));
   put / ' ' eq_reaction_term(Net) / ' ' eq_reaction_term_ge(Net);
   loop(comp, put / ' ' eq_partial_reaction_term(Net,comp) / ' ' eq_partial_reaction_term_ge(Net,comp));
   put / ' ' EqTcat(Net) / ' else' / ' ' no_reaction_term(Net) / ' ' no_reaction_term_ge(Net);
   loop(comp, put / ' ' no_partial_reaction_term(Net,comp) / ' ' no_partial_reaction_term_ge(Net,comp));
   loop((N,j), put / ' ' NodPcat(N,j,Net) / ' ' NodPcat_ge(N,j,Net));
   put /;
* Feeds and boil-up return.
   put 'disjunction ' yf1(Net) / ' ' eq_ETin(Net) / ' ' eq_ETin_ge(Net) / ' else' / ' ' no_ETin(Net) / ' ' no_ETin_ge(Net) /;
   put 'disjunction ' yf2(Net) / ' ' eq_BUTin(Net) / ' ' eq_BUTin_ge(Net) / ' else' / ' ' no_BUTin(Net) / ' ' no_BUTin_ge(Net) /;
   loop(last, put 'disjunction ' yb(Net) / ' ' eq_boilup_flow(Net,last) / ' ' eq_boilup_flow_ge(Net,last)
                  / ' else' / ' ' no_boilup_flow(Net,last) / ' ' no_boilup_flow_ge(Net,last) /);
);
putclose emp;

$onecho > jams.opt
SubSolver %solver%
FileName reformulated_%reform%.gms
$offecho
DSDA.optfile = 1;
option nlp = conopt, mip = cplex, minlp = %solver%, threads = 1;
DSDA.optcr = 0;
DSDA.reslim = %reslim%;
solve DSDA using emp minimizing zobj;

* Configuration of the returned point, in stage positions.
scalar f1pos, c1pos, c2pos, c3pos, f2pos, bpos, ncat;
f1pos = sum(Net$(yf1.l(Net) > 0.5), ord(Net));
f2pos = sum(Net$(yf2.l(Net) > 0.5), ord(Net));
bpos = sum(Net$(yb.l(Net) > 0.5), ord(Net));
ncat = sum(Net$(yc.l(Net) > 0.5), 1);
c1pos = smin(Net$(yc.l(Net) > 0.5), ord(Net));
c3pos = smax(Net$(yc.l(Net) > 0.5), ord(Net));
c2pos = sum(Net$(yc.l(Net) > 0.5 and ord(Net) > c1pos and ord(Net) < c3pos), ord(Net));

file result /"%out%"/;
result.nd = 10;
put result;
put "reform=%reform% big=%big% solver=%solver% modelstat=" DSDA.modelstat:0:0 " solvestat=" DSDA.solvestat:0:0;
put " zobj=" zobj.l:0:6 " objest=" DSDA.objest:0:6 " resusd=" DSDA.resusd:0:4;
put " f1=" f1pos:0:0 " c1=" c1pos:0:0 " c2=" c2pos:0:0 " c3=" c3pos:0:0 " f2=" f2pos:0:0 " b=" bpos:0:0 " ncat=" ncat:0:0;
put " maxfrac=" smax(Net, abs(yf1.l(Net) - round(yf1.l(Net))) + abs(yc.l(Net) - round(yc.l(Net))) + abs(yb.l(Net) - round(yb.l(Net)))):0:6;
put " xETBE=" x.l('1','1','ETBE','22'):0:6;
put " rhoLmin=" smin((N,j,inner), rhoLm.l(N,j,inner)):0:3 " rhoVmax=" smax((N,j,inner), rhoVm.l(N,j,inner)):0:3 /;
putclose result;
$if set gdx execute_unload "%gdx%";
