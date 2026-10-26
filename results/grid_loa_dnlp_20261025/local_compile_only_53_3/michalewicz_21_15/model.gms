$offlisting
$offdigit

EQUATIONS
	c1
	c2
	c3_hi
	c4;

POSITIVE VARIABLES
	x1
	x2;

VARIABLES
	GAMS_OBJECTIVE
	x3;


c1.. x1 =e= 2.199114857512855 ;
c2.. x2 =e= 1.5707963267948966 ;
c3_hi.. ((- sin(x1)*power(sin(power(x1, 2)/3.141592653589793), 20) - sin(x2)*power(sin(2*power(x2, 2)/3.141592653589793), 20)) + 1.8010702893119994)/1.8010702893119994 - x3 =l= 0 ;
c4.. GAMS_OBJECTIVE =e= x3 ;

x1.up = 3.141592653589793;
x1.l = 1.5707963267948966;
x2.up = 3.141592653589793;
x2.l = 1.5707963267948966;
x3.lo = -0.11045083130208694;
x3.l = 0;

MODEL GAMS_MODEL /all/ ;
option dnlp=scip;
option solprint=off;
option limrow=0;
option limcol=0;
option solvelink=5;
SOLVE GAMS_MODEL USING dnlp minimizing GAMS_OBJECTIVE;

Scalars MODELSTAT 'model status', SOLVESTAT 'solve status';
MODELSTAT = GAMS_MODEL.modelstat;
SOLVESTAT = GAMS_MODEL.solvestat;

Scalar OBJEST 'best objective', OBJVAL 'objective value';
OBJEST = GAMS_MODEL.objest;
OBJVAL = GAMS_MODEL.objval;

Scalar NUMVAR 'number of variables';
NUMVAR = GAMS_MODEL.numvar

Scalar NUMEQU 'number of equations';
NUMEQU = GAMS_MODEL.numequ

Scalar NUMDVAR 'number of discrete variables';
NUMDVAR = GAMS_MODEL.numdvar

Scalar NUMNZ 'number of nonzeros';
NUMNZ = GAMS_MODEL.numnz

Scalar ETSOLVE 'time to execute solve statement';
ETSOLVE = GAMS_MODEL.etsolve

