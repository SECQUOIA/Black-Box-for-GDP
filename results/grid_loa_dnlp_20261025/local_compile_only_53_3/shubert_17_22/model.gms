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


c1.. x1 =e= 5.666666666666666 ;
c2.. x2 =e= 7.333333333333333 ;
c3_hi.. (((cos(2*x1 + 1) + 2*cos(3*x1 + 2) + 3*cos(4*x1 + 3))*(cos(2*x2 + 1) + cos(x2 + 2))) + 11.037819188275034)/21.75809118738504 - x3 =l= 0 ;
c4.. GAMS_OBJECTIVE =e= x3 ;

x1.up = 10;
x1.l = 5;
x2.up = 10;
x2.l = 5;
x3.lo = -0.044221747369218765;
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

