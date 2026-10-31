* Corrected catalytic distillation model: distillation_model.gms with the fixes of REVIEW.md
* (findings 1-5, 8, 11-19, 21-24, 27, and the Ketbe coefficient). The published model is unchanged.
* English translation of catalytic_distillation/dsda-gdp-cd-column/DISTILLATION.gms
* from SECQUOIA/dsda-gdp at 3e469dbeea8931670b8cd6752014ab7a767d3af5.
* Only comments and descriptions were translated; the GAMS code is unchanged.
* Model only: the D-SDA external-variable setup is in DISTILLATION.gms.
$ontext
================================================================================
MINLP solver

          David Esteban Bernal Neira-David Alejandro Liñán Romero
                                 2020

*this ordered set must start at 1
*the model name must be DSDA
*problem must be expresed as a minimization problem
*the objective function variable must be called zobj
*the initialization gdx file must be called init.gdx
*subproblems must be nlp
================================================================================
$offtext
*-------------------------------------------------------------------------------
*                                   Section 1
*                        Sets for steady-state operation
*-------------------------------------------------------------------------------
*Only the initial element and the initial collocation point are used: steady state
*This is equivalent to removing j and N from the formulation
sets j "1 collocation point (0)" /1/
     N "1 finite element" /1/;
*-------------------------------------------------------------------------------
*                                   Section 2
*         Main sets, variables, parameters, and equations of the system
*-------------------------------------------------------------------------------
*Sets
set comp "components in the system" /iButene, Ethanol, nButene, ETBE/;
set Net "All column stages, real and superfluous, including condenser and reboiler" /1*22/;
*Alias of Net used in the binary (logic) constraints:
alias(Net,Net1);
set F "1 is ethanol and 2 is butenes" /1,2/;

*Main variables
positive variables
L(N,j,Net)  "Liquid flow [mol/min]"
V(N,j,Net)  "Vapor flow [mol/min]"
x(N,j,comp,Net)     "Liquid mole percentage [%]"
y(N,j,comp,Net)     "Vapor mole percentage [%]"
Temp(N,j,Net)       "Operating temperature [K]"
P(N,j,Net)  "Stage pressure [bar]"
Z(N,j,Net)  "Compressibility factor [-]"
RR(N,j)      "Molar reflux ratio [-]"
Qc(N,j)      "Condenser duty [kJ/min]"
Qr(N,j)      "Reboiler duty [kJ/min]"
BR(N,j)       "Boil up [-]"
;

*Hydraulic parameters
parameter
da      "Hole diameter [m]"  /2E-3/
ep      "Tray thickness [m]" /0.002/
pitch   "Hole pitch [m]"  /0.009/
Sfactor "Safety factor for the column height [-]" /0.15/
poro  "Tray porosity [-]"
K0    "Orifice coefficient [-]"
;
poro=0.907*sqr(da/pitch);
K0=(880.6-(67.7*da/ep)+(7.32*((da/ep)**2))-(0.338*((da/ep)**3)))*1E-3;

*Variables hidraulicas
positive variable D "Column diameter [m]";
positive variable hw      "Weir height [m]";
positive variable  HS      "Tray spacing [m]";
positive variable Htotal "Total column height [m]";
positive variable At "Active area [m2]";
positive variable Ad  "Downcomer area [m2]";
positive variable Lw "Weir length [m]";
positive variable A0 "Hole area [m2]";

*Hydraulic equations
Equation EqHwmin;
EqHwmin.. hw=g=0.05*HS;
Equation EqHwmax;
EqHwmax.. hw=l=HS/3;
equation EqAt;
EqAt.. At=e=sqr(D/2)*(pi-(1.854590-0.96));
equation EqAd;
EqAd.. Ad=e=sqr(D/2)*(0.5*(1.854590-0.96));
equation EqLw;
EqLw.. Lw=e=0.8*D;
equation EqA0;
EqA0.. A0=e=At*poro;

*Butenes feed
parameter FB "Butenes feed flow [mol/min]" /5.774/
parameter zb(N,j,comp) "Mole percentage in the butenes feed";
zb(N,j,'iButene')=30;
zb(N,j,'nButene')=100-zb(N,j,'iButene');
zb(N,j,'Ethanol')=0;
zb(N,j,'ETBE')=0;

*Ethanol feed
parameter
FE  "Ethanol feed flow [mol/min; labeled mol-h in the source]" /1.7118/
ze(comp)        "Mole percentage in the ethanol feed"
/
iButene 0
Ethanol 100
nButene 0
ETBE 0
/
;
*Operating parameters
parameter
Pop     "Condenser operating pressure [bar]"        /9.5/
TaliB   "Butenes feed temperature [K]"    /323/
TaliE   "Ethanol feed temperature [K]"        /342.38/
xBetbe  "Required ETBE mole percentage in the bottoms"   /83/
MCR     "Constant holdup in reboiler and condenser [mol]" /1/
cR      "Gas constant [m3*bar/K*mol]" /0.00008314/
;
*-------------------------------------------------------------------------------
*                                   Section 13
*          Definition of parameters, constraints, and binary variables
*-------------------------------------------------------------------------------

*Parameter that determines whether reactive stages are treated as equilibrium stages
scalar CASE "0 means reactive stages are equilibrium stages"/0/;
*Presence of catalyst
parameter yc(Net) "1 if the stage holds catalyst";

*Presence of reflux
parameter yr(Net) "1 if the reflux returns to the stage";
yr(Net)$((ord(Net) ne card(Net)) and (ord(Net) ne 1))=0;
yr('2')=1;
*Presence of boil-up
parameter yb(Net) "1 if the boil-up returns to the stage";

*Identifies whether a stage is real or superfluous
parameter par(Net) "1 if the stage physically exists";
par('1')=1;
par(Net)$(ord(Net) eq card(Net))=1;
*Presence of equilibrium relations
parameter ye(Net) "1 if the stage is an equilibrium stage";

*Presence of feed
parameter yf1(Net) "1 if the ethanol feed enters the stage";
parameter yf2(Net) "1 if the butenes feed enters the stage";

*-------------------------------------------------------------------------------
*                                   Section 14
*                              Logical constraints
*-------------------------------------------------------------------------------

scalar cmej /1/;
scalar NCmax "number of reactive stages" /3/;

equation logic1(Net) "The boil up stage is below the reflux stage";
logic1(Net)$(ord(Net)>1 and ord(Net)<card(Net))..cmej*(sum(Net1$((ord(Net1) ge 2) and (ord(Net1) le ord(Net))),yr(Net1)))=g=cmej*(yb(Net));

equation logic2 "There is one reflux stage";
logic2..cmej*(sum(Net1$((ord(Net1) ge 2) and (ord(Net1) le (card(Net1)-1))),yr(Net1)))=e=cmej*1;

equation logic3 "There is one boil up stage";
logic3..cmej*(sum(Net1$((ord(Net1) ge 2) and (ord(Net1) le (card(Net1)-1))),yb(Net1)))=e=cmej*1;

equation logic4a,logic4b "There is one feed stage of EtOH and there is one feed stage of butenes";
logic4a..cmej*(sum(Net1$((ord(Net1) ge 2) and (ord(Net1) le (card(Net1)-1))),yf1(Net1)))=e=cmej*1;
logic4b..cmej*(sum(Net1$((ord(Net1) ge 2) and (ord(Net1) le (card(Net1)-1))),yf2(Net1)))=e=cmej*1;

equation logic6 "There is a maximum number of  catalytic stages";
logic6.. cmej*(sum(Net1$((ord(Net1) ge 2) and (ord(Net1) le (card(Net1)-1))),yc(Net1))) =e=cmej*NCmax;

equation logic7a(Net),logic7b(Net) "Both feed stages are below the reflux";
logic7a(Net)$(ord(Net)>1 and ord(Net)<card(Net))..cmej*(sum(Net1$((ord(Net1) ge 2) and (ord(Net1) le ord(Net))),yr(Net1)))=g=cmej*yf1(Net);
logic7b(Net)$(ord(Net)>1 and ord(Net)<card(Net))..cmej*(sum(Net1$((ord(Net1) ge 2) and (ord(Net1) le ord(Net))),yr(Net1)))=g=cmej*yf2(Net);

equation logic8a(Net),logic8b(Net) "The boil up stage is below the feed stages";
logic8a(Net)$(ord(Net)>1 and ord(Net)<card(Net))..cmej*(sum(Net1$((ord(Net1) ge 2) and (ord(Net1) le ord(Net))),yf1(Net1)))=g=cmej*yb(Net);
logic8b(Net)$(ord(Net)>1 and ord(Net)<card(Net))..cmej*(sum(Net1$((ord(Net1) ge 2) and (ord(Net1) le ord(Net))),yf2(Net1)))=g=cmej*yb(Net);

equation logic9(Net)  "The EtOH feed is above the butenes feed";
logic9(Net)$(ord(Net)>1 and ord(Net)<card(Net))..cmej*(sum(Net1$((ord(Net1) ge 2) and (ord(Net1) le ord(Net))),yf1(Net1)))=g=cmej*yf2(Net);

equation logic10(Net) "The catalytic stages are below the EtOH feed stage";
logic10(Net)$(ord(Net)>1 and ord(Net)<card(Net))..cmej*(sum(Net1$((ord(Net1) ge 2) and (ord(Net1) le ord(Net))),yf1(Net1)))=g=cmej*yc(Net);

equation logic11(Net) "The catalytic stages are above the butenes  feed stage";
logic11(Net)$(ord(Net)>1 and ord(Net)<card(Net))..cmej*((sum(Net1$((ord(Net1) ge 2) and (ord(Net1) le ord(Net))),yf2(Net1)))-(yf2(Net)))=l=cmej*(1-yc(Net));

