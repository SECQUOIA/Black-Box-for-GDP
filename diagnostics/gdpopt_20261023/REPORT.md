# GDPopt 종료 불일치 진단

원자료는 보존했고, 이 디렉터리에만 진단 코드와 복사본 및 새 결과를 저장했다.
커밋·push·PR·CI·원고 변경은 하지 않았다.
추가 최적화 solver 호출은 0회다.

## 1. 확인된 사실

로컬 `main`은 `d05b392d4a93e4233a2ee69617da2767395fd27b`다.
GitHub에서 조회한 최신 `main`은 `2d1e2e49158d924f1fe589a55f7d7f210bf5f28b`다.
로컬 `origin`은 AlbertLee125/RBFopt_Test이고 `upstream`은 이름 변경 전 SECQUOIA/RBFopt_Test URL이다.
브랜치를 바꾸거나 원격 설정을 수정하지 않았다.
수정 중이던 `gdp_models/comparison.py`, `gdp_models/grid_benchmark.py`, `grid_gdp_benchmark.py` 및 미추적 자료를 보존했다.
초기 상태는 `initial_git_status.txt`와 `initial_git_context.txt`에 기록했다.
현재 수정본 `comparison.py`를 과거 실행 재현에 사용하지 않았다.

Grid archive의 SHA256은 `fb5d962307731a84d5833b1065cd5e94772bdb15c8a4a7f5d05b3ff0b67a7c94`다.
CSTR A12 archive의 SHA256은 `7fbb60f75bd46ecefd8788540be2e070656df37d6b80f075aea9e09c5ad33d4e`다.
W03 추가 검증 archive의 SHA256은 `7c254d626bfa1fb087151ca20acd238b70b5946a51b6b197b11a4b056c147837`다.
모든 실행 소스 파일은 각 archive의 `run.json`에 있는 SHA256과 일치한다.
두 원실행 archive에는 실행 저장소의 단일 Git HEAD가 기록돼 있지 않으므로 이를 추측하지 않았다.
실행 소스의 식별 기준은 archive와 파일별 해시다.
Grid 수식 출처 revision은 `11ba8728a107d6d16ed63e72d334a66662f9ebc1`이다.
CSTR 모델 출처 revision은 dsda-gdp의 `3e469dbeea8931670b8cd6752014ab7a767d3af5`이다.

CSTR 검증 자료는 `/private/tmp/cstr15-dantzig-results`의 `8c7515d602802ab7b5b23eef4373988036a7f7ce`에서 읽었다.
검증 디렉터리의 8개 파일은 최신 원격 main의 Git blob SHA와 모두 일치한다.
이는 해당 작업 디렉터리 전체가 원격 main과 같다는 뜻은 아니다.
검증 서버 실행 revision은 `70bf17ca95e5ee1b98069e494c22fcafd6398960`이다.

| 항목 | Grid Michalewicz | CSTR15 GLOA A12 |
|---|---|---|
| Pyomo / GDPopt | 6.10.0 / 22.5.13 | 6.10.0 / 22.5.13 |
| 원래 실행 | Python 3.11.16, Linux Dantzig, GAMS 52.2.0 | Python 3.11.16, Linux Dantzig, GAMS 52.2.0 |
| 구성된 solver | MIP HiGHS, NLP BARON | MIP HiGHS, NLP BARON |
| 실제 호출 | 방법마다 HiGHS 1.12.0 1,420회, BARON 0회 | HiGHS 1.12.0 2회, BARON 25.11.17 2회 |
| BARON 옵션 | 구성만 존재: `LPSol 8`, `NLPSol 9` | 실제 사용: `LPSol 8`, `NLPSol 9` |
| BARON 내부 solver | 호출되지 않음 | CLP/CBC 및 IPOPT, 내부 IPOPT 버전은 원로그에 기록 없음 |
| 전처리 | `subproblem_presolve=True`, `mip_presolve=True` | 동일 |
| 주요 허용오차 | constraint `1e-6`, variable `1e-8`, bound `1e-5` | 동일 |

