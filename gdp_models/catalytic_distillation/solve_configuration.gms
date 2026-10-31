* Solve the catalytic distillation NLP for one configuration of the external variables.
*
* Usage: gams solve_configuration.gms --f1=4 --c1=4 --c2=6 --c3=8 --f2=8 --b=10
*        [--solver=conopt] [--init=init] [--out=result.txt] [--model=distillation_model.gms] [--gdx=solution.gdx]
*
* f1: ethanol feed stage, c1<c2<c3: catalytic stages, f2: butenes feed stage,
* b: boil-up stage; the reflux returns to stage 2.  Admissible configurations
* satisfy 2 <= f1 <= c1 < c2 < c3 <= f2 <= b <= 21.  Every solve starts from the
* same initialization file, so the response does not depend on earlier solves.

$if not set model  $set model  distillation_model.gms
$if not set solver $set solver conopt
$if not set init   $set init   init
$if not set out    $set out    result.txt

$include %model%

yb(Net) = 0;
yc(Net) = 0;
yf1(Net) = 0;
yf2(Net) = 0;
yf1('%f1%') = 1;
yc('%c1%') = 1;
yc('%c2%') = 1;
yc('%c3%') = 1;
yf2('%f2%') = 1;
yb('%b%') = 1;

* Dependent indicators, as in DISTILLATION.gms.
par(Net)$((ord(Net) ne card(Net)) and (ord(Net) ne 1)) = (sum(Net1$((ord(Net1) ge 2) and (ord(Net1) le ord(Net))), yr(Net1))) + (yb(Net)) - (sum(Net1$((ord(Net1) ge 2) and (ord(Net1) le ord(Net))), yb(Net1)));
ye(Net)$((ord(Net) ne card(Net)) and (ord(Net) ne 1)) = par(Net)*(1-yc(Net))*CASE + par(Net)*(1-CASE);

execute_loadpoint "%init%";
option nlp = %solver%;
solve DSDA using nlp minimizing zobj;

file result /"%out%"/;
result.nd = 10;
put result;
put "f1=%f1% c1=%c1% c2=%c2% c3=%c3% f2=%f2% b=%b% solver=%solver%";
put " modelstat=" DSDA.modelstat:0:0 " solvestat=" DSDA.solvestat:0:0;
put " zobj=" zobj.l:0:6 " resusd=" DSDA.resusd:0:4 " numequ=" DSDA.numequ:0:0 " numvar=" DSDA.numvar:0:0 /;
putclose result;
$if set gdx execute_unload "%gdx%";