equation logic12(Net) "The catalytic stages are below the reflux stage";
logic12(Net)$(ord(Net)>1 and ord(Net)<card(Net))..cmej*(sum(Net1$((ord(Net1) ge 2) and (ord(Net1) le ord(Net))),yr(Net1)))=g=cmej*yc(Net);

equation logic13(Net) "The catalytic stages are above the boil up stage";
logic13(Net)$(ord(Net)>1 and ord(Net)<card(Net))..cmej*((sum(Net1$((ord(Net1) ge 2) and (ord(Net1) le ord(Net))),yb(Net1)))-(yb(Net)))=l=cmej*(1-yc(Net));

*-------------------------------------------------------------------------------
*                                   Section 3
*                           Unit conversion parameter
*-------------------------------------------------------------------------------
parameter
hora    "Seconds per time unit: 60 for analysis per minute [s]" /60/;

*-------------------------------------------------------------------------------
*                                   Section 4
*                               Purity constraints
*-------------------------------------------------------------------------------

equations pureza0(Net);
pureza0(Net)$(ord(Net) eq card(Net)).. x('1','1','ETBE',Net)=g=xBetbe;

*-------------------------------------------------------------------------------
*                                   Section 5
*            Saturation pressures from the extended Antoine equation
*-------------------------------------------------------------------------------
*Constants of the extended Antoine equation
parameters
C1a(comp)
/
iButene 66.4970745
Ethanol 61.7910745
nButene 40.3230745
ETBE    52.67507454
/
C2a(comp)
/
iButene -4634.1
Ethanol -7122.3
nButene -4019.2
ETBE    -5820.2
/
C3a(comp)
/
iButene 0
Ethanol 0
nButene 0
ETBE    0
/
C4a(comp)
/
iButene 0
Ethanol 0
nButene 0
ETBE    0
/
C5a(comp)
/
iButene -8.9575
Ethanol -7.1424
nButene -4.5229
ETBE    -6.1343
/
C6a(comp)
/
iButene 1.3413E-5
Ethanol 2.8853E-6
nButene 4.8833E-17
ETBE    2.1405E-17
/
C7a(comp)
/
iButene 2
Ethanol 2
nButene 6
ETBE    6
/
;
positive variables Psat(N,j,comp,Net) saturation pressure (bar);
equations EqPsat(N,j,comp,Net);
EqPsat(N,j,comp,Net)$(par(Net) eq 1).. Psat(N,j,comp,Net)=e=exp( C1a(comp) + (C2a(comp)/(Temp(N,j,Net)+C3a(comp))) + (C4a(comp)*Temp(N,j,Net)) + (C5a(comp)*log(Temp(N,j,Net)) + (C6a(comp)*(Temp(N,j,Net)**C7a(comp)))) );

*-------------------------------------------------------------------------------
*                                   Section 6
*                   Liquid densities from the IK-CAPI equation
*               Liquid densities from the critical DIPPR equation
*              Gas densities from the corrected ideal-gas equation
*-------------------------------------------------------------------------------
*Constants of the DIPPR equation
parameters
MW(comp) "Molecular weight [kg/kmol]"
/
iButene 56.10752
Ethanol 46.06904
nButene 56.10752
ETBE    102.17656
/
Tcrit(comp) "Critical temperature [K]"
/
iButene 417.9
Ethanol 514
nButene 419.5
ETBE    509.4
/
Pcrit(comp) "Critical pressure [bar]"
/
iButene 40.0
Ethanol 61.37
nButene 40.2
ETBE    29.34
/
C1rh(comp)
/
iButene        8.9711123119
Ethanol        -2.932961888E-2
nButene        5.956235579
ETBE           -1.323678817E-1
/
C2rh(comp)
/
iButene        0
Ethanol        6.9361857406E-4
nButene        0
ETBE           2.1486345729E-3
/
C3rh(comp)
/
iButene 0
Ethanol -1.962897037E-6
nButene 0
ETBE    -6.092181735E-6
/
C4rh(comp)
/
iButene 0
Ethanol 2.089632106E-9
nButene 0
ETBE    6.4627035532E-9
/
C5rh(comp)
/
iButene 0
Ethanol 0
nButene 0
ETBE    0
/
C6rh(comp)
/
iButene -1.4666609E-10
Ethanol 0
nButene -9.3717935E-11
ETBE    0
/
C7rh(comp)
/
iButene 1.286186216E-12
Ethanol 0
nButene 8.150339357E-13
ETBE    0
/
C8rh(comp)
/
iButene -4.33826109E-15
Ethanol 0
nButene -2.72421122E-15
ETBE    0
/
C9rh(comp)
/
iButene 6.619652613E-18
Ethanol 0
nButene 4.115761136E-18
ETBE    0
/
C10rh(comp)
/
iButene -3.8362103001E-21
Ethanol 0
nButene -2.3593237507E-21
ETBE    0
/
C1r(comp)
/
iButene        1.1446
Ethanol        1.6288
nButene        1.0877
ETBE        0.66333
/
C2r(comp)
/
iButene        0.2724
Ethanol        0.27469
nButene        2.6454E-01
ETBE        2.6135E-01
/
C3r(comp)
/
iButene        0.28172
Ethanol        0.23178
nButene        0.2843
ETBE        0.28571
/
C4r(comp)
/
iButene 0
Ethanol 0
nButene 0
ETBE    0
/
;
*Corrected: properties use the critical temperature of each component; the mixture Tcritm is removed.
positive variables rho(N,j,comp,Net) "Liquid molar density of each component [mol/m^3]";
equation Eqrho(N,j,comp,Net);
Eqrho(N,j,comp,Net)$(par(Net) eq 1).. rho(N,j,comp,Net)=e=( C1r(comp)/(C2r(comp)**(1+((1-(Temp(N,j,Net)/Tcrit(comp)))**C3r(comp)))) )*1000;

positive variable rhoV(N,j,Net) "Vapor molar density [mol/m^3]";
equation EqurhoV(N,j,Net);
EqurhoV(N,j,Net)$(par(Net) eq 1).. rhoV(N,j,Net)=e=P(N,j,Net)/(0.00008314*Temp(N,j,Net)*(Z(N,j,Net)));

*-------------------------------------------------------------------------------
*                                   Section 7
*                Surface tension from the critical DIPPR equation
*-------------------------------------------------------------------------------
*Constants of the DIPPR equation
parameters
C1sig(comp)
/
iButene        0.05544
Ethanol        0.03764
nButene        0.055945
ETBE        0.071885
/
C2sig(comp)
/
iButene        1.2453
Ethanol        -2.157E-5
nButene        1.2402
ETBE        2.1204
/
C3sig(comp)
/
iButene        0.0
Ethanol        1.025E-7
nButene        0
ETBE        -1.5583
/
C4sig(comp)
/
iButene 0
Ethanol 0
nButene 0
ETBE    0.76657
/
;
positive variables sigma(N,j,Net) "Liquid-vapor surface tension [N/m]";
equation Eqsigma(N,j,Net);
Eqsigma(N,j,Net)$(par(Net) eq 1).. sigma(N,j,Net)=e=sum(comp$(not sameas(comp,'Ethanol')),(x(N,j,comp,Net)/100)*C1sig(comp)
                        *(1-(Temp(N,j,Net)/Tcrit(comp)))**(C2sig(comp)+C3sig(comp)*(Temp(N,j,Net)/Tcrit(comp))+C4sig(comp)*sqr(Temp(N,j,Net)/Tcrit(comp))))
                        +(x(N,j,'Ethanol',Net)/100)*(C1sig('Ethanol')+C2sig('Ethanol')*Temp(N,j,Net)-C3sig('Ethanol')*sqr(Temp(N,j,Net)));
*-------------------------------------------------------------------------------
*                                   Section 8
*                   Activity coefficients from the NRTL model
*-------------------------------------------------------------------------------
table a_nrtl(comp,comp) NRTL parameter a
                       iButene            Ethanol            nButene            ETBE
iButene                0.0                0.0                0.0                0.0
Ethanol                0.0                0.0                0.0                0.0
nButene                0.0                0.0                0.0                0.0
ETBE                   0.0                0.0                0.0                0.0
;

table b_nrtl(comp,comp) NRTL parameter b
                iButene                Ethanol            nButene            ETBE
iButene         0.0                    623.5810010        107.526499         219.73407
Ethanol         141.9632130            0.0                164.57256          187.104064
nButene         -93.24546420           595.5299820        0.0                226.373398
ETBE            -172.59152             344.481315         -177.88565         0.0
;

table c_nrtl(comp,comp) NRTL parameter c
                       iButene            Ethanol            nButene            ETBE
iButene                0.0                0.3                0.3                0.3
Ethanol                0.3                0.0                0.3                0.3
nButene                0.3                0.3                0.0                0.3
ETBE                   0.3                0.3                0.3                0.0
;
alias (comp,comp1);
parameter alfa_nrtl(comp,comp);
alfa_nrtl(comp,comp1)$(ord(comp) ne ord(comp1))=c_nrtl(comp,comp1);

*NRTL parameters G and tau
variables tao_nrtl(N,j,comp,comp1,Net);
equations Eq_tao_nrtl(N,j,comp,comp1,Net);
Eq_tao_nrtl(N,j,comp,comp1,Net)$(par(Net) eq 1).. tao_nrtl(N,j,comp,comp1,Net)=e=a_nrtl(comp,comp1) + (b_nrtl(comp,comp1)/Temp(N,j,Net));

