* English translation of catalytic_distillation/dsda-gdp-cd-column/DISTILLATION.gms
* from SECQUOIA/dsda-gdp at 3e469dbeea8931670b8cd6752014ab7a767d3af5.
* Comments were translated, the model moved to distillation_model.gms, and CONOPT replaces MSNLP.
* The model is in distillation_model.gms; this file adds the D-SDA external-variable
* setup (embedded Python) used by D_SDA.gms through main.gms.
$include distillation_model.gms
* The source selected MSNLP, which current GAMS releases no longer distribute.
option nlp=conopt;
*--------------------DATA FROM THE MODEL------------------------------------
$embeddedCode Python:
import csv
import os
###User params 1: independent & dependent binar terms---------------------------
Indep={"x1":["yf1",None,"Net"],
"x2":["yf2",None,"Net"],
"x3":["yc",None,"Net"],
"x4":["yb",None,"Net"]}

Dep=["par(Net)$((ord(Net) ne card(Net)) and (ord(Net) ne 1))=(sum(Net1$((ord(Net1) ge 2) and (ord(Net1) le ord(Net))),yr(Net1)))+(yb(Net))-(sum(Net1$((ord(Net1) ge 2) and (ord(Net1) le ord(Net))),yb(Net1)));",
"ye(Net)$((ord(Net) ne card(Net)) and (ord(Net) ne 1))=par(Net)*(1-yc(Net))*CASE+par(Net)*(1-CASE);"]

###User params 2: neighborhood--------------------------------------------------
#use: Infinity,Separable,Mflat,Lflat
neighborhood="Separable"

###User params 3:User defined reformulation,initialization----------------------
###and_ inequality constraints--------------------------------------------------

#use: Automatic,User_defined
Reform_type="User_defined"
Reform=["fex('x1_1')=xvalue_p('x1_1');",
"fex('x2_1')=xvalue_p('x4_1')-xvalue_p('x2_1');",
"fex('x3_1')=xvalue_p('x1_1')+xvalue_p('x3_1'); ",
"fex('x3_2')=xvalue_p('x1_1')+xvalue_p('x3_1')+xvalue_p('x3_2');",
"fex('x3_3')=xvalue_p('x4_1')-xvalue_p('x2_1')-xvalue_p('x3_3');","fex('x4_1')=xvalue_p('x4_1'); "]
Initial=["xvalinit('x1_1')=3;","xvalinit('x2_1')=1;","xvalinit('x3_1')=1; ","xvalinit('x3_2')=1; ","xvalinit('x3_3')=2;  ","xvalinit('x4_1')=9; "]

#use: Automatic,User_defined
Ineq_type="User_defined"
#merge_constraints: 1 if_ user constraints must be merged with automatic constraints.
#merge_constraints: 0 if_ user defined constraints are going to be used alone.
merge_constraints="0"
Ineq=["2-fex('x1_1');","fex('x2_1')-fex('x4_1');","fex('x3_1')+1-fex('x3_2'); ","fex('x3_2')+1-fex('x3_3');","fex('x1_1')-fex('x3_1');","fex('x3_3')-fex('x2_1'); ","fex('x4_1')-21; "]

###user params 3: Decide if_ logical constranits are going to remain in the subProblems
#logic_sub:1 if_ logical constraints appear in the subproblems, gams is allowed to skip the solution stage for_ infeasible neighbors
#logic_sub:0 if_ logical constraints do_ not_ appear in the subproblems, the master problem oversees the logic_
logic_sub="0"

###Create list of external variabs (extvar)-------------------------------------
extvar=list()
for i in Indep:
 Indep[i][1]=str(sum(list(gams.get(Indep[i][0],KeyType.INT,KeyFormat.SKIP))))
 numb=int(float(Indep[i][1]))
 for j in range(1,numb+1):
  extvar.append(i+"_"+str(j))
  Indep[i].append(i+"_"+str(j))

#Total numb of external var
numb=len(extvar)


#print("number of external variables=",numb)
#print("set of external variables=",extvar)


#Total numb of neighbors
if neighborhood=="Infinity":
 num_neigh=(3**numb)-1
elif neighborhood=="Separable":
 num_neigh=2*numb
elif neighborhood=="Mflat":
 num_neigh=numb*(numb+1)
elif neighborhood=="Lflat":
 num_neigh=2**(numb+1)-2

#extvar set_ and_ subsets
Ext="set extvar /"+','.join(extvar)+"/; \n"
Ext_sub=""
for i in Indep:
 Ext_sub=Ext_sub+"set s_"+i+"(extvar) /"+','.join(Indep[i][3:None])+"/; \n"
#print(Ext)
#print(Ext_sub)

neigh="set neigh /d1*d"+str(num_neigh)+"/; \n"
#print(neigh)

#create de csv file_ with the niegihbors
os.chdir('./neighborhood_MATLAB')
file=str(numb)+'_'+neighborhood+'.csv'
with open(file) as csvfile:
 readCSV = csv.reader(csvfile, delimiter=',')
 neigh_values=","+','.join(extvar)+"\n"
 for row in readCSV:
  neigh_values=neigh_values+str(','.join(row))+"\n"
os.chdir('..')

#print(neigh_values)

