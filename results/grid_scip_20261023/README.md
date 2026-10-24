# 2026-10-23 Dantzig Grid-GDP SCIP 반환 결과와 GDPopt 진단 검토

**105개 작업 모두 `solution.json`에 변수 벡터를 반환했고, 독립 재검사에서
기존 원래 GDP 허용오차 `1e-5`를 통과했다.** MINLP Big-M과 Hull은 각각 21/21개
함수에서 참조 목표값에 도달했다. GDPopt GLOA·LOA·RIC는 각각 18/21개다.
따라서 해를 반환하지 못한 문제가 아니라, 일부 GDPopt 반환해의 품질과
`optimal` 종료의 해석이 문제다. 전체 목표 도달은 96/105개다.

원래 실행/원고 결과는 변경하지 않았다. 이 검토에서 optimizer 호출은 0회다.
네 반환 ZIP과 진단 ZIP의 원본 바이트를 보존했다. 세 GDPopt ZIP은
`results/archives`에서, MINLP ZIP과 제공된 checksum은 사용자가 지정한
Downloads에서 가져왔다. PR 49의 마지막 head `ef93072d1ac28dbcf22ecc8b448f3e6869fbbdaf`
위에 독립 분석과 근거를 추가했다. PR 49 자체는 이미 병합된 상태다.

## 1. 방법별 결과

모든 작업은 Dantzig GAMS 52.2.0, Pyomo 6.10.0, 방법별 1,800초 제한과
1 thread를 사용했다. Grid 수식과 21개 CSV는 실행 소스와 현재 감사 모델이
바이트 단위로 동일하다. 목표 도달 기준은 정규화 목적값과 참조 최솟값의 차이
`<= 1e-5`다. 전체 데이터는 [summary.csv](summary.csv),
[작업별 결과](jobs.csv), [원자료 검증](audit.json)에 있다.

| 방법 | 반환·유효한 해 | 목표 도달 | `optimal` 종료 | 시간 제한 종료 | `optimal`인데 목표 미달 | 방법 시간 합계 (초) |
|---|---:|---:|---:|---:|---:|---:|
| SCIP Big-M | 21/21 | 21/21 | 21 | 0 | 0 | 24.469 |
| SCIP Hull | 21/21 | 21/21 | 21 | 0 | 0 | 16.386 |
| GDPopt GLOA | 21/21 | 18/21 | 18 | 3 | 2 | 19,116.235 |
| GDPopt LOA | 21/21 | 18/21 | 17 | 4 | 2 | 18,471.434 |
| GDPopt RIC | 21/21 | 18/21 | 17 | 4 | 2 | 19,057.874 |

시간은 각 `result.json`의 `method_wall_s` 합계다. 모델/CSV 전처리와 사전검사는
포함하지 않으며, 42개 MINLP 작업 합계는 40.855초다. 중앙값은 Big-M 0.655초,
Hull 0.533초다. 이는 이 유한 Grid 수식/표현에서의 관측이며, 일반 MINLP나
Process 사례의 성능 우위를 뜻하지 않는다. GDPopt의 `status=finished`는
시간 제한 종료를 포함하므로 `termination`을 별도로 집계했다.

Big-M/Hull 42개는 원기록의 global certificate가 true이고 참조 목표값으로도
확인됐다. GDPopt 63개는 모두 global certificate가 false다. GDPopt의
`optimal` 문자열만을 전역 최적성 인증으로 사용하지 않는다.

## 2. 실제 어떤 solver가 실행됐는가

구성은 요청대로 GDPopt의 BARON NLP를 SCIP NLP로 교체하고 HiGHS MILP를
유지했다. 하지만 **63개 GDPopt 작업의 실제 benchmark 호출 61,063회는 전부
HiGHS MIP**였다. SCIP NLP와 BARON 호출은 각각 0회다.

| 실행 구분 | 실제 benchmark 호출 |
|---|---:|
| Big-M/Hull | SCIP MINLP 42회 |
| GLOA | HiGHS MIP 20,778회 |
| LOA | HiGHS MIP 19,299회 |
| RIC | HiGHS MIP 20,986회 |

두 좌표를 고정한 뒤 GDPopt 전처리가 subproblem을 선형으로 만들면 기존
`solve_subproblem` 경로가 HiGHS를 사용한다. GDPopt ZIP마다 사전검사에서
SCIP NLP 2회가 호출됐지만 이는 benchmark 호출과 분리했다. 따라서 이 자료는
SCIP 직접 reformulation 성능을 보여주지만, GDPopt NLP의 BARON 대비 SCIP
속도 향상을 측정한 자료가 아니다. 기존 진단의 Michalewicz 원실행에서도
BARON이 실제로 호출되지 않았다는 사실과 일치한다.

## 3. 해 벡터와 목표 미달을 독립적으로 확인한 결과