variables g_nrtl(N,j,comp,comp1,Net);
equations Eq_g_nrtl(N,j,comp,comp1,Net);
Eq_g_nrtl(N,j,comp,comp1,Net)$(par(Net) eq 1).. g_nrtl(N,j,comp,comp1,Net)=e=exp( -alfa_nrtl(comp,comp1)*tao_nrtl(N,j,comp,comp1,Net));

*Activity coefficient (gamma)
alias (comp,comp2,comp3);
variables gamma(N,j,comp,Net);
equations Eqgamma(N,j,comp,Net);
Eqgamma(N,j,comp,Net)$(par(Net) eq 1).. gamma(N,j,comp,Net)=e=
        exp(sum(comp1,x(N,j,comp1,Net)*tao_nrtl(N,j,comp1,comp,Net)*
        g_nrtl(N,j,comp1,comp,Net))/sum(comp1,x(N,j,comp1,Net)*
        g_nrtl(N,j,comp1,comp,Net))+sum(comp1,x(N,j,comp1,Net)*
        g_nrtl(N,j,comp,comp1,Net)/sum(comp2,x(N,j,comp2,Net)*
        g_nrtl(N,j,comp2,comp1,Net))*(tao_nrtl(N,j,comp,comp1,Net)-
        sum(comp2,x(N,j,comp2,Net)*tao_nrtl(N,j,comp2,comp1,Net)*
        g_nrtl(N,j,comp2,comp1,Net))/sum(comp3,x(N,j,comp3,Net)*
        g_nrtl(N,j,comp3,comp1,Net)))));

*-------------------------------------------------------------------------------
*                                   Section 9
*                               Chemical reaction
*-------------------------------------------------------------------------------
Parameter
Nu(comp) "Stoichiometric coefficients of the reaction"
/
iButene -1
Ethanol -1
nButene 0
ETBE    1
/
mcat  "Catalyst mass per catalytic stage [kg]"     /0.4/
;
variable Ketbe(N,j,Net) "Equilibrium constant [-]";
$ontext
$offtext
equation EqKetbe(N,j,Net);
EqKetbe(N,j,Net)$((ord(Net) ne card(Net)) and (ord(Net) ne 1) and yc(net) eq 1).. Ketbe(N,j,Net) =e=
                exp(10.387+4060.59/(Temp(N,j,Net))
                -2.89055*log(Temp(N,j,Net))
                -0.0191544*Temp(N,j,Net)
                +0.0000528586*power(Temp(N,j,Net),2)
                -0.0000000532977*power(Temp(N,j,Net),3));

positive variable Krate(N,j,Net) "Rate constant [mol/(kg_cat.min)]";
equation EqKrate(N,j,Net);
EqKrate(N,j,Net)$((ord(Net) ne card(Net)) and (ord(Net) ne 1) and yc(net) eq 1)..  Krate(N,j,Net) =e= 7.41816E15*exp(-60400.0/(8.314*Temp(N,j,Net)))*hora/3600;
positive variable Ka(N,j,Net) "Adsorption constant";
equation EqKa(N,j,Net);
EqKa(N,j,Net)$((ord(Net) ne card(Net)) and (ord(Net) ne 1) and yc(net) eq 1)..  Ka(N,j,Net) =e= exp(-1.0707+1323.1/Temp(N,j,Net));
variable Rx(N,j,Net) "Reaction rate [mol/(kg_cat.min)]";
equation EqRx(N,j,Net);
EqRx(N,j,Net)$((ord(Net) ne card(Net)) and (ord(Net) ne 1) and yc(net) eq 1)..  Rx(N,j,Net)*(power(1+Ka(N,j,Net)*gamma(N,j,'Ethanol',Net)*x(N,j,'Ethanol',Net)/100,3))*Ketbe(N,j,Net) =e=
                        (Krate(N,j,Net)*(gamma(N,j,'Ethanol',Net)*x(N,j,'Ethanol',Net)/100))
                        *((Ketbe(N,j,Net)*gamma(N,j,'iButene',Net)*x(N,j,'iButene',Net)/100*gamma(N,j,'Ethanol',Net)*x(N,j,'Ethanol',Net)/100)
                        -(gamma(N,j,'ETBE',Net)*x(N,j,'ETBE',Net)/100));
*-------------------------------------------------------------------------------
*                                   Section 10
*                     Equation of state (calculation of phi)
*-------------------------------------------------------------------------------
parameter
Omega(comp) "Acentric factor [-]"
/
iButene 0.19484
Ethanol 0.643558
nButene 0.184495
ETBE    0.316231
/
TcritSRK(comp) "Soave-Redlich-Kwong critical temperature [K]"
/
iButene 417.9
Ethanol 514
nButene 419.5
ETBE    509.4
/
mEOS(comp) "Parameter m in EOS"
biEOS(comp) "Parameter bi in EOS"
;
mEOS(comp)=0.48508+1.55171*Omega(comp)-0.15613*sqr(Omega(comp));
biEOS(comp)=0.08664*0.00008314*TcritSRK(comp)/Pcrit(comp);
parameter acEOS(comp) "SRK a at the critical point [bar.m^6/mol^2]";
acEOS(comp)=0.42747*sqr(0.00008314*TcritSRK(comp))/Pcrit(comp);
positive variable alphaEOS(N,j,comp,Net);
equation EqAlphaEOS(N,j,comp,Net);
EqAlphaEOS(N,j,comp,Net)$(par(net) eq 1).. alphaEOS(N,j,comp,Net) =e= sqr(1+mEOS(comp)*(1-(Temp(N,j,Net)/TcritSRK(comp))**(1/2)));
positive variable aiEOS(N,j,comp,Net);
equation EqaiEOS(N,j,comp,Net);
EqaiEOS(N,j,comp,Net)$(par(net) eq 1).. aiEOS(N,j,comp,Net) =e= alphaEOS(N,j,comp,Net)*0.42747*(sqr(0.00008314*TcritSRK(comp)))/Pcrit(comp);

positive variable bEOS(N,j,Net);
equation EqbEOS(N,j,Net);
EqbEOS(N,j,Net)$(par(net) eq 1).. bEOS(N,j,Net) =e= sum(comp,(y(N,j,comp,Net)/100)*biEOS(comp));

positive variable aEOS(N,j,Net);
equation EqaEOS(N,j,Net);
EqaEOS(N,j,Net)$(par(net) eq 1).. aEOS(N,j,Net) =e= sum(comp,sum(comp1, (y(N,j,comp,Net)/100)*(y(N,j,comp1,Net)/100)*(aiEOS(N,j,comp,Net)*aiEOS(N,j,comp1,Net))**0.5));

equation VaporZ(N,j,Net);
VaporZ(N,j,Net)$(par(net) eq 1).. (Z(N,j,Net))**3-(Z(N,j,Net))**2+(Z(N,j,Net))
                *((aEOS(N,j,Net)*P(N,j,Net)/((0.00008314*Temp(N,j,Net))**2))
                -(bEOS(N,j,Net)*P(N,j,Net)/(0.00008314*Temp(N,j,Net)))
                -(bEOS(N,j,Net)*P(N,j,Net)/(0.00008314*Temp(N,j,Net)))**2)
                -((aEOS(N,j,Net)*P(N,j,Net)/((0.00008314*Temp(N,j,Net))**2)))
                *(bEOS(N,j,Net)*P(N,j,Net)/(0.00008314*Temp(N,j,Net))) =e= 0;

positive variable phi(N,j,comp,Net);
equation EqPhi(N,j,comp,Net);
EqPhi(N,j,comp,Net)$(par(net) eq 1).. phi(N,j,comp,Net) =e= exp((Z(N,j,Net)-1)*biEOS(comp)/bEOS(N,j,Net)
                                        -log(Z(N,j,Net)-bEOS(N,j,Net)*P(N,j,Net)/(0.00008314*Temp(N,j,Net)))
                                        -(aEOS(N,j,Net)/(bEOS(N,j,Net)*0.00008314*Temp(N,j,Net)))
                                        *(2*((aiEOS(N,j,comp,Net)/aEOS(N,j,Net))**(1/2))-biEOS(comp)/bEOS(N,j,Net))
                                        *log(1+bEOS(N,j,Net)*P(N,j,Net)/(0.00008314*Temp(N,j,Net)*Z(N,j,Net))));

*18: fugacity coefficient of each pure component as saturated vapor at the stage temperature
*(vapor root of SRK at Psat; the bound and EqZsatV select the vapor root, Kamath et al. 2010)
positive variables Zsat(N,j,comp,Net), phisat(N,j,comp,Net);
equations VaporZsat(N,j,comp,Net), EqZsatV(N,j,comp,Net), EqPhisat(N,j,comp,Net);
VaporZsat(N,j,comp,Net)$(par(net) eq 1).. power(Zsat(N,j,comp,Net),3)-sqr(Zsat(N,j,comp,Net))
        +Zsat(N,j,comp,Net)*(aiEOS(N,j,comp,Net)*Psat(N,j,comp,Net)/sqr(0.00008314*Temp(N,j,Net))
                             -biEOS(comp)*Psat(N,j,comp,Net)/(0.00008314*Temp(N,j,Net))
                             -sqr(biEOS(comp)*Psat(N,j,comp,Net)/(0.00008314*Temp(N,j,Net))))
        -(aiEOS(N,j,comp,Net)*Psat(N,j,comp,Net)/sqr(0.00008314*Temp(N,j,Net)))*(biEOS(comp)*Psat(N,j,comp,Net)/(0.00008314*Temp(N,j,Net))) =e= 0;