Grid 전수평가의 GAMS/IPOPT 경로는 GDPopt의 실제 HiGHS 호출 경로와 별개다.
CSTR 추가 검증의 IPOPT 3.14.19/MUMPS 5.8.1 설정을 원래 BARON 내부 IPOPT 설정으로 간주하지 않았다.
원래 제한은 1,800초이며 두 사례 모두 시간 제한으로 종료하지 않았다.

### Grid 원자료

격자는 31×31이고 CSV와 원래 목적함수의 전수 검사는 961점을 포함한다.
유일한 최소점은 외부 좌표 `(21,15)`이고 물리 좌표는 `(2.199114857512855,1.5707963267948966)`이다.
정규화 전 목적값은 `-1.8010702893119994`이고 정규화 후 목적값은 0이다.
archive의 별도 전수평가 기록에서도 flat index 666의 목적값은 0이다.
이 기록은 GDPopt가 그 점을 평가했다는 증거가 아니다.

| 방법 | 반환점 | 목적값 | 종료 | 반복 | 이산문제 행 | 실행 가능 콜백 / 서로 다른 점 |
|---|---|---|---|---|---|---|
| RIC | (22,15) | 0.08649170482029742 | optimal | 962 | 961 | 458 / 458 |
| GLOA | (22,15) | 0.08649170482029742 | optimal | 962 | 961 | 458 / 458 |
| LOA | (22,15) | 0.08649170482029742 | optimal | 962 | 961 | 458 / 458 |

각 방법에는 구성 식별 정보가 없는 이산문제 반복이 503개 있다.
962번째 반복은 최종 이산문제 infeasible 판정이다.
961회의 이산문제 행을 961개 정상 하위문제 평가로 해석할 수 없다.
GLOA의 `(22,15)`는 반복 358, wrapper 호출 605, 로그 56953행에서 incumbent를 개선했다.
`(21,15)`의 선택 반복, 실제 하위문제 상태, 해당 no-good cut과 그 직전 incumbent는 원기록에 없다.
이 정보는 사건 표에 `기록 없음`으로 표시했다.
GLOA 로그 138346행은 남은 이산 구성이 탐색되거나 제외되어 MILP가 infeasible이라고 보고한다.
그다음 보고 하한과 상한을 같은 값으로 맞추고 `optimal`로 종료한다.

### CSTR15 원자료

A12의 최종 보고 하한과 목적값은 `3.522552007803194`다.
기존 Dantzig 검증 목적값은 `2.8293940632857595`다.
최대 원래 GDP 위반은 `1.1102230246251565e-16`이고 검증 기준은 `1e-8`이다.
완료된 실행 가능성 검사를 새 solver로 반복하지 않았다.
W03은 feed 15, recycle 15, reactor 1–15 구성이다.
A12 초기 incumbent는 feed 15, recycle 11, reactor 1–15 구성이다.

| 단계 | 구성 | solver / 결과 | GDPopt 하한 | GDPopt 상한 | incumbent |
|---|---|---|---|---|---|
| 초기화 0 | feed15, recycle11, 15 reactors | HiGHS set covering; BARON optimal, 3.522552007803192 | -inf | 3.522552007803194 | 갱신 |
| 반복 1 이산문제 | feed1, recycle1, 1 reactor | HiGHS optimal | 0.006266666666667 | 3.522552007803194 | 유지 |
| 반복 1 하위문제 | 같은 구성 | BARON locallyOptimal, LB 9.894637896687904, UB 9.89473684210525 | 0.006266666666667 | 3.522552007803194 | 유지 |
| 반복 2 종료 | 기록 없음 | 추가 wrapper 호출 없음 | 3.522552007803194 | 3.522552007803194 | 유지 |