`solution.json`을 읽어 원래 변수 64개(Csendes는 66개)를 모두 복원했다.
누락된 변수에 생성자의 초기값을 대신 쓰지 않는다. 변수 경계, binary 정수성,
두 XOR, 선택된 disjunct의 등식 및 Csendes reciprocal, 원래 해석적 목적값을
검사했다. 이어 선택 좌표와 CSV 최솟값을 대조했다. 모든 함수의 961개 해석적
격자값을 CSV와 검증하는 기존 model audit도 사용했다.

최대 원래 GDP 위반은 `1.9808652753638967e-6`, 저장 목적값과 재계산한 목적값의
최대 차이는 `3.1170855730844047e-17`이다. 기존 기준 `1e-5`에서는 105개 모두
유효하다. 더 엄격한 `1e-8`에서 통과하는 것은 102/105개이며 나머지는 다음과 같다.
이 기록의 변수를 반올림하거나 덮어쓰지 않았다.

| 함수/방법 | 최대 원래 GDP 위반 |
|---|---:|
| deflected_corrugated_spring / Hull | 1.9808652753638967e-6 |
| michalewicz / Hull | 5.02655339573721e-8 |
| sum_of_squares / Big-M | 3.4970414e-8 |

세 GDPopt 방법이 놓친 함수와 반환점은 동일하다. 아래의 참조 최솟값은 모두 0이다.
좌표는 CSV의 0–30 인덱스이며 물리 좌표와 구분한다.

| 함수 | 세 방법의 반환점 | 반환 정규화 목적값 | 참조 최소점 | 종료 |
|---|---|---:|---|---|
| Holder Table | (0,1) | 0.14516723995340786 | (3,1), (27,1) | 세 방법 모두 시간 제한 |
| Michalewicz | (22,15) | 0.08649170482029742 | (21,15) | 세 방법 모두 `optimal` |
| Shubert | (17,21) | 0.08242781075119937 | (17,22) | 세 방법 모두 `optimal` |

SCIP Big-M/Hull은 이 함수들의 참조 최소점도 반환했다. 이로써 Michalewicz와
Shubert의 GDPopt 반환점보다 좋은 해가 같은 모델에서 실제 반환됐음을 직접
대조할 수 있다. 원자료에는 두 방법의 전체 변수 벡터와 raw GAMS 상태가 있다.

시간 제한 11개 중 8개는 이미 목표값에 도달했다. GLOA의 Levy·Levy13,
LOA의 Hosaki·Levy13·Styblinski–Tang, RIC의 Levy·Levy13·Styblinski–Tang이
해당한다. 나머지 3개는 Holder Table이다. 시간 제한은 해 부재와 같지 않다.

## 4. 좌표 기록과 전처리 진단

각 GDPopt 작업의 `grid_path.jsonl`에는 전처리를 통과한 하위문제의 before/after
좌표가 저장돼 있다. Michalewicz는 각 방법에서 서로 다른 458점, Shubert는
74점만 이 콜백에 도달했다. 세 방법 모두 해당 참조 최소점은 콜백에 없다.
두 함수의 `gdpopt_iterations`는 962다. 이 수를 961개의 정상 목적함수 평가로
해석하면 안 된다. GLOA와 RIC의 콜백 좌표 순서는 두 함수에서 각각 일치하지만
LOA 순서는 달라, 경로 전체가 세 방법에서 같다고 주장하지 않는다.

콜백이 전처리 뒤에 있으므로, 기록 부재만으로 그 구성이 master에서 선택되지
않았다고 말할 수는 없다. 전체 Dantzig candidate → presolve → no-good 연결
추적은 이 ZIP에 없다. 과거 진단의 같은 기록 한계도 여전히 남는다.

추가 optimizer 없이, 실행 모델과 동일한 Grid 수식과 Pyomo 6.10.0의 공통
GDPopt 전처리를 로컬에서 재현했다. [presolve_probe.json](presolve_probe.json)에
소스 해시, 역삼각함수 전파 입력/출력, 예외와 결과가 있다.

| 함수/점 | 로컬 전처리 결과 |
|---|---|
| Michalewicz (21,15), 참조 최소점 | FBBT infeasible; x 하한 2.199114857512855 > 상한 0.9424777960769378 |
| Michalewicz (22,15), 반환점 | 통과 |
| Shubert (17,22), 참조 최소점 | FBBT `InfeasibleConstraintException` |
| Shubert (17,21), 반환점 | 통과 |
| Holder Table (3,1), (27,1), 참조 최소점 | FBBT infeasible; y 하한 -3.233037281025837 > 상한 -9.333333333333336 |
| Holder Table (0,1), 반환점 | 통과 |

원래 모델에서 가능한 최소점이 solver 호출 전 탈락한다는 현상이 새 반환
자료의 실패와 부합한다. 따라서 Holder Table의 미달을 단순히 시간 부족만으로
설명하기도 어렵다. 다만 로컬 재현은 원래 서버의 각 후보 선택 순간을 직접
관측한 것과 다르다. Shubert·Holder Table에 기존 singleton-sine 후보 패치가
충분한지, 수정 후 시간/최적성 결과가 어떤지는 이번 검토에서 검증하지 않았다.