EqZsatV(N,j,comp,Net)$(par(net) eq 1).. 3*sqr(Zsat(N,j,comp,Net))-2*Zsat(N,j,comp,Net)
        +aiEOS(N,j,comp,Net)*Psat(N,j,comp,Net)/sqr(0.00008314*Temp(N,j,Net))
        -biEOS(comp)*Psat(N,j,comp,Net)/(0.00008314*Temp(N,j,Net))
        -sqr(biEOS(comp)*Psat(N,j,comp,Net)/(0.00008314*Temp(N,j,Net))) =g= 0;
EqPhisat(N,j,comp,Net)$(par(net) eq 1).. phisat(N,j,comp,Net) =e= exp(Zsat(N,j,comp,Net)-1
        -log(Zsat(N,j,comp,Net)-biEOS(comp)*Psat(N,j,comp,Net)/(0.00008314*Temp(N,j,Net)))
        -(aiEOS(N,j,comp,Net)/(biEOS(comp)*0.00008314*Temp(N,j,Net)))
        *log(1+biEOS(comp)*Psat(N,j,comp,Net)/(0.00008314*Temp(N,j,Net)*Zsat(N,j,comp,Net))));
Zsat.lo(N,j,comp,Net)=1/3;
Zsat.up(N,j,comp,Net)=1.2;
Zsat.l(N,j,comp,Net)=0.9;
phisat.lo(N,j,comp,Net)=0.1;
phisat.up(N,j,comp,Net)=2;
phisat.l(N,j,comp,Net)=0.9;

*-------------------------------------------------------------------------------
*                                   Section 11
*                                   Enthalpies
*-------------------------------------------------------------------------------
*Ideal-gas Cp constants (kJ/mol.K)
parameters
C1c(comp)
/
iButene        0.016052191
Ethanol        0.00901418
nButene        -0.00299356
ETBE        -0.014651654
/
C2c(comp)
/
iButene        0.000280432
Ethanol        0.000214071
nButene        0.000353198
ETBE        0.000698631
/
C3c(comp)
/
iButene        -0.00000010914988
Ethanol        -0.000000083903472
nButene        -0.00000019904047
ETBE           -0.00000044791741
/
C4c(comp)
/
iButene        0.0000000000090979164
Ethanol        0.0000000000013732704
nButene        0.000000000044631288
ETBE           0.00000000011636811
/
C5c(comp)
/
iButene        0
Ethanol        0
nButene        0
ETBE           0
/
C6c(comp)
/
iButene        0
Ethanol        0
nButene        0
ETBE           0
/
;
parameter
Tref "Reference temperature [K]" /298.15/
Hform(comp) "Enthalpy of formation (kJ/mol)"
/
iButene -16.9147
Ethanol -234.963
nButene -0.125604
ETBE        -313.9
/
Tb      "Boiling temperature of the components at P=9.5 bar [K]"
/
iButene 342.03
Ethanol 421.99
nButene 341.66
ETBE    439.27
/
;
*Vapor-phase enthalpy (kJ/mol) -- Int(Cp dT)
variable HVi(N,j,comp,Net),HV(N,j,Net);
equations EqHVi(N,j,comp,Net),EqHV(N,j,Net);
EqHVi(N,j,comp,Net)$(par(net) eq 1).. HVi(N,j,comp,Net)=e=( (C1c(comp)*(Temp(N,j,Net)-Tref)) + ((C2c(comp)/2)*((Temp(N,j,Net)**2)-(Tref**2)))
                                   + ((C3c(comp)/3)*((Temp(N,j,Net)**3)-(Tref**3))) + ((C4c(comp)/4)*((Temp(N,j,Net)**4)-(Tref**4)))
                                   + ((C5c(comp)/5)*((Temp(N,j,Net)**5)-(Tref**5))) + ((C6c(comp)/6)*((Temp(N,j,Net)**6)-(Tref**6))) + Hform(comp)
                                   + (8.314/1000)*Temp(N,j,Net)*(Z(N,j,Net)-1)+100*(1+mEOS(comp))*(acEOS(comp)**0.5)*((aEOS(N,j,Net)**0.5)/bEOS(N,j,Net))*log(Z(N,j,Net)/(Z(N,j,Net)+(bEOS(N,j,Net)*P(N,j,Net)/(0.00008314*Temp(N,j,Net))))));

EqHV(N,j,Net)$(par(net) eq 1).. HV(N,j,Net)=e=sum(comp,HVi(N,j,comp,Net)*y(N,j,comp,Net)/100);

*Constants of the enthalpy of vaporization (kJ/mol)
parameter
C1v(comp)
/iButene        32.614
Ethanol        55.789
nButene        33.774
ETBE        45.29
/
C2v(comp)
/iButene        0.38073
Ethanol        0.31245
nButene        0.5107
ETBE        0.27343
/
C3v(comp)
/iButene        0
Ethanol        0
nButene        -0.17304
ETBE        0.21645
/
C4v(comp)
/iButene        0
Ethanol        0
nButene        0.05181
ETBE        -0.11756
/
C5v(comp)
/iButene        0
Ethanol        0
nButene        0
ETBE        0
/
;

*Reduced temperatures
parameter Tred(comp);
Tred(comp)=Tb(comp)/Tcrit(comp);


parameter alphaEOSb(comp), aiEOSb(comp);
alphaEOSb(comp)=(1+mEOS(comp)*(1-(Tb(comp)/Tcrit(comp))**(1/2)))**2;
aiEOSb(comp)=alphaEOSb(comp)*0.42747*((0.00008314*TcritSRK(comp))**2)/Pcrit(comp);
positive variable Zboil(N,j,comp,Net);
equation VaporZb(N,j,comp,Net);
VaporZb(N,j,comp,Net)$(par(net) eq 1).. (Zboil(N,j,comp,Net))**3-(Zboil(N,j,comp,Net))**2+(Zboil(N,j,comp,Net))
                        *((aiEOSb(comp)*P(N,j,Net)/((0.00008314*Tb(comp))**2))
                        -(biEOS(comp)*P(N,j,Net)/(0.00008314*Tb(comp)))
                        -(biEOS(comp)*P(N,j,Net)/(0.00008314*Tb(comp)))**2)
                        -((aiEOSb(comp)*P(N,j,Net)/((0.00008314*Tb(comp))**2)))
                        *(biEOS(comp)*P(N,j,Net)/(0.00008314*Tb(comp))) =e= 0;

*Enthalpy of vaporization (kJ/mol)
parameter DHvap(comp), Hvib(comp);
DHVap(comp)=( C1v(comp)*( (1-Tred(comp))**( C2v(comp) + (C3v(comp)*Tred(comp)) + (C4v(comp)*(Tred(comp)**2)) + (C5v(comp)*(Tred(comp)**3)) ) ) );
HVib(comp)=( (C1c(comp)*(Tb(comp)-Tref)) + ((C2c(comp)/2)*((Tb(comp)**2)-(Tref**2))) + ((C3c(comp)/3)*((Tb(comp)**3)-(Tref**3))) + ((C4c(comp)/4)*((Tb(comp)**4)-(Tref**4))) + ((C5c(comp)/5)*((Tb(comp)**5)-(Tref**5))) + ((C6c(comp)/6)*((Tb(comp)**6)-(Tref**6))) + Hform(comp));
variable depHvib(N,j,comp,Net);
equation EqdepHvib(N,j,comp,Net);
EqdepHvib(N,j,comp,Net)$(par(net) eq 1).. depHvib(N,j,comp,Net) =e= (8.314/1000)*Tb(comp)*(Zboil(N,j,comp,Net)-1)
                                                +100*(1+mEOS(comp))*((acEOS(comp)*aiEOSb(comp))**0.5)/biEOS(comp)
                                                *log(Zboil(N,j,comp,Net)/(Zboil(N,j,comp,Net)+(biEOS(comp)*P(N,j,Net)/(0.00008314*Tb(comp)))));

*Liquid Cp constants (kJ/mol.K)
parameter
C1l(comp)
/
iButene         0.08768
Ethanol         0.10264
nButene         0.18205
ETBE            0.11096
/
C2l(comp)
/iButene        0.0002171
Ethanol         -0.00013963
nButene         -0.001611
ETBE            0.00031422
/
C3l(comp)
/iButene        -9.15300E-07
Ethanol         -3.03410E-08
nButene         1.19630E-05
ETBE            1.74800E-07
/
C4l(comp)
/iButene        2.2660E-09
Ethanol         2.0386E-09
nButene         -3.7454E-08
ETBE            0
/
C5l(comp)
/iButene        0
Ethanol         0
nButene         4.5027E-11
ETBE            0
/
;

*Liquid-phase enthalpy (kJ/mol)
variable HLi(N,j,comp,Net),HL(N,j,Net);
equation EqHLi(N,j,comp,Net),EqHL(N,j,Net);
EqHLi(N,j,comp,Net)$(par(net) eq 1).. HLi(N,j,comp,Net)=e=HVib(comp)-DHVap(comp)
                        +((C1l(comp)*(Temp(N,j,Net)-Tb(comp))) + ((C2l(comp)/2)*((Temp(N,j,Net)**2)-(Tb(comp)**2)))
                        +((C3l(comp)/3)*((Temp(N,j,Net)**3)-(Tb(comp)**3))) + ((C4l(comp)/4)*((Temp(N,j,Net)**4)-(Tb(comp)**4)))
                        +((C5l(comp)/5)*((Temp(N,j,Net)**5)-(Tb(comp)**5))))+depHvib(N,j,comp,Net);

