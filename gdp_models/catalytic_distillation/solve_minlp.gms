* Solve the MINLP form of the corrected column (minlp_model_corrected.gms).
*
* Usage: gams solve_minlp.gms --solver=dicopt [--reslim=3600] [--init=init] [--out=result.txt] [--gdx=solution.gdx]
*        gams solve_minlp.gms --f1=7 --c1=8 --c2=11 --c3=16 --f2=16 --b=20 [...]
*
* Without --f1, a MINLP solver (DICOPT, SBB, BARON, SCIP, ...) optimizes over all configurations,
* starting from init.gdx and the configuration (3,4,5,6,8,9) stored in it.  With --f1 ... --b,
* the binaries are fixed to that configuration and CONOPT solves the remaining NLP, which
* checks the MINLP form against the GDP form of solve_configuration.gms.

$if not set model  $set model  minlp_model_corrected.gms
$if not set solver $set solver dicopt
$if not set reslim $set reslim 3600
$if not set init   $set init   init
$if not set out    $set out    minlp_result.txt

$include %model%

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
ye.l(Net)$((ord(Net) ne card(Net)) and (ord(Net) ne 1)) = par.l(Net)*(1-yc.l(Net))*CASE + par.l(Net)*(1-CASE);

option nlp = conopt, mip = cplex, threads = 1;
DSDA.optcr = 0;
DSDA.reslim = %reslim%;
$ifthen set f1
solve DSDA using rminlp minimizing zobj;
$else
option minlp = %solver%;
solve DSDA using minlp minimizing zobj;
$endif

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
put "solver=%solver% modelstat=" DSDA.modelstat:0:0 " solvestat=" DSDA.solvestat:0:0;
put " zobj=" zobj.l:0:6 " objest=" DSDA.objest:0:6 " resusd=" DSDA.resusd:0:4;
put " numequ=" DSDA.numequ:0:0 " numvar=" DSDA.numvar:0:0 " numdvar=" DSDA.numdvar:0:0;
put " f1=" f1pos:0:0 " c1=" c1pos:0:0 " c2=" c2pos:0:0 " c3=" c3pos:0:0 " f2=" f2pos:0:0 " b=" bpos:0:0 " ncat=" ncat:0:0;
put " maxfrac=" smax(Net, min(abs(yf1.l(Net) - round(yf1.l(Net))), 1) + abs(yc.l(Net) - round(yc.l(Net))) + abs(yb.l(Net) - round(yb.l(Net)))):0:6;
put " xETBE=" x.l('1','1','ETBE','22'):0:6 /;
putclose result;
$if set gdx execute_unload "%gdx%";