#get and_ add ordered sets_in list format
for i in Indep:
 Indep[i].append(list(gams.get(Indep[i][2],KeyType.STRING)))

#create aux variables_ for_ reformulation
Ext_aux=""
for i in Indep:
 Ext_aux=Ext_aux+"parameter yaux_"+i+"(extvar,"+Indep[i][2]+");\nyaux_"+i+"(extvar,"+Indep[i][2]+")=0;\n"

#get and_ add value of intependente binary_ terms for_ initializations
for i in Indep:
 Indep[i].append(list(gams.get(Indep[i][0],KeyType.STRING)))

#print("\n",str(Indep))


#Creation of external variables_ functions_ and_ initialization
reform_string=""
initialization_string=""
if Reform_type=="User_defined":
 reform_string='\n'.join(Reform)
 initialization_string='\n'.join(Initial)
if Reform_type=="Automatic":
 cuent=0;
 for i in Indep:
  reform_string=reform_string+"fex(s_"+i+")=xvalue_p(s_"+i+");\n"
  for j in Indep[i][-1]:
   initialization_string=initialization_string+"xvalinit(\'"+extvar[cuent]+"\')="+str(j[0])+";\n"
   cuent=cuent+1

#print(reform_string)
#print(initialization_string)
#Total number of inequality constraints and_ definiton of ineqs
number_user_defined_ineq=len(Ineq)
numb_ineq=numb*2
ineq_string_Automatic=""
ineq_string_User=""
ineq_string=""
cuent1=1;
for i in Indep:
 cuent2=0;
 for j in Indep[i][-1]:
  cuent2=cuent2+1;
  ineq_string_Automatic=ineq_string_Automatic+"gval(\'g"+str(cuent1)+"\')=1-fex(\'"+i+"_"+str(cuent2)+"\');\n"
  ineq_string_Automatic=ineq_string_Automatic+"gval(\'g"+str(cuent1+1)+"\')=fex(\'"+i+"_"+str(cuent2)+"\')-"+str(len(Indep[i][-2]))+";\n"
  cuent1=cuent1+2
  if cuent2>=2:
   ineq_string_Automatic=ineq_string_Automatic+"gval(\'g"+str(cuent1)+"\')=1+fex(\'"+i+"_"+str(cuent2-1)+"\')-fex(\'"+i+"_"+str(cuent2)+"\');\n"
   numb_ineq=numb_ineq+1
   cuent1=cuent1+1

if Ineq_type=="Automatic":
 ineq_string=ineq_string_Automatic
elif Ineq_type=="User_defined" and merge_constraints=="1":
 numb_ineq=numb_ineq+int(number_user_defined_ineq)
 for i in Ineq:
  ineq_string_User=ineq_string_User+"gval(\'g"+str(cuent1)+"\')="+i+"\n"
  cuent1=cuent1+1
 ineq_string=ineq_string_Automatic+ineq_string_User
elif Ineq_type=="User_defined" and merge_constraints=="0":
 numb_ineq=int(number_user_defined_ineq)
 cuent1=1;
 for i in Ineq:
  ineq_string_User=ineq_string_User+"gval(\'g"+str(cuent1)+"\')="+i+"\n"
  cuent1=cuent1+1
 ineq_string=ineq_string_User

Ineq_set="set extineq /g1*g"+str(numb_ineq)+"/; \n"
#print(Ineq_set)
#print(ineq_string)

#Reformulation with external variables_
recalculation_string="\n"
for i in Indep:
 recalculation_string=recalculation_string+"yaux_"+i+"(extvar,"+Indep[i][2]+")=0;\n"
 recalculation_string=recalculation_string+"yaux_"+i+"(extvar,"+Indep[i][2]+")$(ord("+Indep[i][2]+") eq floor(fex(extvar)))=1-mod(fex(extvar),1);\n"
 recalculation_string=recalculation_string+"yaux_"+i+"(extvar,"+Indep[i][2]+")$(ord("+Indep[i][2]+") eq 1+floor(fex(extvar)))=mod(fex(extvar),1);\n\n"
 recalculation_string=recalculation_string+Indep[i][0]+"("+Indep[i][2]+")=sum(s_"+i+",yaux_"+i+"(s_"+i+","+Indep[i][2]+"));\n"
recalculation_string=recalculation_string+'\n'.join(Dep)

#print(recalculation_string)

#treatment of logical constraints
logic_string1=""
logic_string2=""

if logic_sub=="1":
 logic_string1=logic_string1+"maxExecError=100000;"
 logic_string2=logic_string2+"ExecError=0;"
###Writing txts-----------------------------------------------------------------
file = open("neigh_values.csv",'w')
file.write(neigh_values)
file.close()

file=open("param_sets.txt",'w')
file.write(Ext+Ext_sub+neigh+Ineq_set)
file.close()

file=open("param_extaux.txt",'w')
file.write(Ext_aux+initialization_string)
file.close()

file=open("recalculation.txt",'w')
file.write(recalculation_string)
file.close()

file=open("reformulation.txt",'w')
file.write(reform_string)
file.close()

file=open("Inequalities.txt",'w')
file.write(ineq_string)
file.close()

file=open("logics1.txt",'w')
file.write(logic_string1)
file.close()

file=open("logics2.txt",'w')
file.write(logic_string2)
file.close()
$endEmbeddedCode