EqHL(N,j,Net)$(par(net) eq 1).. HL(N,j,Net)=e=sum(comp,HLi(N,j,comp,Net)*x(N,j,comp,Net)/100);
*-------------------------------------------------------------------------------
*                                   Section 12
*                                Feed enthalpies
*-------------------------------------------------------------------------------
*Enthalpy of the butenes feed
parameter HV_b(comp)    "Vapor enthalpy of the feed [kJ/mol]"
          Tred_b(comp)  "Reduced feed temperature [-]"
          DHVap_b(comp) "Enthalpy of vaporization of the feed [kJ/mol]"
          HL_b(comp)    "Liquid enthalpy of the feed [kJ/mol]";
HV_b(comp)=( (C1c(comp)*(TaliB-Tref)) + ((C2c(comp)/2)*((TaliB**2)-(Tref**2))) + ((C3c(comp)/3)*((TaliB**3)-(Tref**3))) + ((C4c(comp)/4)*((TaliB**4)-(Tref**4))) + ((C5c(comp)/5)*((TaliB**5)-(Tref**5))) + ((C6c(comp)/6)*((TaliB**6)-(Tref**6))) + Hform(comp));
Tred_b(comp)=TaliB/Tcrit(comp);
DHVap_b(comp)=( C1v(comp)*( (1-Tred_b(comp))**( C2v(comp) + (C3v(comp)*Tred_b(comp)) + (C4v(comp)*(Tred_b(comp)**2)) + (C5v(comp)*(Tred_b(comp)**3)) ) ) );
HL_b(comp)=HV_b(comp)-DHVap_b(comp);
parameter alphaEOSbut(comp), aiEOSbut(comp), aEOSbut(N,j), bEOSbut(N,j);
alphaEOSbut(comp)=(1+mEOS(comp)*(1-(TaliB/Tcrit(comp))**(1/2)))**2;
aiEOSbut(comp)=alphaEOSbut(comp)*0.42747*((0.00008314*TcritSRK(comp))**2)/Pcrit(comp);
bEOSbut(N,j)=sum(comp,(zb(N,j,comp)/100)*biEOS(comp));
aEOSbut(N,j)=sum(comp,sum(comp1, (zb(N,j,comp)/100)*(zb(N,j,comp1)/100)*(aiEOSbut(comp)*aiEOSbut(comp1))**0.5));



*HFB is computed for all internal stages
variable HFB(N,j,Net) "Enthalpy of the butenes feed";
equation EqHFB(N,j,Net);
parameter CpLb(comp) "Liquid heat from Tb to the butenes feed temperature [kJ/mol]";
CpLb(comp)=((C1l(comp)*(TaliB-Tb(comp))) + ((C2l(comp)/2)*((TaliB**2)-(Tb(comp)**2))) + ((C3l(comp)/3)*((TaliB**3)-(Tb(comp)**3))) + ((C4l(comp)/4)*((TaliB**4)-(Tb(comp)**4))) + ((C5l(comp)/5)*((TaliB**5)-(Tb(comp)**5))));
EqHFB(N,j,Net)$((ord(Net) ne card(Net)) and (ord(Net) ne 1) and yf2(net) eq 1).. HFB(N,j,Net) =e= sum(comp,(zb(N,j,comp)/100)*(HVib(comp)-DHVap(comp)+CpLb(comp)+depHvib(N,j,comp,Net)));

*Enthalpy of the ethanol feed
parameter HV_e(comp)    "Vapor enthalpy of the feed [kJ/mol]"
          Tred_e(comp)  "Reduced feed temperature [-; labeled K in the source]"
          DHVap_e(comp) "Enthalpy of vaporization of the feed [kJ/mol]"
          HL_e(comp)    "Liquid enthalpy of the feed [kJ/mol]";
HV_e(comp)=( (C1c(comp)*(TaliE-Tref)) + ((C2c(comp)/2)*((TaliE**2)-(Tref**2))) + ((C3c(comp)/3)*((TaliE**3)-(Tref**3))) + ((C4c(comp)/4)*((TaliE**4)-(Tref**4))) + ((C5c(comp)/5)*((TaliE**5)-(Tref**5))) + ((C6c(comp)/6)*((TaliE**6)-(Tref**6))) + Hform(comp));
Tred_e(comp)=TaliE/Tcrit(comp);
DHVap_e(comp)=( C1v(comp)*( (1-Tred_e(comp))**( C2v(comp) + (C3v(comp)*Tred_e(comp)) + (C4v(comp)*(Tred_e(comp)**2)) + (C5v(comp)*(Tred_e(comp)**3)) ) ) );
HL_e(comp)=HV_e(comp)-DHVap_e(comp);
parameter alphaEOSeth(comp), aiEOSeth(comp), aEOSeth, bEOSeth;
alphaEOSeth(comp)=(1+mEOS(comp)*(1-(TaliE/Tcrit(comp))**(1/2)))**2;
aiEOSeth(comp)=alphaEOSeth(comp)*0.42747*((0.00008314*TcritSRK(comp))**2)/Pcrit(comp);
bEOSeth=sum(comp,(ze(comp)/100)*biEOS(comp));
aEOSeth=sum(comp,sum(comp1, (ze(comp)/100)*(ze(comp1)/100)*(aiEOSeth(comp)*aiEOSeth(comp1))**0.5));


*HFE is computed for all internal stages
variable  HFE(N,j,Net)   "Enthalpy of the ethanol feed [kJ/mol]";
equation EqHFE(N,j,Net);
parameter CpLe(comp) "Liquid heat from Tb to the ethanol feed temperature [kJ/mol]";
CpLe(comp)=((C1l(comp)*(TaliE-Tb(comp))) + ((C2l(comp)/2)*((TaliE**2)-(Tb(comp)**2))) + ((C3l(comp)/3)*((TaliE**3)-(Tb(comp)**3))) + ((C4l(comp)/4)*((TaliE**4)-(Tb(comp)**4))) + ((C5l(comp)/5)*((TaliE**5)-(Tb(comp)**5))));
EqHFE(N,j,Net)$((ord(Net) ne card(Net)) and (ord(Net) ne 1) and yf1(net) eq 1).. HFE(N,j,Net) =e= sum(comp,(ze(comp)/100)*(HVib(comp)-DHVap(comp)+CpLe(comp)+depHvib(N,j,comp,Net)));

*-------------------------------------------------------------------------------
*                                   Section 15
*                              Condenser equations
*-------------------------------------------------------------------------------

*Initial conditions (steady-state operation)
equation BalMasaC0,BalMasaParcialC0(comp),SumaC0,EquilibrioC0(comp),BalEnergiaC0;
BalMasaC0.. 0=e=V('1','1','2')-V('1','1','1')*(1+RR('1','1'));
BalMasaParcialC0(comp).. 0=e=V('1','1','2')*y('1','1',comp,'2')-V('1','1','1')*x('1','1',comp,'1')*(1+RR('1','1'));
SumaC0.. sum(comp,y('1','1',comp,'1')-x('1','1',comp,'1'))=e=0;
EquilibrioC0(comp).. y('1','1',comp,'1')*P('1','1','1')*phi('1','1',comp,'1')=e=Psat('1','1',comp,'1')*phisat('1','1',comp,'1')*exp((P('1','1','1')-Psat('1','1',comp,'1'))*100000/(rho('1','1',comp,'1')*8.314*Temp('1','1','1')))*gamma('1','1',comp,'1')*x('1','1',comp,'1');
BalEnergiaC0.. 0=e=V('1','1','2')*HV('1','1','2')-V('1','1','1')*(1+RR('1','1'))*HL('1','1','1')-QC('1','1');

*Fixed liquid flow
equation fixedL(N,j);
fixedL(N,j)..L(N,j,'1')=e=0;

*-------------------------------------------------------------------------------
*                                   Section 16
*                        Column equations (steady state)
*-------------------------------------------------------------------------------
*MAIN DISJUNCTIONS
positive variable ETin(net),BUTin(net),reflux_flow(net),boilup_flow(net,net1);
variable reaction_term(net),partial_reaction_term(net,comp);
equations eq_ETin(net),eq_BUTin(net),eq_reflux_flow(net),eq_boilup_flow(net,net1),eq_reaction_term(net);
equations no_ETin(net),no_BUTin(net),no_reflux_flow(net),no_boilup_flow(net,net1),no_reaction_term(net);
equation eq_partial_reaction_term(net,comp),no_partial_reaction_term(net,comp);

eq_ETin(net)$(yf1(net) eq 1)..ETin(net)=e=FE;
eq_BUTin(net)$(yf2(net) eq 1)..BUTin(net)=e=FB;
eq_reflux_flow(net)$(yr(net) eq 1)..reflux_flow(net)=e=RR('1','1')*V('1','1','1');
eq_boilup_flow(net,net1)$(ord(net1) eq card(net1) and yb(net) eq 1)..boilup_flow(net,net1)=e=BR('1','1')*L('1','1',Net1);
eq_reaction_term(net)$(yc(net) eq 1)..reaction_term(net)=e=(sum(comp,Nu(comp))*mcat*Rx('1','1',Net));

no_ETin(net)$(yf1(net) eq 0)..ETin(net)=e=0;
no_BUTin(net)$(yf2(net) eq 0)..BUTin(net)=e=0;
no_reflux_flow(net)$(yr(net) eq 0)..reflux_flow(net)=e=0;
no_boilup_flow(net,net1)$(ord(net1) eq card(net1) and yb(net) eq 0)..boilup_flow(net,net1)=e=0;
no_reaction_term(net)$(yc(net) eq 0)..reaction_term(net)=e=0;