처음 W03보다 큰 **GDPopt 전역 보고 하한**이 나타나는 위치는 `run.log` 983행의 반복 2 종료 행이다.
초기 BARON의 3.522552…는 고정 구성의 하한이므로 이보다 앞선 전역 하한으로 세지 않았다.
마지막 출력은 bounds converged/crossed이며, 마지막 HiGHS solve가 높은 전역 하한을 반환한 것이 아니다.
소스상 추가 호출 없이 이 경로에 들어가는 설명은 MIP FBBT infeasible → 내부 dual=+inf → dual을 incumbent로 재설정하는 경로다.
당시 DEBUG 전처리 예외와 두 번째 하위문제의 전체 연속 벡터는 저장되지 않았다.
따라서 마지막 모순을 일으킨 정확한 제약과 경계는 원실행에서 미확정이다.

## 2. 원인과 증거 수준

### Grid: solver-free로 확인한 잘못된 전처리 판정

원래 모델의 좌표 인덱스, XOR 선택, 수식, 정규화는 CSV와 일치한다.
비선형 목적함수는 `z >= f(x,y)`와 `min z`로 이동한다.
이 epigraph 변환 자체는 최적값을 보존한다.
MC++가 만든 z 경계 `[-0.11045083130208694,0.9999999999999999]`는 최적점의 z=0을 포함한다.

archive 소스로 만든 `(21,15)` 하위문제에 Pyomo 6.10.0 전처리를 적용하면 solver를 부르기 전에 infeasible이 반환된다.
FBBT의 `sin(x)` 역전파 입력은 `[0.8090169943749475,0.8090169943749473]`이다.
하한이 상한보다 약 `2.22e-16` 크다.
`interval.asin`은 이 작은 역전을 기존 `1e-6` 허용오차 안의 수치 문제로 흡수하지 못하고 다른 sine 가지의 상한 `0.9424777960769378`을 반환한다.
그 결과 고정 좌표 `x=2.199114857512855`와 모순되어 `InfeasibleConstraintException`이 발생한다.
원인 제약은 변환된 `_gdpopt_cuts.objective_constr`이고, 실패 단계는 FBBT다.
`detect_fixed_vars`와 상수 제약 제거에 도달하기 전 실패한다.

공통 `solve_subproblem`은 이 예외를 infeasible로 바꾸고 solver 및 feasible 콜백을 생략한다.
RIC·GLOA·LOA의 이후 no-good 경로는 이 구성을 제외할 수 있다.
wrapper의 `strict_subproblems` 검사는 실제 solver 호출에만 적용되어 이 경로를 검사하지 못한다.
실제 no-good cut이 `(21,15)`를 배제하고 인접 `(22,15)`는 허용하는 것을 회귀 검사했다.

이는 로컬에서 확인된 구체적인 잘못된 판정이며 원실행 결과와 강하게 부합한다.
그러나 원실행에서 `(21,15)`가 선택된 순간까지 직접 연결한 추적은 확보하지 못했다.
원래 Linux 바이너리와 다른 로컬 환경의 961개 전처리 검사에서는 453개가 통과하고 508개가 탈락했다.
과거 458개 콜백 집합과 7개 점에서 달라 완전한 실행 재현으로 주장하지 않는다.
구체적으로 로컬만 통과한 점은 `(16,14)`이고 과거만 통과한 점은 `(16,5),(16,11),(16,13),(16,18),(16,24),(16,27)`이다.
후보 패치에서는 961개 모두 전처리를 통과했다.
이는 전처리 검사 결과이며 961개 solver 최적화 결과가 아니다.

### CSTR15: 유효한 비교해를 배제하는 GLOA cut

