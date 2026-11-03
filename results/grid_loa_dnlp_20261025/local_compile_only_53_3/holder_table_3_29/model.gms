$offlisting
$offdigit

EQUATIONS
	c1
	c2
	c3_hi
	c4;

VARIABLES
	GAMS_OBJECTIVE
	x1
	x2
	x3;


c1.. x1 =e= -8 ;
c2.. x2 =e= 9.333333333333332 ;
c3_hi.. ((- abs(sin(x1)*cos(x2)*exp(abs(1 - sqrt(power(x1, 2) + power(x2, 2))/3.141592653589793)))) + 18.138024104635146)/18.138024104635146 - x3 =l= 0 ;
c4.. GAMS_OBJECTIVE =e= x3 ;

x1.lo = -10;
x1.up = 10;
x1.l = 0;
x2.lo = -10;
x2.up = 10;
x2.l = 0;
x3.lo = -0.8286373404940521;
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