eq_partial_reaction_term(net,comp)$(yc(net) eq 1)..partial_reaction_term(net,comp)=e=(Nu(comp)*mcat*Rx('1','1',Net));
no_partial_reaction_term(net,comp)$(yc(net) eq 0)..partial_reaction_term(net,comp)=e=0;



*Initial conditions (steady-state operation)
equations BalMasa0(Net,Net1),BalMasaParcial0(comp,Net,Net1),Suma0(Net),BalEnergia0(Net,Net1);
BalMasa0(Net,Net1)$((ord(Net)>1 and ord(Net)<card(Net)) and (ord(Net1) eq card(Net1)))..0=e=ETin(net)+BUTin(net)+reflux_flow(net)+boilup_flow(net,net1)+L('1','1',Net-1)+V('1','1',Net+1)-L('1','1',Net)-V('1','1',Net)+reaction_term(net);
BalMasaParcial0(comp,Net,Net1)$((ord(Net)>1 and ord(Net)<card(Net)) and (ord(Net1) eq card(Net1)))..0=e=ETin(net)*ze(comp)+BUTin(net)*zb('1','1',comp)+reflux_flow(net)*x('1','1',comp,'1')+boilup_flow(net,net1)*y('1','1',comp,Net1)+L('1','1',Net-1)*x('1','1',comp,Net-1)+V('1','1',Net+1)*y('1','1',comp,Net+1)-L('1','1',Net)*x('1','1',comp,Net)-V('1','1',Net)*y('1','1',comp,Net)+100*partial_reaction_term(net,comp);
Suma0(Net)$(ord(Net)>1 and ord(Net)<card(Net)).. sum(comp,x('1','1',comp,Net)-y('1','1',comp,Net))=e=0;
BalEnergia0(Net,Net1)$(ord(Net)>1 and ord(Net)<card(Net) and ord(Net1) eq card(Net1))..0=e=ETin(net)*HFE('1','1',Net)+BUTin(net)*HFB('1','1',Net)+reflux_flow(net)*HL('1','1','1')+boilup_flow(net,net1)*HV('1','1',Net1)+L('1','1',Net-1)*HL('1','1',Net-1)+V('1','1',Net+1)*HV('1','1',Net+1)-L('1','1',Net)*HL('1','1',Net)-V('1','1',Net)*HV('1','1',Net);

*Equilibrium relations
equations Equilibrio10(comp,Net);
Equilibrio10(comp,Net)$(ord(Net)>1 and ord(Net)<card(Net) and ye(net) eq 1)..0=e=((y('1','1',comp,Net)*P('1','1',Net)*phi('1','1',comp,Net))-(Psat('1','1',comp,Net)*phisat('1','1',comp,Net)*exp((P('1','1',Net)-Psat('1','1',comp,Net))*100000/(rho('1','1',comp,Net)*8.314*Temp('1','1',Net)))*gamma('1','1',comp,Net)*x('1','1',comp,Net)));
equations Equilibrio20(comp,Net);
Equilibrio20(comp,Net)$(ord(Net)>1 and ord(Net)<card(Net) and ord(comp) ne 1 and ((sum(Net1$(ord(Net1) ge 2 and ord(Net1) le ord(Net)),yr(Net1)))) eq 1 and (1-ye(Net)) eq 1)..0=e=(y('1','1',comp,Net)-y('1','1',comp,Net+1));
equation Equilibrio30(comp,Net);
Equilibrio30(comp,Net)$(ord(Net)>1 and ord(Net)<card(Net) and ord(comp) ne 1 and ((1-sum(Net1$((ord(Net1) ge 2) and (ord(Net1) le ord(Net))),yr(Net1)))) eq 1 and (1-ye(Net)) eq 1)..0=e=(x('1','1',comp,Net)-x('1','1',comp,Net-1));
Equation Equilibrio40(Net,Net1);
Equilibrio40(Net,Net1)$(ord(Net)>1 and ord(Net)<card(Net) and ord(Net1) eq card(Net1))..0=e=(1-ye(Net))*(V('1','1',Net)-V('1','1',Net+1)-boilup_flow(net,net1));

*-------------------------------------------------------------------------------
*                                   Section 17
*                               Reboiler equations
*-------------------------------------------------------------------------------

*Initial conditions (steady-state operation)
equation BalMasaR0(Net),BalMasaParcialR0(comp,Net),SumaR0(Net),EquilibrioR0(comp,Net),BalEnergiaR0(Net);
BalMasaR0(Net)$(ord(Net) eq card(Net))..0=e=L('1','1',Net-1)-L('1','1',Net)*(1+BR('1','1'));
BalMasaParcialR0(comp,Net)$(ord(Net) eq card(Net))..0=e=L('1','1',Net-1)*x('1','1',comp,Net-1)-L('1','1',Net)*(x('1','1',comp,Net)+BR('1','1')*y('1','1',comp,Net));
SumaR0(Net)$(ord(Net) eq card(Net)).. sum(comp,y('1','1',comp,Net)-x('1','1',comp,Net))=e=0;
EquilibrioR0(comp,Net)$(ord(Net) eq card(Net))..y('1','1',comp,Net)*P('1','1',Net)*phi('1','1',comp,Net)=e=Psat('1','1',comp,Net)*phisat('1','1',comp,Net)*exp((P('1','1',Net)-Psat('1','1',comp,Net))*100000/(rho('1','1',comp,Net)*8.314*Temp('1','1',Net)))*gamma('1','1',comp,Net)*x('1','1',comp,Net);
BalEnergiaR0(Net)$(ord(Net) eq card(Net))..0=e=QR('1','1')+L('1','1',Net-1)*HL('1','1',Net-1)-L('1','1',Net)*HL('1','1',Net)-BR('1','1')*L('1','1',Net)*HV('1','1',Net);

*Fixed vapor flow in the last stage
equation fixedV(N,j,Net);
fixedV(N,j,Net)$(ord(Net) eq card(Net))..V(N,j,Net)=e=0;



*-------------------------------------------------------------------------------
*                                   Section 18
*                  Hydraulic relations for all internal stages
*-------------------------------------------------------------------------------
*Catalyst characteristics
scalar fracvol /0.3/;
scalar fracEnvelop /0.5/;

*Definition of the vapor velocity
positive variables far(N,j,Net) "Aeration factor [-]";
equations Eqfa(N,j,Net);
Eqfa(N,j,Net)$(ord(Net)>1 and ord(Net)<card(Net) and par(net) eq 1).. (far(N,j,Net))=e=(0.981*exp(-0.411*((V(N,j,Net)/(rhoV(N,j,Net))/hora)*(rhoV(N,j,Net)*sum(comp,MW(comp)*y(N,j,comp,Net)/100)/1000)**(0.5))/At));

positive variable hD(N,j,Net)   "Liquid height above the weir [m]";
equations EqhD(N,j,Net);
EqhD(N,j,Net)$(ord(Net)>1 and ord(Net)<card(Net) and par(net) eq 1).. (hD(N,j,Net))=e=(0.6*(((((L(N,j,Net)/sum(comp,rho(N,j,comp,Net)*x(N,j,comp,Net)/100))/hora)/Lw))**(2/3)));

positive variable uhv(N,j,Net) "Vapor velocity through the holes [m/s]";
equations Equhv(N,j,Net);
Equhv(N,j,Net)$(ord(Net)>1 and ord(Net)<card(Net) and par(net) eq 1).. (uhv(N,j,Net))=e=((V(N,j,Net)/(rhoV(N,j,Net))/hora)/A0);

positive variable unv(N,j,Net) "Vapor velocity over the tray [m/s]";
equations Equnv(N,j,Net);
Equnv(N,j,Net)$(ord(Net)>1 and ord(Net)<card(Net) and par(net) eq 1).. unv(N,j,Net)=e=((V(N,j,Net)/(rhoV(N,j,Net))/hora)/At);

*Definition of the liquid velocity
positive variable ul(N,j,Net) "Liquid velocity in the downcomer [m/s]";
equations Equl(N,j,Net);
Equl(N,j,Net)$(ord(Net)>1 and ord(Net)<card(Net) and par(net) eq 1).. ul(N,j,Net)=e=((L(N,j,Net)/(sum(comp,rho(N,j,comp,Net)*x(N,j,comp,Net)/100))/hora)/Ad);

*Liquid load
positive variable hcl(N,j,Net)  "Clear liquid height in the spray regime [m]"
equation Eqhcl(N,j,Net);
scalar consmach /1e-20/;
Eqhcl(N,j,Net)$(ord(Net)>1 and ord(Net)<card(Net) and par(net) eq 1).. hcl(N,j,Net)=e=((0.157*(poro**(-0.791))/(1+1.04E-4*(((((L(N,j,Net)+consmach)/sum(comp,rho(N,j,comp,Net)*x(N,j,comp,Net)/100))/hora)/Lw)**(-0.59))
                                                        *(poro**(-1.791))))*(da**0.833)
                                                        *(996/(sum(comp,rho(N,j,comp,Net)*x(N,j,comp,Net)/100)*sum(comp,MW(comp)*x(N,j,comp,Net)/100)/1000))**(0.5*(1-0.91*da/poro)));
positive variable Csbf(N,j,Net);
equation EqCsbf(N,j,Net);
EqCsbf(N,j,Net)$(ord(Net)>1 and ord(Net)<card(Net) and par(net) eq 1).. (Csbf(N,j,Net))=e=(0.37*(((sqr(da)*sigma(N,j,Net)/(sum(comp,rho(N,j,comp,Net)*x(N,j,comp,Net)/100)*sum(comp,MW(comp)*x(N,j,comp,Net)/100)/1000)))**0.125)
                                                        *((((rhoV(N,j,Net))*sum(comp,MW(comp)*y(N,j,comp,Net)/100)/1000)/(sum(comp,rho(N,j,comp,Net)*x(N,j,comp,Net)/100)*sum(comp,MW(comp)*x(N,j,comp,Net)/100)/1000))**0.1)
                                                        *((HS/hcl(N,j,Net))**0.5));