## 5. 제공된 GDPopt 진단 패키지와의 관계

[원래 진단 보고서](../../diagnostics/gdpopt_20261023/REPORT.md)와
[보존 패키지 안내](../../diagnostics/gdpopt_20261023/INDEX.md)를 함께 읽어야 한다.
`dantzig_package.zip`은 완료된 새 서버 실행 결과가 아니다. 원기록 분석,
solver-free probe, 후보 패치와 앞으로 실행할 수 있는 진단 runner를 묶은
패키지다. `execution_accounting.json`에는 GDPopt 추가 실행 0회,
독립 고정 구성 최적화 0회, 내부 추가 solver 호출 0회가 기록돼 있다.
**따라서 후보 패치 적용 후 Dantzig에서 해를 반환하거나 최적성을 회복했다는
주장은 아직 할 수 없다.**

Grid Michalewicz에서는 singleton sine 인수에 대한 FBBT 역전파가 약 `2.22e-16`의
경계 역전 때문에 다른 sine 가지로 이동하는 문제를 기존 진단이 추적했다.
새 SCIP 설정 실행도 같은 (22,15), 목적값 0.08649170482029742를 반환하고
458점 콜백을 남겨 그 진단과 부합한다. 기존 `pyomo610-grid-v1` 보정은
고정 exponent와 Alpine1/LOA에 관한 것으로 이 singleton-sine 후보 패치와 다르다.

CSTR15 GLOA A12의 3.522552007803194는 이미 검증된 W03의
2.8293940632857595보다 크다. 진단은 초기 GLOA convex cut이 `cvSlope` 대신
`ccSlope`를 사용하면서 W03의 활성 reactor disjunct에서 15개 cut 위반을 만든다는
점을 확인했다. 최대 위반은 36.01008109919173이다. 기울기만 고친 로컬
cut 재구성에서는 해당 변환 master 위반이 사라졌다. 원래 마지막 master FBBT
모순의 정확한 제약까지 완전히 복원한 것은 아니다.

이번 검토에서도 보존 패키지를 임시 디렉터리에 풀어 원래 5개 solver-free
회귀 검사를 다시 통과시켰다. 원본 보고서/입력은 수정하지 않았고, CSTR 최적화를
새로 돌리지 않았다. 이 CSTR cut 결함을 모든 Grid 방법의 동일 원인으로 일반화하지
않는다. 특히 Grid RIC에서도 같은 실패가 나타난다.

## 6. 검증·재현과 보존 범위

네 ZIP의 CRC, 내부 SHA256SUMS, 모든 job seal, `run.json`의 실행 소스 해시를
확인했다. 진단 ZIP의 내부 manifest와 제공된 외부 SHA256SUMS 235개도
원래 바이트와 일치했다. MINLP의 제공된 ZIP sidecar를 보존했고, 외부 sidecar가
없던 GDPopt 세 ZIP에는 수신한 원본 바이트의 SHA256 sidecar를 새로 기록했다.
내부 checksum 검증과 별개로, 이 새 sidecar가 송신 전 checksum이었다고 주장하지 않는다.

원본 solver 로그, 전체 해 벡터, 좌표/solver-call journal과 실행 소스는
[MINLP ZIP](../archives/grid_scip_minlp_20261023_143526_ce02ov4c.zip),
[GLOA ZIP](../archives/grid_scip_gloa_20261023_143538_k3722s6a.zip),
[LOA ZIP](../archives/grid_scip_loa_20261023_143545_30_v346o.zip),
[RIC ZIP](../archives/grid_scip_ric_20261023_143553_new9tgw4.zip)에 보존돼 있다.
[jobs.json](jobs.json)의 `solution_member`로 각각의 반환 벡터 위치를 찾을 수 있다.

```bash
python scripts/analyze_grid_scip_return.py --output /tmp/grid-scip-audit
python -m pytest tests/test_grid_scip_return.py -q
PYOMO_CONFIG_DIR=/path/to/existing/pyomo-config \
  python scripts/probe_grid_scip_presolve.py --output /tmp/grid-scip-presolve.json
```

감사 코드는 반환값이 빠졌을 때 초기값으로 통과시키거나, 저장된 objective/target
flag를 그대로 신뢰하지 않는 회귀 검사 7개를 포함한다. 별도 출력 디렉터리에서
재실행한 감사 JSON/CSV가 동일함을 확인했다. Pyomo 6.10.0과 기존 MC++ 환경을
사용한 probe는 solver-free이며 전체 알고리즘 재실행이 아니다. 실행 상세는
[validation.json](validation.json)에 기록했다. 설치된 Pyomo, 기존 실행기,
역사적 성능표 및 원고는 이 분석을 위해 수정하지 않았다.
