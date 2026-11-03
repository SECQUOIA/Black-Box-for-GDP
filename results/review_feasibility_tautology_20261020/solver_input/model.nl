g3 1 1 0	# problem gdp_reactors
 156 303 1 0 155 	# vars, constraints, objectives, ranges, eqns
 47 0 0 0 0 0	# nonlinear constrs, objs; ccons: lin, nonlin, nd, nzlb
 0 0	# network constraints: nonlinear, linear
 93 0 0 	# nonlinear vars in constraints, objectives, both
 0 0 0 1	# linear network variables; functions; arith, flags
 0 0 0 0 0 	# discrete variables: binary, integer, nonlinear (b,c,o)
 407 15 	# nonzeros in Jacobian, obj. gradient
 44 10	# max name lengths: constraints, variables
 0 0 0 0 0	# common exprs: b,c,o,c1,o1
C0	#unreact_mole[A,15]
o2	#*
v44	#rate[A,15]
v74	#V[15]
C1	#unreact_mole[B,15]
o2	#*
v59	#rate[B,15]
v74	#V[15]
C2	#react_mole[A,1]
o2	#*
v30	#rate[A,1]
v60	#V[1]
C3	#react_mole[A,2]
o2	#*
v31	#rate[A,2]
v61	#V[2]
C4	#react_mole[A,3]
o2	#*
v32	#rate[A,3]
v62	#V[3]
C5	#react_mole[A,4]
o2	#*
v33	#rate[A,4]
v63	#V[4]
C6	#react_mole[A,5]
o2	#*
v34	#rate[A,5]
v64	#V[5]
C7	#react_mole[A,6]
o2	#*
v35	#rate[A,6]
v65	#V[6]
C8	#react_mole[A,7]
o2	#*
v36	#rate[A,7]
v66	#V[7]
C9	#react_mole[A,8]
o2	#*
v37	#rate[A,8]
v67	#V[8]
C10	#react_mole[A,9]
o2	#*
v38	#rate[A,9]
v68	#V[9]
C11	#react_mole[A,10]
o2	#*
v39	#rate[A,10]
v69	#V[10]
C12	#react_mole[A,11]
o2	#*
v40	#rate[A,11]
v70	#V[11]
C13	#react_mole[A,12]
o2	#*
v41	#rate[A,12]
v71	#V[12]
C14	#react_mole[A,13]
o2	#*
v42	#rate[A,13]
v72	#V[13]
C15	#react_mole[A,14]
o2	#*
v43	#rate[A,14]
v73	#V[14]
C16	#react_mole[B,1]
o2	#*
v45	#rate[B,1]
v60	#V[1]
C17	#react_mole[B,2]
o2	#*
v46	#rate[B,2]
v61	#V[2]
C18	#react_mole[B,3]
o2	#*
v47	#rate[B,3]
v62	#V[3]
C19	#react_mole[B,4]
o2	#*
v48	#rate[B,4]
v63	#V[4]
C20	#react_mole[B,5]
o2	#*
v49	#rate[B,5]
v64	#V[5]
C21	#react_mole[B,6]
o2	#*
v50	#rate[B,6]
v65	#V[6]
C22	#react_mole[B,7]
o2	#*
v51	#rate[B,7]
v66	#V[7]
C23	#react_mole[B,8]
o2	#*
v52	#rate[B,8]
v67	#V[8]
C24	#react_mole[B,9]
o2	#*
v53	#rate[B,9]
v68	#V[9]
C25	#react_mole[B,10]
o2	#*
v54	#rate[B,10]
v69	#V[10]
C26	#react_mole[B,11]
o2	#*
v55	#rate[B,11]
v70	#V[11]
C27	#react_mole[B,12]
o2	#*
v56	#rate[B,12]
v71	#V[12]
C28	#react_mole[B,13]
o2	#*
v57	#rate[B,13]
v72	#V[13]
C29	#react_mole[B,14]
o2	#*
v58	#rate[B,14]
v73	#V[14]
C30	#split_add[A]
o0	#+
o2	#*
v90	#P[A]
v75	#Q[1]
o16	#-
o2	#*
v0	#F[A,1]
v92	#QP
C31	#split_add[B]
o0	#+
o2	#*
v91	#P[B]
v75	#Q[1]
o16	#-
o2	#*
v15	#F[B,1]
v92	#QP
C32	#YP_is_cstr[1].YPD_rate_calc
o0	#+
o2	#*
o2	#*
v30	#rate[A,1]
v75	#Q[1]
v75	#Q[1]
o2	#*
o2	#*
n2
v0	#F[A,1]
v15	#F[B,1]
C33	#YP_is_cstr[2].YPD_rate_calc
o0	#+
o2	#*
o2	#*
v31	#rate[A,2]
v76	#Q[2]
v76	#Q[2]
o2	#*
o2	#*
n2
v1	#F[A,2]
v16	#F[B,2]
C34	#YP_is_cstr[3].YPD_rate_calc
o0	#+
o2	#*
o2	#*
v32	#rate[A,3]
v77	#Q[3]
v77	#Q[3]
o2	#*
o2	#*
n2
v2	#F[A,3]
v17	#F[B,3]
C35	#YP_is_cstr[4].YPD_rate_calc
o0	#+
o2	#*
o2	#*
v33	#rate[A,4]
v78	#Q[4]
v78	#Q[4]
o2	#*
o2	#*
n2
v3	#F[A,4]
v18	#F[B,4]
C36	#YP_is_cstr[5].YPD_rate_calc
o0	#+
o2	#*
o2	#*
v34	#rate[A,5]
v79	#Q[5]
v79	#Q[5]
o2	#*
o2	#*
n2
v4	#F[A,5]
v19	#F[B,5]
C37	#YP_is_cstr[6].YPD_rate_calc
o0	#+
o2	#*
o2	#*
v35	#rate[A,6]
v80	#Q[6]
v80	#Q[6]
o2	#*
o2	#*
n2
v5	#F[A,6]
v20	#F[B,6]
C38	#YP_is_cstr[7].YPD_rate_calc
o0	#+
o2	#*
o2	#*
v36	#rate[A,7]
v81	#Q[7]
v81	#Q[7]
o2	#*
o2	#*
n2
v6	#F[A,7]
v21	#F[B,7]
C39	#YP_is_cstr[8].YPD_rate_calc
o0	#+
o2	#*
o2	#*
v37	#rate[A,8]
v82	#Q[8]
v82	#Q[8]
o2	#*
o2	#*
n2
v7	#F[A,8]
v22	#F[B,8]
C40	#YP_is_cstr[9].YPD_rate_calc
o0	#+
o2	#*
o2	#*
v38	#rate[A,9]
v83	#Q[9]
v83	#Q[9]
o2	#*
o2	#*
n2
v8	#F[A,9]
v23	#F[B,9]
C41	#YP_is_cstr[10].YPD_rate_calc
o0	#+
o2	#*
o2	#*
v39	#rate[A,10]
v84	#Q[10]
v84	#Q[10]
o2	#*
o2	#*
n2
v9	#F[A,10]
v24	#F[B,10]
C42	#YP_is_cstr[11].YPD_rate_calc
o0	#+
o2	#*
o2	#*
v40	#rate[A,11]
v85	#Q[11]
v85	#Q[11]
o2	#*
o2	#*
n2
v10	#F[A,11]
v25	#F[B,11]
C43	#YP_is_cstr[12].YPD_rate_calc
o0	#+
o2	#*
o2	#*
v41	#rate[A,12]
v86	#Q[12]
v86	#Q[12]
o2	#*
o2	#*
n2
v11	#F[A,12]
v26	#F[B,12]
C44	#YP_is_cstr[13].YPD_rate_calc
o0	#+
o2	#*
o2	#*
v42	#rate[A,13]
v87	#Q[13]
v87	#Q[13]
o2	#*
o2	#*
n2
v12	#F[A,13]
v27	#F[B,13]
C45	#YP_is_cstr[14].YPD_rate_calc
o0	#+
o2	#*
o2	#*
v43	#rate[A,14]
v88	#Q[14]
v88	#Q[14]
o2	#*
o2	#*
n2
v13	#F[A,14]
v28	#F[B,14]
C46	#YP_is_cstr[15].YPD_rate_calc
o0	#+
o2	#*
o2	#*
v44	#rate[A,15]
v89	#Q[15]
v89	#Q[15]
o2	#*
o2	#*
n2
v14	#F[A,15]
v29	#F[B,15]
C47	#unreact_cont[15]
n0
C48	#react_cont[1]
n0
C49	#react_cont[2]
n0
C50	#react_cont[3]
n0
C51	#react_cont[4]
n0
C52	#react_cont[5]
n0
C53	#react_cont[6]
n0
C54	#react_cont[7]
n0
C55	#react_cont[8]
n0
C56	#react_cont[9]
n0
C57	#react_cont[10]
n0
C58	#react_cont[11]
n0
C59	#react_cont[12]
n0
C60	#react_cont[13]
n0
C61	#react_cont[14]
n0
C62	#split_mole[A]
n0
C63	#split_mole[B]
n0
C64	#split_cont
n0
C65	#prod_spec
n0
C66	#vol_cons[2]
n0
C67	#vol_cons[3]
n0
C68	#vol_cons[4]
n0
C69	#vol_cons[5]
n0
C70	#vol_cons[6]
n0
C71	#vol_cons[7]
n0
C72	#vol_cons[8]
n0
C73	#vol_cons[9]
n0
C74	#vol_cons[10]
n0
C75	#vol_cons[11]
n0
C76	#vol_cons[12]
n0
C77	#vol_cons[13]
n0
C78	#vol_cons[14]
n0
C79	#vol_cons[15]
n0
C80	#YR_is_recycle[15].YRD_FR_act[A]
n0
C81	#YR_is_recycle[15].YRD_FR_act[B]
n0
C82	#YR_is_recycle[15].YRD_QFR_act
n0
C83	#YR_is_not_recycle[1].neg_YRD_FR_desact[A]
n0
C84	#YR_is_not_recycle[1].neg_YRD_FR_desact[B]
n0
C85	#YR_is_not_recycle[1].neg_YRD_QFR_desact
n0
C86	#YR_is_not_recycle[2].neg_YRD_FR_desact[A]
n0
C87	#YR_is_not_recycle[2].neg_YRD_FR_desact[B]
n0
C88	#YR_is_not_recycle[2].neg_YRD_QFR_desact
n0
C89	#YR_is_not_recycle[3].neg_YRD_FR_desact[A]
n0
C90	#YR_is_not_recycle[3].neg_YRD_FR_desact[B]
n0
C91	#YR_is_not_recycle[3].neg_YRD_QFR_desact
n0
C92	#YR_is_not_recycle[4].neg_YRD_FR_desact[A]
n0
C93	#YR_is_not_recycle[4].neg_YRD_FR_desact[B]
n0
C94	#YR_is_not_recycle[4].neg_YRD_QFR_desact
n0
C95	#YR_is_not_recycle[5].neg_YRD_FR_desact[A]
n0
C96	#YR_is_not_recycle[5].neg_YRD_FR_desact[B]
n0
C97	#YR_is_not_recycle[5].neg_YRD_QFR_desact
n0
C98	#YR_is_not_recycle[6].neg_YRD_FR_desact[A]
n0
C99	#YR_is_not_recycle[6].neg_YRD_FR_desact[B]
n0
C100	#YR_is_not_recycle[6].neg_YRD_QFR_desact
n0
C101	#YR_is_not_recycle[7].neg_YRD_FR_desact[A]
n0
C102	#YR_is_not_recycle[7].neg_YRD_FR_desact[B]
n0
C103	#YR_is_not_recycle[7].neg_YRD_QFR_desact
n0
C104	#YR_is_not_recycle[8].neg_YRD_FR_desact[A]
n0
C105	#YR_is_not_recycle[8].neg_YRD_FR_desact[B]
n0
C106	#YR_is_not_recycle[8].neg_YRD_QFR_desact
n0
C107	#YR_is_not_recycle[9].neg_YRD_FR_desact[A]
n0
C108	#YR_is_not_recycle[9].neg_YRD_FR_desact[B]
n0
C109	#YR_is_not_recycle[9].neg_YRD_QFR_desact
n0
C110	#YR_is_not_recycle[10].neg_YRD_FR_desact[A]
n0
C111	#YR_is_not_recycle[10].neg_YRD_FR_desact[B]
n0
C112	#YR_is_not_recycle[10].neg_YRD_QFR_desact
n0
C113	#YR_is_not_recycle[11].neg_YRD_FR_desact[A]
n0
C114	#YR_is_not_recycle[11].neg_YRD_FR_desact[B]
n0
C115	#YR_is_not_recycle[11].neg_YRD_QFR_desact
n0
C116	#YR_is_not_recycle[12].neg_YRD_FR_desact[A]
n0
C117	#YR_is_not_recycle[12].neg_YRD_FR_desact[B]
n0
C118	#YR_is_not_recycle[12].neg_YRD_QFR_desact
n0
C119	#YR_is_not_recycle[13].neg_YRD_FR_desact[A]
n0
C120	#YR_is_not_recycle[13].neg_YRD_FR_desact[B]
n0
C121	#YR_is_not_recycle[13].neg_YRD_QFR_desact
n0
C122	#YR_is_not_recycle[14].neg_YRD_FR_desact[A]
n0
C123	#YR_is_not_recycle[14].neg_YRD_FR_desact[B]
n0
C124	#YR_is_not_recycle[14].neg_YRD_QFR_desact
n0
C125	#YP_is_cstr[1].YPD_rate_rel
n0
C126	#YP_is_cstr[1].YPD_vol_act
n0
C127	#YP_is_cstr[2].YPD_rate_rel
n0
C128	#YP_is_cstr[2].YPD_vol_act
n0
C129	#YP_is_cstr[3].YPD_rate_rel
n0
C130	#YP_is_cstr[3].YPD_vol_act
n0
C131	#YP_is_cstr[4].YPD_rate_rel
n0
C132	#YP_is_cstr[4].YPD_vol_act
n0
C133	#YP_is_cstr[5].YPD_rate_rel
n0
C134	#YP_is_cstr[5].YPD_vol_act
n0
C135	#YP_is_cstr[6].YPD_rate_rel
n0
C136	#YP_is_cstr[6].YPD_vol_act
n0
C137	#YP_is_cstr[7].YPD_rate_rel
n0
C138	#YP_is_cstr[7].YPD_vol_act
n0
C139	#YP_is_cstr[8].YPD_rate_rel
n0
C140	#YP_is_cstr[8].YPD_vol_act
n0
C141	#YP_is_cstr[9].YPD_rate_rel
n0
C142	#YP_is_cstr[9].YPD_vol_act
n0
C143	#YP_is_cstr[10].YPD_rate_rel
n0
C144	#YP_is_cstr[10].YPD_vol_act
n0
C145	#YP_is_cstr[11].YPD_rate_rel
n0
C146	#YP_is_cstr[11].YPD_vol_act
n0
C147	#YP_is_cstr[12].YPD_rate_rel
n0
C148	#YP_is_cstr[12].YPD_vol_act
n0
C149	#YP_is_cstr[13].YPD_rate_rel
n0
C150	#YP_is_cstr[13].YPD_vol_act
n0
C151	#YP_is_cstr[14].YPD_rate_rel
n0
C152	#YP_is_cstr[14].YPD_vol_act
n0
C153	#YP_is_cstr[15].YPD_rate_rel
n0
C154	#YP_is_cstr[15].YPD_vol_act
n0
C155	#logic_to_linear.transformed_constraints[1]
n0
C156	#logic_to_linear.transformed_constraints[2]
n0
C157	#logic_to_linear.transformed_constraints[3]
n0
C158	#logic_to_linear.transformed_constraints[4]
n0
C159	#logic_to_linear.transformed_constraints[5]
n0
C160	#logic_to_linear.transformed_constraints[6]
n0
C161	#logic_to_linear.transformed_constraints[7]
n0
C162	#logic_to_linear.transformed_constraints[8]
n0
C163	#logic_to_linear.transformed_constraints[9]
n0
C164	#logic_to_linear.transformed_constraints[10]
n0
C165	#logic_to_linear.transformed_constraints[11]
n0
C166	#logic_to_linear.transformed_constraints[12]
n0
C167	#logic_to_linear.transformed_constraints[13]
n0
C168	#logic_to_linear.transformed_constraints[14]
n0
C169	#logic_to_linear.transformed_constraints[15]
n0
C170	#logic_to_linear.transformed_constraints[19]
n0
C171	#logic_to_linear.transformed_constraints[20]
n0
C172	#logic_to_linear.transformed_constraints[21]
n0
C173	#logic_to_linear.transformed_constraints[22]
n0
C174	#logic_to_linear.transformed_constraints[23]
n0
C175	#logic_to_linear.transformed_constraints[24]
n0
C176	#logic_to_linear.transformed_constraints[25]
n0
C177	#logic_to_linear.transformed_constraints[26]
n0
C178	#logic_to_linear.transformed_constraints[27]
n0
C179	#logic_to_linear.transformed_constraints[28]
n0
C180	#logic_to_linear.transformed_constraints[29]
n0
C181	#logic_to_linear.transformed_constraints[30]
n0
C182	#logic_to_linear.transformed_constraints[31]
n0
C183	#logic_to_linear.transformed_constraints[32]
n0
C184	#logic_to_linear.transformed_constraints[33]
n0
C185	#logic_to_linear.transformed_constraints[34]
n0
C186	#logic_to_linear.transformed_constraints[35]
n0
C187	#logic_to_linear.transformed_constraints[36]
n0
C188	#logic_to_linear.transformed_constraints[37]
n0
C189	#logic_to_linear.transformed_constraints[38]
n0
C190	#logic_to_linear.transformed_constraints[39]
n0
C191	#logic_to_linear.transformed_constraints[40]
n0
C192	#logic_to_linear.transformed_constraints[41]
n0
C193	#logic_to_linear.transformed_constraints[42]
n0
C194	#logic_to_linear.transformed_constraints[43]
n0
C195	#logic_to_linear.transformed_constraints[44]
n0
C196	#logic_to_linear.transformed_constraints[45]
n0
C197	#logic_to_linear.transformed_constraints[46]
n0
C198	#logic_to_linear.transformed_constraints[47]
n0
C199	#logic_to_linear.transformed_constraints[48]
n0
C200	#logic_to_linear.transformed_constraints[49]
n0
C201	#logic_to_linear.transformed_constraints[50]
n0
C202	#logic_to_linear.transformed_constraints[51]
n0
C203	#logic_to_linear.transformed_constraints[52]
n0
C204	#logic_to_linear.transformed_constraints[53]
n0
C205	#logic_to_linear.transformed_constraints[54]
n0
C206	#logic_to_linear.transformed_constraints[55]
n0
C207	#logic_to_linear.transformed_constraints[56]
n0
C208	#logic_to_linear.transformed_constraints[57]
n0
C209	#logic_to_linear.transformed_constraints[58]
n0
C210	#logic_to_linear.transformed_constraints[59]
n0
C211	#logic_to_linear.transformed_constraints[60]
n0
C212	#logic_to_linear.transformed_constraints[61]
n0
C213	#logic_to_linear.transformed_constraints[62]
n0
C214	#logic_to_linear.transformed_constraints[63]
n0
C215	#logic_to_linear.transformed_constraints[64]
n0
C216	#logic_to_linear.transformed_constraints[65]
n0
C217	#logic_to_linear.transformed_constraints[66]
n0
C218	#logic_to_linear.transformed_constraints[67]
n0
C219	#logic_to_linear.transformed_constraints[68]
n0
C220	#logic_to_linear.transformed_constraints[69]
n0
C221	#logic_to_linear.transformed_constraints[70]
n0
C222	#logic_to_linear.transformed_constraints[71]
n0
C223	#logic_to_linear.transformed_constraints[72]
n0
C224	#logic_to_linear.transformed_constraints[73]
n0
C225	#logic_to_linear.transformed_constraints[74]
n0
C226	#logic_to_linear.transformed_constraints[75]
n0
C227	#logic_to_linear.transformed_constraints[76]
n0
C228	#logic_to_linear.transformed_constraints[77]
n0
C229	#logic_to_linear.transformed_constraints[78]
n0
C230	#logic_to_linear.transformed_constraints[79]
n0
C231	#logic_to_linear.transformed_constraints[80]
n0
C232	#logic_to_linear.transformed_constraints[81]
n0
C233	#logic_to_linear.transformed_constraints[82]
n0
C234	#logic_to_linear.transformed_constraints[83]
n0
C235	#logic_to_linear.transformed_constraints[84]
n0
C236	#logic_to_linear.transformed_constraints[85]
n0
C237	#logic_to_linear.transformed_constraints[86]
n0
C238	#logic_to_linear.transformed_constraints[87]
n0
C239	#logic_to_linear.transformed_constraints[88]
n0
C240	#logic_to_linear.transformed_constraints[89]
n0
C241	#logic_to_linear.transformed_constraints[90]
n0
C242	#logic_to_linear.transformed_constraints[91]
n0
C243	#logic_to_linear.transformed_constraints[92]
n0
C244	#logic_to_linear.transformed_constraints[93]
n0
C245	#logic_to_linear.transformed_constraints[94]
n0
C246	#logic_to_linear.transformed_constraints[95]
n0
C247	#logic_to_linear.transformed_constraints[96]
n0
C248	#logic_to_linear.transformed_constraints[97]
n0
C249	#logic_to_linear.transformed_constraints[98]
n0
C250	#logic_to_linear.transformed_constraints[99]
n0
C251	#logic_to_linear.transformed_constraints[100]
n0
C252	#logic_to_linear.transformed_constraints[101]
n0
C253	#logic_to_linear.transformed_constraints[102]
n0
C254	#logic_to_linear.transformed_constraints[103]
n0
C255	#logic_to_linear.transformed_constraints[104]
n0
C256	#logic_to_linear.transformed_constraints[105]
n0
C257	#logic_to_linear.transformed_constraints[106]
n0
C258	#logic_to_linear.transformed_constraints[107]
n0
C259	#logic_to_linear.transformed_constraints[108]
n0
C260	#logic_to_linear.transformed_constraints[109]
n0
C261	#logic_to_linear.transformed_constraints[110]
n0
C262	#logic_to_linear.transformed_constraints[111]
n0
C263	#logic_to_linear.transformed_constraints[112]
n0
C264	#logic_to_linear.transformed_constraints[113]
n0
C265	#logic_to_linear.transformed_constraints[114]
n0
C266	#logic_to_linear.transformed_constraints[115]
n0
C267	#logic_to_linear.transformed_constraints[116]
n0
C268	#logic_to_linear.transformed_constraints[117]
n0
C269	#logic_to_linear.transformed_constraints[118]
n0
C270	#logic_to_linear.transformed_constraints[119]
n0
C271	#logic_to_linear.transformed_constraints[120]
n0
C272	#logic_to_linear.transformed_constraints[121]
n0
C273	#logic_to_linear.transformed_constraints[122]
n0
C274	#logic_to_linear.transformed_constraints[123]
n0
C275	#logic_to_linear.transformed_constraints[124]
n0
C276	#logic_to_linear.transformed_constraints[125]
n0
C277	#logic_to_linear.transformed_constraints[126]
n0
C278	#logic_to_linear.transformed_constraints[127]
n0
C279	#logic_to_linear.transformed_constraints[128]
n0
C280	#logic_to_linear.transformed_constraints[129]
n0
C281	#logic_to_linear.transformed_constraints[130]
n0
C282	#logic_to_linear.transformed_constraints[131]
n0
C283	#logic_to_linear.transformed_constraints[132]
n0
C284	#logic_to_linear.transformed_constraints[133]
n0
C285	#logic_to_linear.transformed_constraints[134]
n0
C286	#logic_to_linear.transformed_constraints[135]
n0
C287	#logic_to_linear.transformed_constraints[136]
n0
C288	#logic_to_linear.transformed_constraints[137]
n0
C289	#logic_to_linear.transformed_constraints[138]
n0
C290	#logic_to_linear.transformed_constraints[139]
n0
C291	#logic_to_linear.transformed_constraints[140]
n0
C292	#logic_to_linear.transformed_constraints[141]
n0
C293	#logic_to_linear.transformed_constraints[142]
n0
C294	#logic_to_linear.transformed_constraints[143]
n0
C295	#logic_to_linear.transformed_constraints[144]
n0
C296	#logic_to_linear.transformed_constraints[145]
n0
C297	#logic_to_linear.transformed_constraints[146]
n0
C298	#logic_to_linear.transformed_constraints[147]
n0
C299	#logic_to_linear.transformed_constraints[148]
n0
C300	#logic_to_linear.transformed_constraints[149]
n0
C301	#logic_to_linear.transformed_constraints[150]
n0
C302	#logic_to_linear.transformed_constraints[151]
n0
O0 0	#obj
n0
x156	# initial guess
0 0.062278060199072	#F[A,1]
1 0.080197985894676	#F[A,2]
2 0.10292470695733	#F[A,3]
3 0.131522956079007	#F[A,4]
4 0.167152722810683	#F[A,5]
5 0.210986363370071	#F[A,6]
6 0.264065810272073	#F[A,7]
7 0.327090335160582	#F[A,8]
8 0.400143822588917	#F[A,9]
9 0.482404712242046	#F[A,10]
10 0.571926528611842	#F[A,11]
11 0.665610470790917	#F[A,12]
12 0.759476244352939	#F[A,13]
13 0.849243127341302	#F[A,14]
14 0.931081492129203	#F[A,15]
15 1.183241928722817	#F[B,1]
16 1.165321930154751	#F[B,2]
17 1.142595124391784	#F[B,3]
18 1.113996784160153	#F[B,4]
19 1.078366891318518	#F[B,5]
20 1.034533154022015	#F[B,6]
21 0.981453606947987	#F[B,7]
22 0.918428978962767	#F[B,8]
23 0.845375385880735	#F[B,9]
24 0.763114388266725	#F[B,10]
25 0.673592461776295	#F[B,11]
26 0.579908405195295	#F[B,12]
27 0.486042519426135	#F[B,13]
28 0.39627551975116	#F[B,14]
29 0.314437035685385	#F[B,15]
30 -0.095003341135379	#rate[A,1]
31 -0.120486821640815	#rate[A,2]
32 -0.151614950078144	#rate[A,3]
33 -0.188892943555139	#rate[A,4]
34 -0.232386084026629	#rate[A,5]
35 -0.281403125001094	#rate[A,6]
36 -0.334127380694455	#rate[A,7]
37 -0.387296094123976	#rate[A,8]
38 -0.436109784732075	#rate[A,9]
39 -0.474603895924898	#rate[A,10]
40 -0.496669912317388	#rate[A,11]
41 -0.497633565002774	#rate[A,12]
42 -0.475903142895273	#rate[A,13]
43 -0.433869779144965	#rate[A,14]
44 -0.377443110917706	#rate[A,15]
45 0.095003341135379	#rate[B,1]
46 0.120486821640815	#rate[B,2]
47 0.151614950078144	#rate[B,3]
48 0.188892943555139	#rate[B,4]
49 0.232386084026629	#rate[B,5]
50 0.281403125001094	#rate[B,6]
51 0.334127380694455	#rate[B,7]
52 0.387296094123976	#rate[B,8]
53 0.436109784732075	#rate[B,9]
54 0.474603895924898	#rate[B,10]
55 0.496669912317388	#rate[B,11]
56 0.497633565002774	#rate[B,12]
57 0.475903142895273	#rate[B,13]
58 0.433869779144965	#rate[B,14]
59 0.377443110917706	#rate[B,15]
60 0.188623374549076	#V[1]
61 0.188623374549076	#V[2]
62 0.188623374549076	#V[3]
63 0.188623374549076	#V[4]
64 0.188623374549076	#V[5]
65 0.188623374549076	#V[6]
66 0.188623374549076	#V[7]
67 0.188623374549076	#V[8]
68 0.188623374549076	#V[9]
69 0.188623374549076	#V[10]
70 0.188623374549076	#V[11]
71 0.188623374549076	#V[12]
72 0.188623374549076	#V[13]
73 0.188623374549076	#V[14]
74 0.188623374549076	#V[15]
75 1.245517805372418	#Q[1]
76 1.245517805372418	#Q[2]
77 1.245517805372418	#Q[3]
78 1.245517805372418	#Q[4]
79 1.245517805372418	#Q[5]
80 1.245517805372418	#Q[6]
81 1.245517805372418	#Q[7]
82 1.245517805372418	#Q[8]
83 1.245517805372418	#Q[9]
84 1.245517805372418	#Q[10]
85 1.245517805372418	#Q[11]
86 1.245517805372418	#Q[12]
87 1.245517805372418	#Q[13]
88 1.245517805372418	#Q[14]
89 1.245517805372418	#Q[15]
90 0.050001706008645	#P[A]
91 0.95	#P[B]
92 1.0	#QP
93 0.188623374549076	#c[1]
94 0.188623374549076	#c[2]
95 0.188623374549076	#c[3]
96 0.188623374549076	#c[4]
97 0.188623374549076	#c[5]
98 0.188623374549076	#c[6]
99 0.188623374549076	#c[7]
100 0.188623374549076	#c[8]
101 0.188623374549076	#c[9]
102 0.188623374549076	#c[10]
103 0.188623374549076	#c[11]
104 0.188623374549076	#c[12]
105 0.188623374549076	#c[13]
106 0.188623374549076	#c[14]
107 0.188623374549076	#c[15]
108 0	#FR[A,1]
109 0	#FR[A,2]
110 0	#FR[A,3]
111 0	#FR[A,4]
112 0	#FR[A,5]
113 0	#FR[A,6]
114 0	#FR[A,7]
115 0	#FR[A,8]
116 0	#FR[A,9]
117 0	#FR[A,10]
118 0	#FR[A,11]
119 0	#FR[A,12]
120 0	#FR[A,13]
121 0	#FR[A,14]
122 0.012276409955186	#FR[A,15]
123 0	#FR[B,1]
124 0	#FR[B,2]
125 0	#FR[B,3]
126 0	#FR[B,4]
127 0	#FR[B,5]
128 0	#FR[B,6]
129 0	#FR[B,7]
130 0	#FR[B,8]
131 0	#FR[B,9]
132 0	#FR[B,10]
133 0	#FR[B,11]
134 0	#FR[B,12]
135 0	#FR[B,13]
136 0	#FR[B,14]
137 0.23324199491819	#FR[B,15]
138 0	#QFR[1]
139 0	#QFR[2]
140 0	#QFR[3]
141 0	#QFR[4]
142 0	#QFR[5]
143 0	#QFR[6]
144 0	#QFR[7]
145 0	#QFR[8]
146 0	#QFR[9]
147 0	#QFR[10]
148 0	#QFR[11]
149 0	#QFR[12]
150 0	#QFR[13]
151 0	#QFR[14]
152 0.245517805372418	#QFR[15]
153 0.012276409955186	#R[A]
154 0.23324199491819	#R[B]
155 0.245517805372418	#QR
r	#303 ranges (rhs's)
4 -0.99	#unreact_mole[A,15]
4 -0.01	#unreact_mole[B,15]
4 0	#react_mole[A,1]
4 0	#react_mole[A,2]
4 0	#react_mole[A,3]
4 0	#react_mole[A,4]
4 0	#react_mole[A,5]
4 0	#react_mole[A,6]
4 0	#react_mole[A,7]
4 0	#react_mole[A,8]
4 0	#react_mole[A,9]
4 0	#react_mole[A,10]
4 0	#react_mole[A,11]
4 0	#react_mole[A,12]
4 0	#react_mole[A,13]
4 0	#react_mole[A,14]
4 0	#react_mole[B,1]
4 0	#react_mole[B,2]
4 0	#react_mole[B,3]
4 0	#react_mole[B,4]
4 0	#react_mole[B,5]
4 0	#react_mole[B,6]
4 0	#react_mole[B,7]
4 0	#react_mole[B,8]
4 0	#react_mole[B,9]
4 0	#react_mole[B,10]
4 0	#react_mole[B,11]
4 0	#react_mole[B,12]
4 0	#react_mole[B,13]
4 0	#react_mole[B,14]
4 0	#split_add[A]
4 0	#split_add[B]
4 0	#YP_is_cstr[1].YPD_rate_calc
4 0	#YP_is_cstr[2].YPD_rate_calc
4 0	#YP_is_cstr[3].YPD_rate_calc
4 0	#YP_is_cstr[4].YPD_rate_calc
4 0	#YP_is_cstr[5].YPD_rate_calc
4 0	#YP_is_cstr[6].YPD_rate_calc
4 0	#YP_is_cstr[7].YPD_rate_calc
4 0	#YP_is_cstr[8].YPD_rate_calc
4 0	#YP_is_cstr[9].YPD_rate_calc
4 0	#YP_is_cstr[10].YPD_rate_calc
4 0	#YP_is_cstr[11].YPD_rate_calc
4 0	#YP_is_cstr[12].YPD_rate_calc
4 0	#YP_is_cstr[13].YPD_rate_calc
4 0	#YP_is_cstr[14].YPD_rate_calc
4 0	#YP_is_cstr[15].YPD_rate_calc
4 -1	#unreact_cont[15]
4 0	#react_cont[1]
4 0	#react_cont[2]
4 0	#react_cont[3]
4 0	#react_cont[4]
4 0	#react_cont[5]
4 0	#react_cont[6]
4 0	#react_cont[7]
4 0	#react_cont[8]
4 0	#react_cont[9]
4 0	#react_cont[10]
4 0	#react_cont[11]
4 0	#react_cont[12]
4 0	#react_cont[13]
4 0	#react_cont[14]
4 0	#split_mole[A]
4 0	#split_mole[B]
4 0	#split_cont
4 0	#prod_spec
4 0	#vol_cons[2]
4 0	#vol_cons[3]
4 0	#vol_cons[4]
4 0	#vol_cons[5]
4 0	#vol_cons[6]
4 0	#vol_cons[7]
4 0	#vol_cons[8]
4 0	#vol_cons[9]
4 0	#vol_cons[10]
4 0	#vol_cons[11]
4 0	#vol_cons[12]
4 0	#vol_cons[13]
4 0	#vol_cons[14]
4 0	#vol_cons[15]
4 0	#YR_is_recycle[15].YRD_FR_act[A]
4 0	#YR_is_recycle[15].YRD_FR_act[B]
4 0	#YR_is_recycle[15].YRD_QFR_act
4 0	#YR_is_not_recycle[1].neg_YRD_FR_desact[A]
4 0	#YR_is_not_recycle[1].neg_YRD_FR_desact[B]
4 0	#YR_is_not_recycle[1].neg_YRD_QFR_desact
4 0	#YR_is_not_recycle[2].neg_YRD_FR_desact[A]
4 0	#YR_is_not_recycle[2].neg_YRD_FR_desact[B]
4 0	#YR_is_not_recycle[2].neg_YRD_QFR_desact
4 0	#YR_is_not_recycle[3].neg_YRD_FR_desact[A]
4 0	#YR_is_not_recycle[3].neg_YRD_FR_desact[B]
4 0	#YR_is_not_recycle[3].neg_YRD_QFR_desact
4 0	#YR_is_not_recycle[4].neg_YRD_FR_desact[A]
4 0	#YR_is_not_recycle[4].neg_YRD_FR_desact[B]
4 0	#YR_is_not_recycle[4].neg_YRD_QFR_desact
4 0	#YR_is_not_recycle[5].neg_YRD_FR_desact[A]
4 0	#YR_is_not_recycle[5].neg_YRD_FR_desact[B]
4 0	#YR_is_not_recycle[5].neg_YRD_QFR_desact
4 0	#YR_is_not_recycle[6].neg_YRD_FR_desact[A]
4 0	#YR_is_not_recycle[6].neg_YRD_FR_desact[B]
4 0	#YR_is_not_recycle[6].neg_YRD_QFR_desact
4 0	#YR_is_not_recycle[7].neg_YRD_FR_desact[A]
4 0	#YR_is_not_recycle[7].neg_YRD_FR_desact[B]
4 0	#YR_is_not_recycle[7].neg_YRD_QFR_desact
4 0	#YR_is_not_recycle[8].neg_YRD_FR_desact[A]
4 0	#YR_is_not_recycle[8].neg_YRD_FR_desact[B]
4 0	#YR_is_not_recycle[8].neg_YRD_QFR_desact
4 0	#YR_is_not_recycle[9].neg_YRD_FR_desact[A]
4 0	#YR_is_not_recycle[9].neg_YRD_FR_desact[B]
4 0	#YR_is_not_recycle[9].neg_YRD_QFR_desact
4 0	#YR_is_not_recycle[10].neg_YRD_FR_desact[A]
4 0	#YR_is_not_recycle[10].neg_YRD_FR_desact[B]
4 0	#YR_is_not_recycle[10].neg_YRD_QFR_desact
4 0	#YR_is_not_recycle[11].neg_YRD_FR_desact[A]
4 0	#YR_is_not_recycle[11].neg_YRD_FR_desact[B]
4 0	#YR_is_not_recycle[11].neg_YRD_QFR_desact
4 0	#YR_is_not_recycle[12].neg_YRD_FR_desact[A]
4 0	#YR_is_not_recycle[12].neg_YRD_FR_desact[B]
4 0	#YR_is_not_recycle[12].neg_YRD_QFR_desact
4 0	#YR_is_not_recycle[13].neg_YRD_FR_desact[A]
4 0	#YR_is_not_recycle[13].neg_YRD_FR_desact[B]
4 0	#YR_is_not_recycle[13].neg_YRD_QFR_desact
4 0	#YR_is_not_recycle[14].neg_YRD_FR_desact[A]
4 0	#YR_is_not_recycle[14].neg_YRD_FR_desact[B]
4 0	#YR_is_not_recycle[14].neg_YRD_QFR_desact
4 0	#YP_is_cstr[1].YPD_rate_rel
4 0	#YP_is_cstr[1].YPD_vol_act
4 0	#YP_is_cstr[2].YPD_rate_rel
4 0	#YP_is_cstr[2].YPD_vol_act
4 0	#YP_is_cstr[3].YPD_rate_rel
4 0	#YP_is_cstr[3].YPD_vol_act
4 0	#YP_is_cstr[4].YPD_rate_rel
4 0	#YP_is_cstr[4].YPD_vol_act
4 0	#YP_is_cstr[5].YPD_rate_rel
4 0	#YP_is_cstr[5].YPD_vol_act
4 0	#YP_is_cstr[6].YPD_rate_rel
4 0	#YP_is_cstr[6].YPD_vol_act
4 0	#YP_is_cstr[7].YPD_rate_rel
4 0	#YP_is_cstr[7].YPD_vol_act
4 0	#YP_is_cstr[8].YPD_rate_rel
4 0	#YP_is_cstr[8].YPD_vol_act
4 0	#YP_is_cstr[9].YPD_rate_rel
4 0	#YP_is_cstr[9].YPD_vol_act
4 0	#YP_is_cstr[10].YPD_rate_rel
4 0	#YP_is_cstr[10].YPD_vol_act
4 0	#YP_is_cstr[11].YPD_rate_rel
4 0	#YP_is_cstr[11].YPD_vol_act
4 0	#YP_is_cstr[12].YPD_rate_rel
4 0	#YP_is_cstr[12].YPD_vol_act
4 0	#YP_is_cstr[13].YPD_rate_rel
4 0	#YP_is_cstr[13].YPD_vol_act
4 0	#YP_is_cstr[14].YPD_rate_rel
4 0	#YP_is_cstr[14].YPD_vol_act
4 0	#YP_is_cstr[15].YPD_rate_rel
4 0	#YP_is_cstr[15].YPD_vol_act
2 -1	#logic_to_linear.transformed_constraints[1]
2 -1	#logic_to_linear.transformed_constraints[2]
2 -1	#logic_to_linear.transformed_constraints[3]
2 -1	#logic_to_linear.transformed_constraints[4]
2 -1	#logic_to_linear.transformed_constraints[5]
2 -1	#logic_to_linear.transformed_constraints[6]
2 -1	#logic_to_linear.transformed_constraints[7]
2 -1	#logic_to_linear.transformed_constraints[8]
2 -1	#logic_to_linear.transformed_constraints[9]
2 -1	#logic_to_linear.transformed_constraints[10]
2 -1	#logic_to_linear.transformed_constraints[11]
2 -1	#logic_to_linear.transformed_constraints[12]
2 -1	#logic_to_linear.transformed_constraints[13]
2 -1	#logic_to_linear.transformed_constraints[14]
2 0	#logic_to_linear.transformed_constraints[15]
2 0	#logic_to_linear.transformed_constraints[19]
2 -1	#logic_to_linear.transformed_constraints[20]
2 0	#logic_to_linear.transformed_constraints[21]
2 -1	#logic_to_linear.transformed_constraints[22]
2 0	#logic_to_linear.transformed_constraints[23]
2 0	#logic_to_linear.transformed_constraints[24]
2 0	#logic_to_linear.transformed_constraints[25]
2 -1	#logic_to_linear.transformed_constraints[26]
2 0	#logic_to_linear.transformed_constraints[27]
2 0	#logic_to_linear.transformed_constraints[28]
2 0	#logic_to_linear.transformed_constraints[29]
2 0	#logic_to_linear.transformed_constraints[30]
2 -1	#logic_to_linear.transformed_constraints[31]
2 0	#logic_to_linear.transformed_constraints[32]
2 0	#logic_to_linear.transformed_constraints[33]
2 0	#logic_to_linear.transformed_constraints[34]
2 0	#logic_to_linear.transformed_constraints[35]
2 0	#logic_to_linear.transformed_constraints[36]
2 -1	#logic_to_linear.transformed_constraints[37]
2 0	#logic_to_linear.transformed_constraints[38]
2 0	#logic_to_linear.transformed_constraints[39]
2 0	#logic_to_linear.transformed_constraints[40]
2 0	#logic_to_linear.transformed_constraints[41]
2 0	#logic_to_linear.transformed_constraints[42]
2 0	#logic_to_linear.transformed_constraints[43]
2 -1	#logic_to_linear.transformed_constraints[44]
2 0	#logic_to_linear.transformed_constraints[45]
2 0	#logic_to_linear.transformed_constraints[46]
2 0	#logic_to_linear.transformed_constraints[47]
2 0	#logic_to_linear.transformed_constraints[48]
2 0	#logic_to_linear.transformed_constraints[49]
2 0	#logic_to_linear.transformed_constraints[50]
2 0	#logic_to_linear.transformed_constraints[51]
2 -1	#logic_to_linear.transformed_constraints[52]
2 0	#logic_to_linear.transformed_constraints[53]
2 0	#logic_to_linear.transformed_constraints[54]
2 0	#logic_to_linear.transformed_constraints[55]
2 0	#logic_to_linear.transformed_constraints[56]
2 0	#logic_to_linear.transformed_constraints[57]
2 0	#logic_to_linear.transformed_constraints[58]
2 0	#logic_to_linear.transformed_constraints[59]
2 0	#logic_to_linear.transformed_constraints[60]
2 -1	#logic_to_linear.transformed_constraints[61]
2 0	#logic_to_linear.transformed_constraints[62]
2 0	#logic_to_linear.transformed_constraints[63]
2 0	#logic_to_linear.transformed_constraints[64]
2 0	#logic_to_linear.transformed_constraints[65]
2 0	#logic_to_linear.transformed_constraints[66]
2 0	#logic_to_linear.transformed_constraints[67]
2 0	#logic_to_linear.transformed_constraints[68]
2 0	#logic_to_linear.transformed_constraints[69]
2 0	#logic_to_linear.transformed_constraints[70]
2 -1	#logic_to_linear.transformed_constraints[71]
2 0	#logic_to_linear.transformed_constraints[72]
2 0	#logic_to_linear.transformed_constraints[73]
2 0	#logic_to_linear.transformed_constraints[74]
2 0	#logic_to_linear.transformed_constraints[75]
2 0	#logic_to_linear.transformed_constraints[76]
2 0	#logic_to_linear.transformed_constraints[77]
2 0	#logic_to_linear.transformed_constraints[78]
2 0	#logic_to_linear.transformed_constraints[79]
2 0	#logic_to_linear.transformed_constraints[80]
2 0	#logic_to_linear.transformed_constraints[81]
2 -1	#logic_to_linear.transformed_constraints[82]
2 0	#logic_to_linear.transformed_constraints[83]
2 0	#logic_to_linear.transformed_constraints[84]
2 0	#logic_to_linear.transformed_constraints[85]
2 0	#logic_to_linear.transformed_constraints[86]
2 0	#logic_to_linear.transformed_constraints[87]
2 0	#logic_to_linear.transformed_constraints[88]
2 0	#logic_to_linear.transformed_constraints[89]
2 0	#logic_to_linear.transformed_constraints[90]
2 0	#logic_to_linear.transformed_constraints[91]
2 0	#logic_to_linear.transformed_constraints[92]
2 0	#logic_to_linear.transformed_constraints[93]
2 -1	#logic_to_linear.transformed_constraints[94]
2 0	#logic_to_linear.transformed_constraints[95]
2 0	#logic_to_linear.transformed_constraints[96]
2 0	#logic_to_linear.transformed_constraints[97]
2 0	#logic_to_linear.transformed_constraints[98]
2 0	#logic_to_linear.transformed_constraints[99]
2 0	#logic_to_linear.transformed_constraints[100]
2 0	#logic_to_linear.transformed_constraints[101]
2 0	#logic_to_linear.transformed_constraints[102]
2 0	#logic_to_linear.transformed_constraints[103]
2 0	#logic_to_linear.transformed_constraints[104]
2 0	#logic_to_linear.transformed_constraints[105]
2 0	#logic_to_linear.transformed_constraints[106]
2 -1	#logic_to_linear.transformed_constraints[107]
2 0	#logic_to_linear.transformed_constraints[108]
2 0	#logic_to_linear.transformed_constraints[109]
2 0	#logic_to_linear.transformed_constraints[110]
2 0	#logic_to_linear.transformed_constraints[111]
2 0	#logic_to_linear.transformed_constraints[112]
2 0	#logic_to_linear.transformed_constraints[113]
2 0	#logic_to_linear.transformed_constraints[114]
2 0	#logic_to_linear.transformed_constraints[115]
2 0	#logic_to_linear.transformed_constraints[116]
2 0	#logic_to_linear.transformed_constraints[117]
2 0	#logic_to_linear.transformed_constraints[118]
2 0	#logic_to_linear.transformed_constraints[119]
2 0	#logic_to_linear.transformed_constraints[120]
2 -1	#logic_to_linear.transformed_constraints[121]
2 0	#logic_to_linear.transformed_constraints[122]
2 0	#logic_to_linear.transformed_constraints[123]
2 0	#logic_to_linear.transformed_constraints[124]
2 0	#logic_to_linear.transformed_constraints[125]
2 0	#logic_to_linear.transformed_constraints[126]
2 0	#logic_to_linear.transformed_constraints[127]
2 0	#logic_to_linear.transformed_constraints[128]
2 0	#logic_to_linear.transformed_constraints[129]
2 0	#logic_to_linear.transformed_constraints[130]
2 0	#logic_to_linear.transformed_constraints[131]
2 0	#logic_to_linear.transformed_constraints[132]
2 0	#logic_to_linear.transformed_constraints[133]
2 0	#logic_to_linear.transformed_constraints[134]
2 0	#logic_to_linear.transformed_constraints[135]
2 0	#logic_to_linear.transformed_constraints[136]
2 -1	#logic_to_linear.transformed_constraints[137]
2 -1	#logic_to_linear.transformed_constraints[138]
2 -1	#logic_to_linear.transformed_constraints[139]
2 -1	#logic_to_linear.transformed_constraints[140]
2 -1	#logic_to_linear.transformed_constraints[141]
2 -1	#logic_to_linear.transformed_constraints[142]
2 -1	#logic_to_linear.transformed_constraints[143]
2 -1	#logic_to_linear.transformed_constraints[144]
2 -1	#logic_to_linear.transformed_constraints[145]
2 -1	#logic_to_linear.transformed_constraints[146]
2 -1	#logic_to_linear.transformed_constraints[147]
2 -1	#logic_to_linear.transformed_constraints[148]
2 -1	#logic_to_linear.transformed_constraints[149]
2 -1	#logic_to_linear.transformed_constraints[150]
2 0	#logic_to_linear.transformed_constraints[151]
b	#156 bounds (on variables)
0 0 10	#F[A,1]
0 0 10	#F[A,2]
0 0 10	#F[A,3]
0 0 10	#F[A,4]
0 0 10	#F[A,5]
0 0 10	#F[A,6]
0 0 10	#F[A,7]
0 0 10	#F[A,8]
0 0 10	#F[A,9]
0 0 10	#F[A,10]
0 0 10	#F[A,11]
0 0 10	#F[A,12]
0 0 10	#F[A,13]
0 0 10	#F[A,14]
0 0 10	#F[A,15]
0 0 10	#F[B,1]
0 0 10	#F[B,2]
0 0 10	#F[B,3]
0 0 10	#F[B,4]
0 0 10	#F[B,5]
0 0 10	#F[B,6]
0 0 10	#F[B,7]
0 0 10	#F[B,8]
0 0 10	#F[B,9]
0 0 10	#F[B,10]
0 0 10	#F[B,11]
0 0 10	#F[B,12]
0 0 10	#F[B,13]
0 0 10	#F[B,14]
0 0 10	#F[B,15]
0 -10 10	#rate[A,1]
0 -10 10	#rate[A,2]
0 -10 10	#rate[A,3]
0 -10 10	#rate[A,4]
0 -10 10	#rate[A,5]
0 -10 10	#rate[A,6]
0 -10 10	#rate[A,7]
0 -10 10	#rate[A,8]
0 -10 10	#rate[A,9]
0 -10 10	#rate[A,10]
0 -10 10	#rate[A,11]
0 -10 10	#rate[A,12]
0 -10 10	#rate[A,13]
0 -10 10	#rate[A,14]
0 -10 10	#rate[A,15]
0 -10 10	#rate[B,1]
0 -10 10	#rate[B,2]
0 -10 10	#rate[B,3]
0 -10 10	#rate[B,4]
0 -10 10	#rate[B,5]
0 -10 10	#rate[B,6]
0 -10 10	#rate[B,7]
0 -10 10	#rate[B,8]
0 -10 10	#rate[B,9]
0 -10 10	#rate[B,10]
0 -10 10	#rate[B,11]
0 -10 10	#rate[B,12]
0 -10 10	#rate[B,13]
0 -10 10	#rate[B,14]
0 -10 10	#rate[B,15]
0 0 10	#V[1]
0 0 10	#V[2]
0 0 10	#V[3]
0 0 10	#V[4]
0 0 10	#V[5]
0 0 10	#V[6]
0 0 10	#V[7]
0 0 10	#V[8]
0 0 10	#V[9]
0 0 10	#V[10]
0 0 10	#V[11]
0 0 10	#V[12]
0 0 10	#V[13]
0 0 10	#V[14]
0 0 10	#V[15]
0 1.0 10	#Q[1]
0 1.0 10	#Q[2]
0 1.0 10	#Q[3]
0 1.0 10	#Q[4]
0 1.0 10	#Q[5]
0 1.0 10	#Q[6]
0 1.0 10	#Q[7]
0 1.0 10	#Q[8]
0 1.0 10	#Q[9]
0 1.0 10	#Q[10]
0 1.0 10	#Q[11]
0 1.0 10	#Q[12]
0 1.0 10	#Q[13]
0 1.0 10	#Q[14]
0 1.0 10	#Q[15]
0 0 10	#P[A]
0 0 9.5	#P[B]
0 0 10	#QP
0 0 10	#c[1]
0 0 10	#c[2]
0 0 10	#c[3]
0 0 10	#c[4]
0 0 10	#c[5]
0 0 10	#c[6]
0 0 10	#c[7]
0 0 10	#c[8]
0 0 10	#c[9]
0 0 10	#c[10]
0 0 10	#c[11]
0 0 10	#c[12]
0 0 10	#c[13]
0 0 10	#c[14]
0 0 10	#c[15]
0 0 10	#FR[A,1]
0 0 10	#FR[A,2]
0 0 10	#FR[A,3]
0 0 10	#FR[A,4]
0 0 10	#FR[A,5]
0 0 10	#FR[A,6]
0 0 10	#FR[A,7]
0 0 10	#FR[A,8]
0 0 10	#FR[A,9]
0 0 10	#FR[A,10]
0 0 10	#FR[A,11]
0 0 10	#FR[A,12]
0 0 10	#FR[A,13]
0 0 10	#FR[A,14]
0 0 10	#FR[A,15]
0 0 10	#FR[B,1]
0 0 10	#FR[B,2]
0 0 10	#FR[B,3]
0 0 10	#FR[B,4]
0 0 10	#FR[B,5]
0 0 10	#FR[B,6]
0 0 10	#FR[B,7]
0 0 10	#FR[B,8]
0 0 10	#FR[B,9]
0 0 10	#FR[B,10]
0 0 10	#FR[B,11]
0 0 10	#FR[B,12]
0 0 10	#FR[B,13]
0 0 10	#FR[B,14]
0 0 10	#FR[B,15]
0 0 9.0	#QFR[1]
0 0 9.0	#QFR[2]
0 0 9.0	#QFR[3]
0 0 9.0	#QFR[4]
0 0 9.0	#QFR[5]
0 0 9.0	#QFR[6]
0 0 9.0	#QFR[7]
0 0 9.0	#QFR[8]
0 0 9.0	#QFR[9]
0 0 9.0	#QFR[10]
0 0 9.0	#QFR[11]
0 0 9.0	#QFR[12]
0 0 9.0	#QFR[13]
0 0 9.0	#QFR[14]
0 0 9	#QFR[15]
0 0 10	#R[A]
0 0 10	#R[B]
0 0 10	#QR
k155	#intermediate Jacobian column lengths
4
7
10
13
16
19
22
25
28
31
34
37
40
43
46
50
53
56
59
62
65
68
71
74
77
80
83
86
89
92
95
98
101
104
107
110
113
116
119
122
125
128
131
134
137
139
141
143
145
147
149
151
153
155
157
159
161
163
165
167
171
176
181
186
191
196
201
206
211
216
221
226
231
236
240
245
248
251
254
257
260
263
266
269
272
275
278
281
284
287
289
292
296
297
298
299
300
301
302
303
304
305
306
307
308
309
310
311
313
315
317
319
321
323
325
327
329
331
333
335
337
339
341
343
345
347
349
351
353
355
357
359
361
363
365
367
369
371
373
375
377
379
381
383
385
387
389
391
393
395
397
399
401
403
405
J0 4	#unreact_mole[A,15]
14 -1
44 0
74 0
122 1
J1 4	#unreact_mole[B,15]
29 -1
59 0
74 0
137 1
J2 5	#react_mole[A,1]
0 -1
1 1
30 0
60 0
108 1
J3 5	#react_mole[A,2]
1 -1
2 1
31 0
61 0
109 1
J4 5	#react_mole[A,3]
2 -1
3 1
32 0
62 0
110 1
J5 5	#react_mole[A,4]
3 -1
4 1
33 0
63 0
111 1
J6 5	#react_mole[A,5]
4 -1
5 1
34 0
64 0
112 1
J7 5	#react_mole[A,6]
5 -1
6 1
35 0
65 0
113 1
J8 5	#react_mole[A,7]
6 -1
7 1
36 0
66 0
114 1
J9 5	#react_mole[A,8]
7 -1
8 1
37 0
67 0
115 1
J10 5	#react_mole[A,9]
8 -1
9 1
38 0
68 0
116 1
J11 5	#react_mole[A,10]
9 -1
10 1
39 0
69 0
117 1
J12 5	#react_mole[A,11]
10 -1
11 1
40 0
70 0
118 1
J13 5	#react_mole[A,12]
11 -1
12 1
41 0
71 0
119 1
J14 5	#react_mole[A,13]
12 -1
13 1
42 0
72 0
120 1
J15 5	#react_mole[A,14]
13 -1
14 1
43 0
73 0
121 1
J16 5	#react_mole[B,1]
15 -1
16 1
45 0
60 0
123 1
J17 5	#react_mole[B,2]
16 -1
17 1
46 0
61 0
124 1
J18 5	#react_mole[B,3]
17 -1
18 1
47 0
62 0
125 1
J19 5	#react_mole[B,4]
18 -1
19 1
48 0
63 0
126 1
J20 5	#react_mole[B,5]
19 -1
20 1
49 0
64 0
127 1
J21 5	#react_mole[B,6]
20 -1
21 1
50 0
65 0
128 1
J22 5	#react_mole[B,7]
21 -1
22 1
51 0
66 0
129 1
J23 5	#react_mole[B,8]
22 -1
23 1
52 0
67 0
130 1
J24 5	#react_mole[B,9]
23 -1
24 1
53 0
68 0
131 1
J25 5	#react_mole[B,10]
24 -1
25 1
54 0
69 0
132 1
J26 5	#react_mole[B,11]
25 -1
26 1
55 0
70 0
133 1
J27 5	#react_mole[B,12]
26 -1
27 1
56 0
71 0
134 1
J28 5	#react_mole[B,13]
27 -1
28 1
57 0
72 0
135 1
J29 5	#react_mole[B,14]
28 -1
29 1
58 0
73 0
136 1
J30 4	#split_add[A]
0 0
75 0
90 0
92 0
J31 4	#split_add[B]
15 0
75 0
91 0
92 0
J32 4	#YP_is_cstr[1].YPD_rate_calc
0 0
15 0
30 0
75 0
J33 4	#YP_is_cstr[2].YPD_rate_calc
1 0
16 0
31 0
76 0
J34 4	#YP_is_cstr[3].YPD_rate_calc
2 0
17 0
32 0
77 0
J35 4	#YP_is_cstr[4].YPD_rate_calc
3 0
18 0
33 0
78 0
J36 4	#YP_is_cstr[5].YPD_rate_calc
4 0
19 0
34 0
79 0
J37 4	#YP_is_cstr[6].YPD_rate_calc
5 0
20 0
35 0
80 0
J38 4	#YP_is_cstr[7].YPD_rate_calc
6 0
21 0
36 0
81 0
J39 4	#YP_is_cstr[8].YPD_rate_calc
7 0
22 0
37 0
82 0
J40 4	#YP_is_cstr[9].YPD_rate_calc
8 0
23 0
38 0
83 0
J41 4	#YP_is_cstr[10].YPD_rate_calc
9 0
24 0
39 0
84 0
J42 4	#YP_is_cstr[11].YPD_rate_calc
10 0
25 0
40 0
85 0
J43 4	#YP_is_cstr[12].YPD_rate_calc
11 0
26 0
41 0
86 0
J44 4	#YP_is_cstr[13].YPD_rate_calc
12 0
27 0
42 0
87 0
J45 4	#YP_is_cstr[14].YPD_rate_calc
13 0
28 0
43 0
88 0
J46 4	#YP_is_cstr[15].YPD_rate_calc
14 0
29 0
44 0
89 0
J47 2	#unreact_cont[15]
89 -1
152 1
J48 3	#react_cont[1]
75 -1
76 1
138 1
J49 3	#react_cont[2]
76 -1
77 1
139 1
J50 3	#react_cont[3]
77 -1
78 1
140 1
J51 3	#react_cont[4]
78 -1
79 1
141 1
J52 3	#react_cont[5]
79 -1
80 1
142 1
J53 3	#react_cont[6]
80 -1
81 1
143 1
J54 3	#react_cont[7]
81 -1
82 1
144 1
J55 3	#react_cont[8]
82 -1
83 1
145 1
J56 3	#react_cont[9]
83 -1
84 1
146 1
J57 3	#react_cont[10]
84 -1
85 1
147 1
J58 3	#react_cont[11]
85 -1
86 1
148 1
J59 3	#react_cont[12]
86 -1
87 1
149 1
J60 3	#react_cont[13]
87 -1
88 1
150 1
J61 3	#react_cont[14]
88 -1
89 1
151 1
J62 3	#split_mole[A]
0 1
90 -1
153 -1
J63 3	#split_mole[B]
15 1
91 -1
154 -1
J64 3	#split_cont
75 1
92 -1
155 -1
J65 2	#prod_spec
91 -1
92 0.95
J66 2	#vol_cons[2]
60 -1
61 1
J67 2	#vol_cons[3]
61 -1
62 1
J68 2	#vol_cons[4]
62 -1
63 1
J69 2	#vol_cons[5]
63 -1
64 1
J70 2	#vol_cons[6]
64 -1
65 1
J71 2	#vol_cons[7]
65 -1
66 1
J72 2	#vol_cons[8]
66 -1
67 1
J73 2	#vol_cons[9]
67 -1
68 1
J74 2	#vol_cons[10]
68 -1
69 1
J75 2	#vol_cons[11]
69 -1
70 1
J76 2	#vol_cons[12]
70 -1
71 1
J77 2	#vol_cons[13]
71 -1
72 1
J78 2	#vol_cons[14]
72 -1
73 1
J79 2	#vol_cons[15]
73 -1
74 1
J80 2	#YR_is_recycle[15].YRD_FR_act[A]
122 1
153 -1
J81 2	#YR_is_recycle[15].YRD_FR_act[B]
137 1
154 -1
J82 2	#YR_is_recycle[15].YRD_QFR_act
152 1
155 -1
J83 1	#YR_is_not_recycle[1].neg_YRD_FR_desact[A]
108 1
J84 1	#YR_is_not_recycle[1].neg_YRD_FR_desact[B]
123 1
J85 1	#YR_is_not_recycle[1].neg_YRD_QFR_desact
138 1
J86 1	#YR_is_not_recycle[2].neg_YRD_FR_desact[A]
109 1
J87 1	#YR_is_not_recycle[2].neg_YRD_FR_desact[B]
124 1
J88 1	#YR_is_not_recycle[2].neg_YRD_QFR_desact
139 1
J89 1	#YR_is_not_recycle[3].neg_YRD_FR_desact[A]
110 1
J90 1	#YR_is_not_recycle[3].neg_YRD_FR_desact[B]
125 1
J91 1	#YR_is_not_recycle[3].neg_YRD_QFR_desact
140 1
J92 1	#YR_is_not_recycle[4].neg_YRD_FR_desact[A]
111 1
J93 1	#YR_is_not_recycle[4].neg_YRD_FR_desact[B]
126 1
J94 1	#YR_is_not_recycle[4].neg_YRD_QFR_desact
141 1
J95 1	#YR_is_not_recycle[5].neg_YRD_FR_desact[A]
112 1
J96 1	#YR_is_not_recycle[5].neg_YRD_FR_desact[B]
127 1
J97 1	#YR_is_not_recycle[5].neg_YRD_QFR_desact
142 1
J98 1	#YR_is_not_recycle[6].neg_YRD_FR_desact[A]
113 1
J99 1	#YR_is_not_recycle[6].neg_YRD_FR_desact[B]
128 1
J100 1	#YR_is_not_recycle[6].neg_YRD_QFR_desact
143 1
J101 1	#YR_is_not_recycle[7].neg_YRD_FR_desact[A]
114 1
J102 1	#YR_is_not_recycle[7].neg_YRD_FR_desact[B]
129 1
J103 1	#YR_is_not_recycle[7].neg_YRD_QFR_desact
144 1
J104 1	#YR_is_not_recycle[8].neg_YRD_FR_desact[A]
115 1
J105 1	#YR_is_not_recycle[8].neg_YRD_FR_desact[B]
130 1
J106 1	#YR_is_not_recycle[8].neg_YRD_QFR_desact
145 1
J107 1	#YR_is_not_recycle[9].neg_YRD_FR_desact[A]
116 1
J108 1	#YR_is_not_recycle[9].neg_YRD_FR_desact[B]
131 1
J109 1	#YR_is_not_recycle[9].neg_YRD_QFR_desact
146 1
J110 1	#YR_is_not_recycle[10].neg_YRD_FR_desact[A]
117 1
J111 1	#YR_is_not_recycle[10].neg_YRD_FR_desact[B]
132 1
J112 1	#YR_is_not_recycle[10].neg_YRD_QFR_desact
147 1
J113 1	#YR_is_not_recycle[11].neg_YRD_FR_desact[A]
118 1
J114 1	#YR_is_not_recycle[11].neg_YRD_FR_desact[B]
133 1
J115 1	#YR_is_not_recycle[11].neg_YRD_QFR_desact
148 1
J116 1	#YR_is_not_recycle[12].neg_YRD_FR_desact[A]
119 1
J117 1	#YR_is_not_recycle[12].neg_YRD_FR_desact[B]
134 1
J118 1	#YR_is_not_recycle[12].neg_YRD_QFR_desact
149 1
J119 1	#YR_is_not_recycle[13].neg_YRD_FR_desact[A]
120 1
J120 1	#YR_is_not_recycle[13].neg_YRD_FR_desact[B]
135 1
J121 1	#YR_is_not_recycle[13].neg_YRD_QFR_desact
150 1
J122 1	#YR_is_not_recycle[14].neg_YRD_FR_desact[A]
121 1
J123 1	#YR_is_not_recycle[14].neg_YRD_FR_desact[B]
136 1
J124 1	#YR_is_not_recycle[14].neg_YRD_QFR_desact
151 1
J125 2	#YP_is_cstr[1].YPD_rate_rel
30 1
45 1
J126 2	#YP_is_cstr[1].YPD_vol_act
60 -1
93 1
J127 2	#YP_is_cstr[2].YPD_rate_rel
31 1
46 1
J128 2	#YP_is_cstr[2].YPD_vol_act
61 -1
94 1
J129 2	#YP_is_cstr[3].YPD_rate_rel
32 1
47 1
J130 2	#YP_is_cstr[3].YPD_vol_act
62 -1
95 1
J131 2	#YP_is_cstr[4].YPD_rate_rel
33 1
48 1
J132 2	#YP_is_cstr[4].YPD_vol_act
63 -1
96 1
J133 2	#YP_is_cstr[5].YPD_rate_rel
34 1
49 1
J134 2	#YP_is_cstr[5].YPD_vol_act
64 -1
97 1
J135 2	#YP_is_cstr[6].YPD_rate_rel
35 1
50 1
J136 2	#YP_is_cstr[6].YPD_vol_act
65 -1
98 1
J137 2	#YP_is_cstr[7].YPD_rate_rel
36 1
51 1
J138 2	#YP_is_cstr[7].YPD_vol_act
66 -1
99 1
J139 2	#YP_is_cstr[8].YPD_rate_rel
37 1
52 1
J140 2	#YP_is_cstr[8].YPD_vol_act
67 -1
100 1
J141 2	#YP_is_cstr[9].YPD_rate_rel
38 1
53 1
J142 2	#YP_is_cstr[9].YPD_vol_act
68 -1
101 1
J143 2	#YP_is_cstr[10].YPD_rate_rel
39 1
54 1
J144 2	#YP_is_cstr[10].YPD_vol_act
69 -1
102 1
J145 2	#YP_is_cstr[11].YPD_rate_rel
40 1
55 1
J146 2	#YP_is_cstr[11].YPD_vol_act
70 -1
103 1
J147 2	#YP_is_cstr[12].YPD_rate_rel
41 1
56 1
J148 2	#YP_is_cstr[12].YPD_vol_act
71 -1
104 1
J149 2	#YP_is_cstr[13].YPD_rate_rel
42 1
57 1
J150 2	#YP_is_cstr[13].YPD_vol_act
72 -1
105 1
J151 2	#YP_is_cstr[14].YPD_rate_rel
43 1
58 1
J152 2	#YP_is_cstr[14].YPD_vol_act
73 -1
106 1
J153 2	#YP_is_cstr[15].YPD_rate_rel
44 1
59 1
J154 2	#YP_is_cstr[15].YPD_vol_act
74 -1
107 1
G0 15	#obj
93 1
94 1
95 1
96 1
97 1
98 1
99 1
100 1
101 1
102 1
103 1
104 1
105 1
106 1
107 1