*Liquid load on catalytic stages
positive variable Lload(N,j,Net) "Liquid load on catalytic stages [m/s]";
equation eqLload(N,j,Net);
eqLload(N,j,Net)$(ord(Net)>1 and ord(Net)<card(Net) and yc(net) eq 1)..(1-fracvol)*((3.1415926/4)*(D**2))*Lload(N,j,Net)=e=ul(N,j,net)*Ad ;

*Vapor flow factor on catalytic stages
positive variable Ffactor(N,j,Net) "Vapor flow factor on catalytic stages [Pa**0.5]"
equation eqFfactor(N,j,Net);
eqFfactor(N,j,Net)$(ord(Net)>1 and ord(Net)<card(Net) and yc(net) eq 1).. (1-fracvol)*(3.1415926/4)*(D**2)*(((rhov(N,j,net))*(sum(comp,(y(N,j,comp,Net)/100)*MW(comp)))*(1/1000))**(1/2))*(Ffactor(N,j,Net))=e=(V(N,j,net)*(1/60))*(sum(comp,(y(N,j,comp,Net)/100)*MW(comp)*(1/1000)));

*Pressure drop
positive variables DPL(N,j,Net) "Pressure drop due to the liquid [bar]";
equations EqDPL(N,j,Net);
EqDPL(N,j,Net)$(ord(Net)>1 and ord(Net)<card(Net) and par(net) eq 1).. (DPL(N,j,Net))=e=((far(N,j,Net)*9.81*(sum(comp,rho(N,j,comp,Net)*x(N,j,comp,Net)/100)*sum(comp,MW(comp)*x(N,j,comp,Net)/100)/1000)*(hD(N,j,Net)+hw))/100000);

positive variables DPS(N,j,Net) "Dry pressure drop through the holes [bar]";
equations EqDPS(N,j,Net);
EqDPS(N,j,Net)$(ord(Net)>1 and ord(Net)<card(Net) and par(net) eq 1).. (DPS(N,j,Net))=e=((1/(2*sqr(K0)))*( (((sqr(V(N,j,Net)/(rhoV(N,j,Net))/hora)/sqr(A0))) )*((rhoV(N,j,Net))*sum(comp,MW(comp)*y(N,j,comp,Net)/100)/1000)*(1-sqr(poro)))/100000);

positive variable DPq(N,j,Net)      "Pressure drop in the downcomer [bar]";
equations EqDPq(N,j,Net);
EqDPq(N,j,Net)$(ord(Net)>1 and ord(Net)<card(Net) and par(net) eq 1).. DPq(N,j,Net)=e=(1/(100000))*1.62*((sum(comp,rho(N,j,comp,Net)*x(N,j,comp,Net)/100)*sum(comp,MW(comp)*x(N,j,comp,Net)/100)/1000))/(sqr(Lw*hw))*(sqr((L(N,j,Net)/sum(comp,rho(N,j,comp,Net)*x(N,j,comp,Net)/100))/hora));

positive variables DP(N,j,Net)  "Total pressure drop [bar]";
positive variable dPcat(N,j,net)    "Pressure drop due to the catalyst on catalytic stages [bar]";
equations EqDP(N,j,Net),NoDP(N,j,Net),EqDPR(N,j,Net),EqdPcat(N,j,net),NodPcat(N,j,net),EqP(N,j,Net),EqPC(N,j,Net),EqPR(N,j,Net) "Definition of the stage pressure [bar]";

EqDPR(N,j,Net)$(ord(Net) eq card(Net)).. DP(N,j,Net)=e=DP(N,j,Net-1);
EqdPcat(N,j,net)$(ord(Net)>1 and ord(Net)<card(Net) and yc(net) eq 1)..dPcat(N,j,net)=e=hs*fracEnvelop*(0.001)*(   (5.69228924748553E-06)*((Lload(N,j,Net)*60*60)**3.05308055949085)*((Ffactor(N,j,Net))**7.851695947) + 1.367015225*((Ffactor(N,j,Net))**1.764157687)    );
NodPcat(N,j,net)$(ord(Net)>1 and ord(Net)<card(Net) and yc(net) eq 0)..dPcat(N,j,net)=e=0;
EqDP(N,j,Net)$(ord(Net)>1 and ord(Net)<card(Net) and par(net) eq 1).. (DP(N,j,Net))=e=(DPS(N,j,Net)+DPL(N,j,Net))+dPcat(N,j,net);
NoDP(N,j,Net)$(ord(Net)>1 and ord(Net)<card(Net) and par(net) eq 0)..DP(N,j,Net)=e=0;

EqP(N,j,Net)$(ord(Net)>1 and ord(Net)<card(Net)).. P(N,j,Net)=e=P(N,j,Net-1)+DP(N,j,Net);
EqPC(N,j,Net)$(ord(Net) eq 1).. P(N,j,Net)=e=Pop;
EqPR(N,j,Net)$(ord(Net) eq card(Net)).. P(N,j,Net)=e=P(N,j,Net-1);

*Undesired effects in the column
*Downflow flooding (flooding in the downcomers)
equation DownFlood(N,j,Net);
DownFlood(N,j,Net)$(ord(Net)>1 and ord(Net)<card(Net) and par(net) eq 1)..0=g=((hw+HD(N,j,Net)+((DP(N,j,Net)+DPq(N,j,Net))*100000)
                                                        /(9.81*(((sum(comp,rho(N,j,comp,Net)*x(N,j,comp,Net)/100)*sum(comp,MW(comp)*x(N,j,comp,Net)/100)/1000))
                                                        -(rhoV(N,j,Net)*sum(comp,MW(comp)*y(N,j,comp,Net)/100)/1000))))-0.5*(HS+hw));
*Entrainment flooding (liquid carried over by the vapor)
equation EntrainFloodV(N,j,Net), EntrainFloodL(N,j,Net);
EntrainFloodV(N,j,Net)$(ord(Net)>1 and ord(Net)<card(Net) and par(net) eq 1)..((((V(N,j,Net)/(rhoV(N,j,Net))/hora)/(At+Ad)))-(Csbf(N,j,Net)*(((((sum(comp,rho(N,j,comp,Net)*x(N,j,comp,Net)/100)*sum(comp,MW(comp)*x(N,j,comp,Net)/100)/1000))
                                                        -(rhoV(N,j,Net)*sum(comp,MW(comp)*y(N,j,comp,Net)/100)/1000)))
                                                        /(rhoV(N,j,Net)*sum(comp,MW(comp)*y(N,j,comp,Net)/100)/1000))**0.5))=l=0;
EntrainFloodL(N,j,Net)$(ord(Net)>1 and ord(Net)<card(Net) and par(net) eq 1)..((ul(N,j,Net))-((sigma(N,j,Net)*9.81*(((sum(comp,rho(N,j,comp,Net)*x(N,j,comp,Net)/100)*sum(comp,MW(comp)*x(N,j,comp,Net)/100)/1000))
                                                        -(rhoV(N,j,Net)*sum(comp,MW(comp)*y(N,j,comp,Net)/100)/1000))
                                                        /((sum(comp,rho(N,j,comp,Net)*x(N,j,comp,Net)/100)*sum(comp,MW(comp)*x(N,j,comp,Net)/100)/1000)**2))**(1/4)))=l=0
*Weeping
equation Weep(N,j,Net);
Weep(N,j,Net)$(ord(Net)>1 and ord(Net)<card(Net) and par(net) eq 1).. 0=g=(((0.68-0.12)/(((rhoV(N,j,Net)*sum(comp,MW(comp)*y(N,j,comp,Net)/100)/1000)
                                                                /((sum(comp,rho(N,j,comp,Net)*x(N,j,comp,Net)/100)*sum(comp,MW(comp)*x(N,j,comp,Net)/100)/1000)
                                                                *9.81*far(N,j,Net)*(hw+hd(N,j,Net))))**0.5))-(uhv(N,j,Net)));
*Catalyst flooding (flooding of the catalyst packing)
equation catflood(N,j,net);
catflood(N,j,net)$(yc(net) eq 1)..(dPcat(N,j,net)-(12E-3)*hs*fracEnvelop)=l=0;

*Column construction
equation Size "Equipment size";
positive variable hs_stage(net);
equation eq_hs_stage(net),no_hs_stage(net);
eq_hs_stage(net)$(par(Net) eq 1)..hs_Stage(net)=e=HS;
no_hs_stage(net)$(par(Net) eq 0)..hs_Stage(net)=e=0;

Size.. 1*Htotal =e= 1*((1+Sfactor)*sum(Net$(ord(Net)>1 and ord(Net)<card(Net)),hs_Stage(net)));

equation  ammountcat "Space available for the catalyst";
ammountcat..mcat=l=(fracvol)*((3.1415926/4)*(D**2))*(hs*fracEnvelop)*770;

