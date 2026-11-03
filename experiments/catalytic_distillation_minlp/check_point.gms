* Check a stored point of the product-form column MINLP (minlp_model_corrected.gms).
*   gams check_point.gms --model=... --point=solution.gdx --mode=examine|scip_fixed|scip_free|baron_free
* examine: Examiner reports the violations of the point (tolerance 1e-6).
* scip_fixed: SCIP with the binaries fixed at the point; scip_free and baron_free: SCIP or BARON on
* the whole MINLP, starting from the point, with a 900 s limit.
$include %model%
execute_loadpoint "%point%";
yf1.l(Net) = round(yf1.l(Net));
yf2.l(Net) = round(yf2.l(Net));
yc.l(Net) = round(yc.l(Net));
yb.l(Net) = round(yb.l(Net));
option threads = 1;
$ifthen %mode%==examine
$onecho > examiner2.opt
examineInitPoint 1
returnInitPoint 1
fCheckPCON 1
fCheckPVAR 1
scaled 0
primalFeasTol 1e-6
$offecho
option minlp = examiner2;
DSDA.optfile = 1;
solve DSDA using minlp minimizing zobj;
$else
$onecho > scip.opt
misc/printreason = TRUE
display/verblevel = 4
$offecho
$ifthen %mode%==scip_fixed
yf1.fx(Net) = yf1.l(Net); yf2.fx(Net) = yf2.l(Net); yc.fx(Net) = yc.l(Net); yb.fx(Net) = yb.l(Net);
$endif
$ifthen %mode%==baron_free
option minlp = baron;
$else
option minlp = scip;
$endif
DSDA.optfile = 1;
DSDA.reslim = 900;
solve DSDA using minlp minimizing zobj;
$endif
display DSDA.modelstat, DSDA.solvestat, zobj.l;