Pyomo 6.10.0 GLOA는 `cvSlope`를 계산하지만 convex cut에 `ccSlope`로 만든 `cut_body`를 사용한다.
이 동작은 보관한 분석 소스와 [공식 6.10.0 소스](https://pyomo.readthedocs.io/en/6.10.0/_modules/pyomo/contrib/gdpopt/gloa.html)에서 확인했다.
원래 모델, 초기 전역 FBBT, 논리 변환, 초기 master FBBT, 저장된 A12 incumbent를 사용해 최초 cut 집합을 재구성했다.
W03은 초기 master 변수 경계를 모두 만족한다.
초기 no-good cut에서도 W03의 좌변은 4이고 요구 하한은 1이므로 이 cut은 W03을 제외하지 않는다.
반면 `YP_is_cstr[1..15].GDPopt_aff.GDPopt_aff_cons[1]`의 15개 convex cut이 W03을 배제한다.
이 disjunct들은 모두 W03에서 활성화되므로 비활성 disjunct의 cut을 전역 cut으로 잘못 검사한 결과가 아니다.
Big-M 변환 후 실제 활성 제약에서도 같은 위반을 확인했다.
최대 위반은 reactor 12 cut의 `36.01008109919173`이다.
convex cut 기울기만 `cvSlope`로 바꾸면 동일 W03 벡터의 변환 master 위반이 모두 사라진다.
목적함수, 논리, 원래 경계, 감사 허용오차는 바꾸지 않았다.

이로써 사용된 버전의 cut 생성 결함과 비교해 배제의 직접적인 연결은 확인됐다.
최종 반복 2에서 어떤 제약이 FBBT 모순을 일으켰는지까지 재현하지는 못했다.
첫 cut 집합만으로는 master FBBT가 infeasible이 되지 않았다.
원래 두 번째 하위문제의 벡터와 이후 생성 cut을 확보해야 마지막 종료 경로를 완전히 닫을 수 있다.
로컬 MC++는 같은 source revision이지만 Linux 바이너리 해시와 다르므로 원래 환경 재확인이 필요하다.

## 3. 같은 원인인가

| 추적 경로 | Grid | CSTR15 |
|---|---|---|
| 원래 GDP와 참조 | 수식·정규화·961 좌표 audit 일치 | 같은 pinned 모델과 저장 W03 벡터, 원래 목적함수는 `sum(c[n])` |
| 외부 좌표·disjunct | 0–30 인덱스가 Xchoice/Ychoice와 일치 | Boolean feed/recycle 및 reactor 선택을 이름으로 복원 |
| 목적함수 이동 | epigraph와 z 경계가 최적점을 포함 | 선형 목적함수여서 비선형 목적함수 이동 없음 |
| 고정·상수·FBBT | FBBT가 detect-fixed/상수 제거 이전에 실패 | 초기 global/master 경계는 W03을 포함하며 마지막 모순 제약은 기록 없음 |
| wrapper 상태 | 실제 호출은 모두 HiGHS, presolve 실패는 wrapper 우회 | raw GAMS 상태와 gap 검사 후 GDPopt에 전달 |
| incumbent 이전 제외 | 로컬 실패에서 feasible 콜백 생략을 확인 | 초기 incumbent 갱신 후 잘못된 cut이 다른 feasible 구성 W03을 배제 |
| cut 조건 | 공통 no-good 경로는 presolve infeasible도 제외 | GLOA는 feasible 하위문제 뒤 affine cut 및 no-good을 추가 |
| 하한·종료 | 마지막 master infeasible 후 incumbent로 bound 정렬 | 반복 2의 solver 없는 master infeasible 경로와 bound 정렬이 소스상 설명 |

현재 증거는 두 가지 서로 다른 구체적 결함을 가리킨다.
Grid의 문제는 sine 경계 전파이고 CSTR의 원래 수식에는 그 경로가 없다.
CSTR의 문제는 GLOA affine cut 기울기이며 Grid의 RIC도 같은 반환 실패를 보인다.
공통점은 잘못 제외된 feasible 영역을 복구하지 않고 이산문제 infeasible을 `optimal` 종료로 연결하는 데이터 흐름이다.
그 공통점만으로 동일 원인이라고 결론 내릴 수 없다.
LOA의 비볼록 모델에 대한 일반적인 전역 하한 보장 한계는 이번 Grid 실패의 구체적인 설명과 별개다.
그 한계를 RIC·GLOA에 그대로 적용하지 않는다.

## 4. 최소 수정

`fbbt_fbbt.patch`는 이미 singleton인 sine 인수에서 기존 허용오차 안의 경계 역전 때문에 다른 가지로 이동하지 않도록 한다.
`gdpopt_gloa.patch`는 convex affine cut에 `cvSlope`를 사용한다.
두 패치는 별도 파일이며 설치된 Pyomo와 기존 저장소 코드를 수정하지 않았다.
`patches.py`는 진단 프로세스 안에서만 후보 패치를 적용한다.
다섯 회귀 검사는 잘못된 infeasible 전달, solver 진입 여부, 실제 no-good 제외, 진짜 infeasible sine 유지, 저장 W03의 cut 위반을 확인하며 모두 통과했다.
이 최소 패치가 Pyomo 전체 문제군에 충분하다는 주장은 하지 않는다.
wrapper의 solver 상태 변환이 이번 두 오류를 만든 증거는 없다.
CSTR 마지막 BARON의 locallyOptimal은 raw gap이 기존 기준을 만족해 허용됐고, 그 하위문제 목적값은 incumbent보다 나빴다.

## 5. 필요한 재실행 범위와 보존 범위

원래 환경에서 우선 Grid GLOA 한 번만 진단 기록을 추가해 실행한다.
이를 통해 `(21,15)`의 반복 번호, presolve 예외, solver 호출 생략, incumbent 유지, no-good 추가를 한 줄기로 연결한다.
CSTR은 먼저 같은 Dantzig MC++ 바이너리로 solver-free cut 재구성을 확인한다.
두 번째 GDPopt 실행은 기존 A12를 대조군으로 두고 convex 기울기 하나만 바꾼 CSTR GLOA 진단에 사용할 수 있다.
원래 환경에서 첫 실행이 다른 현상을 보이면 두 번째 실행 계획을 그 증거에 맞춰 재검토한다.
`dantzig_trace.py`는 두 회의 영속 allocation과 각 1,800초의 프로세스 그룹 제한을 적용한다.
추가 고정 구성 최적화는 현재 필요하지 않으며 실행하지 않았다.

원래 archive, CSV, manifest, verification, 시간 기록은 역사적 관측값으로 유지한다.
기존 Grid 참조 전수평가와 CSTR W03의 완료된 실행 가능성 검증도 유지한다.
문제가 있는 `optimal` 종료를 전역 최적성 인증으로 사용할 수는 없다.
RBFOpt·D-SDA·BAM·FMQA-SA·uniform 결과를 변경하거나 재실행할 근거는 이번 조사에서 만들지 않았다.
전체 benchmark를 재실행하지 않는다.

## 6. 현재 가능한 원고 주장

GDPopt가 `optimal`로 종료했으나 원래 GDP의 더 좋은 실행 가능 해와 불일치한다고 기술할 수 있다.
Grid의 수치 전처리 실패와 CSTR의 잘못된 cut 기울기를 solver-free 진단에서 확인했다고 기술할 수 있다.
원래 환경의 전체 인과 추적은 아직 완료되지 않았다고 함께 명시해야 한다.
이번 근거로 BARON의 오류, 시간 부족, 모든 GDPopt 알고리즘의 일반적 실패, 다른 방법의 우월성을 주장하면 안 된다.
패치 후 최적값과 시간, 전역 인증 회복도 아직 주장하면 안 된다.

## 7. 실제 추가 실행

GDPopt 전체 실행은 0/2회이고 소요 시간은 0초다.
독립 고정 구성 하위문제 최적화는 0/4회이고 소요 시간은 0초다.
GDPopt 내부 추가 solver 호출도 0회다.
모델 평가·FBBT·cut 재구성·회귀 검사는 solver 없는 계산이며 별도 로그에 시간을 기록했다.
로컬에는 원래 `/package/gams/52.2/gams`와 Linux MC++ 바이너리가 없어 임의 solver 대체를 하지 않았다.
실행 방법과 미실행 Dantzig 명령은 `README.md`에 있다.