equation DtoLratio "Ratio between the height and the diameter";
DtoLratio..htotal/D=l=20;
*-------------------------------------------------------------------------------
*                                   Section 19
*                               Objective function
*-------------------------------------------------------------------------------
parameters alfa1 "Weight for ETBE purity" /1e4/
           alfa2 "Weight for the reboiler duty" /500/
           alfa3 "Weight for the reflux ratio" /100/
           CostQr "Cost of the reboiler duty [$/yr]"
           CostQc "Cost of the condenser duty [$/yr]"
           CostB  "Revenue from ETBE in the bottoms [$/yr]"
           CostEth"Cost of the ethanol feed [$/yr]"
           CostBut"Cost of the butenes feed [$/yr]"
           year   "Operational hours per year [hr/yr]" /8000/
           CostCat"Catalyst cost [$/kg]" /7.7/
           AF     "Annualization factor (5 years, 5% interest rate) [1/yr]"
           MS     "Marshall & Swift coefficient" /1050/
           FM     "Material factor (carbon steel)" /1/
           FPres  "Pressure factor (up to 200psi=13.78bar)" /1.15/
           C0     "Initial investment cost AF(Cr1+Cc1) [$]" /10000/
           CT     "Investment cost of the stages [$]"
           Csh    "Investment cost of the shell [$]"
           Fcol   "Column cost factor [-]";
Fcol=FM*FPres;
AF=(0.05/(1-1/(1+0.05)**5));
parameter Ftray "Tray cost factor Fs+Ft+Fm (12-in spacing, sieve, carbon steel; Douglas 1988)" /2.2/;
CT=(MS/280)*4.7*Ftray;
Csh=(MS/280)*101.9*(2.18+Fcol);
CostQr=146.8/(hora);
CostQc=24.5/(hora);
CostB=25.3*3600*year/(1000*hora);
CostEth=15*3600*year/(1000*hora);
CostBut=8.25*3600*year/(1000*hora);

parameters Uex   "Overall heat-transfer coefficient of condenser and reboiler [kW/(m^2.K)] (100 Btu/(h.ft^2.F))" /0.568/
           Tcw1  "Cooling water inlet temperature [K] (90 F)" /305.37/
           Tcw2  "Cooling water outlet temperature [K] (120 F)" /322.04/
           Tstm  "Saturated steam temperature in the reboiler [K] (10 bar)" /453.03/
           Fcond "Condenser cost factor (floating head, carbon steel)" /1.0/
           Freb  "Reboiler cost factor (kettle, carbon steel)" /1.35/;
positive variables Acond "Condenser area [m^2]", Areb "Reboiler area [m^2]";
equations EqAcond, EqAreb;
*Chen's approximation of the log-mean temperature difference
EqAcond.. Acond*Uex*((Temp('1','1','1')-Tcw1)*(Temp('1','1','1')-Tcw2)*((Temp('1','1','1')-Tcw1)+(Temp('1','1','1')-Tcw2))/2)**(1/3) =e= Qc('1','1')/hora;
EqAreb.. Areb*Uex*(Tstm-Temp('1','1','22')) =e= Qr('1','1')/hora;
Acond.lo=1e-4; Areb.lo=1e-4; Acond.l=0.2; Areb.l=0.2;
variables zobj;

equation Fobj(Net);


Fobj(Net)$(ord(Net) eq card(Net)).. zobj=e=1*((((CostEth*FE+CostBut*FB+(CostQr*Qr('1','1'))+(CostQc*Qc('1','1')))/year)*year)
+(AF*((MS/280)*101.3*((Acond*10.7639)**0.65)*(2.29+Fcond)+(MS/280)*101.3*((Areb*10.7639)**0.65)*(2.29+Freb)+mcat*CostCat*sum(Net1,yc(Net1))+CT*((D/0.3048)**1.55)*(sum(Net1$(ord(Net1)>1 and ord(Net1)<card(Net1)),hs_Stage(net1))/0.3048)+Csh*((D/0.3048)**1.066)*((Htotal/0.3048)**0.802)))
-((((CostB*L('1','1',Net)*x('1','1','ETBE',Net)/100))/year)*year));
*-------------------------------------------------------------------------------
*                                   Section 20
*                                Variable bounds
*-------------------------------------------------------------------------------
*bounds
D.up=0.3;
D.lo=0.1;

hw.up=0.1;
hw.lo=0.0001;

hs.up=0.3;
hs.lo=0.1;

htotal.up=10;

at.lo=1e-6;
at.up=0.1;

ad.lo=0.0001;
ad.up=0.01;

lw.up=1;

A0.lo=1e-12;
A0.up=0.01;

RR.lo(N,j)=1;
RR.up(N,j)=50;

Qr.up(N,j)=2000;
Qr.lo(N,j)=10;

Qc.up(N,j)=5000;

L.up(N,j,Net)=1000;
V.up(N,j,Net)=1000;

BR.up(N,j)=50;

P.up(N,j,Net)= 10;
P.lo(N,j,Net)=Pop;

zboil.up(N,j,comp,Net)=1.5;
zboil.lo(N,j,comp,Net)=0.7;



Psat.up(N,j,comp,Net)=100;

tao_nrtl.up(N,j,comp,comp1,Net)    =5;
tao_nrtl.lo(N,j,comp,comp1,Net)    =-5;

g_nrtl.up(N,j,comp,comp1,Net)=2;
g_nrtl.lo(N,j,comp,comp1,Net)=0;

gamma.up(N,j,comp,Net)=50;
gamma.lo(N,j,comp,Net)=0;

Ketbe.lo(N,j,Net)=0;
Ketbe.up(N,j,Net)=100;

Krate.up(N,j,Net)=1000000000;
Krate.lo(N,j,Net)=-10;
Krate.scale(N,j,Net)=10000000;

Ka.up(N,j,Net)=100;

Rx.up(N,j,Net)=100;
Rx.lo(N,j,Net)=-100000;
Rx.scale(N,j,Net)=100000;

alphaEOS.up(N,j,comp,Net)=5;
aiEOS.up(N,j,comp,Net)=1e-3;
aiEOS.lo(N,j,comp,Net)=1e-6;
aiEOS.scale(N,j,comp,Net)=1e-4;

bEOS.up(N,j,Net)=0.01;

aEOS.up(N,j,Net)=1e-3;

phi.up(N,j,comp,Net)=2;

HVi.up(N,j,comp,Net)=1000;
HVi.lo(N,j,comp,Net)=-1000;

HV.up(N,j,Net)=1000;
HV.lo(N,j,Net)=-1000;

depHvib.lo(N,j,comp,Net)=-10;
depHvib.up(N,j,comp,Net)=10;

HLi.lo(N,j,comp,Net)=-1000;
HLi.up(N,j,comp,Net)=1000;

HL.lo(N,j,Net)=-1000;
HL.up(N,j,Net)=1000;

HFB.lo(N,j,Net)=-50;
HFB.up(N,j,Net)=1;

HFE.lo(N,j,Net)=-500;
HFE.up(N,j,Net)=0;

far.up(N,j,Net)=2;
far.lo(N,j,Net)=0.1;

hD.up(N,j,Net)=0.1;
hD.lo(N,j,Net)=0.0001;

DPL.up(N,j,Net)=0.1;

DPS.up(N,j,Net)=0.01;

DP.up(N,j,Net)=0.1;

DPq.up(N,j,Net)=0.1;

uhv.up(N,j,Net)=10;
uhv.lo(N,j,Net)=0.4;

hcl.up(N,j,Net)=0.1;
hcl.lo(N,j,Net)=1e-6;

Lload.up(N,j,Net)=0.008333;
Ffactor.up(N,j,Net)=3.575;
dPcat.up(N,j,net)=10;

x.lo(N,j,comp,Net)= 0;
x.up(N,j,comp,Net)= 100;

y.lo(N,j,comp,Net)= 0;
y.up(N,j,comp,Net)= 100;

z.lo(N,j,Net)= 0.5 ;
z.up(N,j,Net)=  1.3  ;

Temp.lo(N,j,Net)= 200;
Temp.up(N,j,Net)= 417.89;
Temp.lo('1','1','1')=Tcw2+3;


bEOS.lo(N,j,Net)=min(biEOS('iButene'),biEOS('Ethanol'),biEOS('nButene'),biEOS('ETBE'));
aEOS.lo(N,j,Net)=1e-6;

*Bounded flooding variables cause problems with DICOPT:
unv.lo(N,j,Net)=0.01;
unv.up(N,j,Net)=0.89;

ul.up(N,j,Net)=30;
ul.lo(N,j,Net)=0.001;

rho.up(N,j,comp,Net)=25000;
rho.lo(N,j,comp,Net)=1000;

rhoV.up(N,j,Net)=500;
rhoV.lo(N,j,Net)=Pop/(0.00008314*Temp.up(N,j,Net)*(Z.up(N,j,Net)));

Csbf.up(N,j,Net)=1;
Csbf.lo(N,j,Net)=0.001;

sigma.up(N,j,Net)=0.03;
sigma.lo(N,j,Net)=0.005;
*------INITIAL VALUE OF BINARY TERMS--------------------------------------------
yb(Net)=0;
yc(Net)=0;
yf1(Net)=0;
yf2(Net)=0;

yb('9')=1;
yf1('3')=1;
yf2('8')=1;
yc('4')=1;
yc('5')=1;
yc('6')=1;

par(Net)$((ord(Net) ne card(Net)) and (ord(Net) ne 1))=(sum(Net1$((ord(Net1) ge 2) and (ord(Net1) le ord(Net))),yr(Net1)))+(yb(Net))-(sum(Net1$((ord(Net1) ge 2) and (ord(Net1) le ord(Net))),yb(Net1)));
ye(Net)$((ord(Net) ne card(Net)) and (ord(Net) ne 1))=par(Net)*(1-yc(Net))*CASE+par(Net)*(1-CASE);

*----------------------MODEL AND SOLUTION---------------------------------------
*the name of the model must be DSDA
model DSDA /all/;
