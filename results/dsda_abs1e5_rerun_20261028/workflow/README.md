# D-SDA 절대 개선 허용오차 변경 실험

이 워크플로는 Dantzig 서버의 RBFopt_Test 저장소 안에서 실험 입력을 준비하고 별도 명령으로 재실행한다.
실행 코드의 고정 위치는 `/local/scratch/a/lee4382/repository/RBFopt_Test/experiments/dsda_abs1e5/`이다.
입력 snapshot과 결과는 같은 저장소의 `results/` 아래에 새 날짜·시각·PID 이름으로 생성한다.
준비와 실행은 임시 디렉터리에 있는 코드나 전송 파일에 의존하지 않는다.

새 실험을 준비하려면 Dantzig 저장소에서 다음 명령을 실행한다.

```bash
cd /local/scratch/a/lee4382/repository/RBFopt_Test
.venv-dantzig/bin/python experiments/dsda_abs1e5/prepare.py
```

이 명령은 1190건의 입력과 pairing을 검증하고 기존 경계값·예산·초기점 테스트를 실행한다.
전체 실험은 시작하지 않으며 완료 후 `RUN WHEN READY` 줄에 별도 실행 명령을 출력한다.
준비된 입력은 원래 lookup, baseline, seed, 초기점과 순서, 후보 영역, 예산 및 성공 판정과 byte 단위로 일치하는지 검사한다.
`PREPARATION.json`에는 준비 시점의 고정 코드 경로, 소스 해시, 검증 명령 및 상태가 기록된다.

전체 실험은 출력된 명령을 사용하며 아래는 명령 형식이다.

```bash
.venv-dantzig/bin/python experiments/dsda_abs1e5/run.py server --repo "$PWD" --input "$PWD/results/dsda_abs1e5_input_실제준비식별자"
```

입력 준비부터 CPU 재측정과 백그라운드 실행까지 한 번에 수행하려면 다음 명령을 사용한다.

```bash
.venv-dantzig/bin/python experiments/dsda_abs1e5/launch.py
```

실행 PID와 로그 경로 및 예상 반환 ZIP 경로가 출력되며 SSH 종료 후에도 실행은 계속된다.
PID 출력은 시작 확인이며 전체 완료 확인은 로그와 최종 결과를 확인해야 한다.

원하면 `--output "$PWD/results/dsda_abs1e5_새실험이름"`으로 새 결과 디렉터리를 지정할 수 있다.
기존 디렉터리와 ZIP은 덮어쓰지 않으며 같은 입력을 다시 실행해도 결과 이름은 매번 새로 생성된다.
결과 ZIP 경로는 마지막 `RETURN_ARCHIVE`와 `SCP_RETURN_ARCHIVE` 줄에 출력된다.
다운로드는 맥 터미널에서 그 경로를 대상으로 SCP를 실행하고 목적지를 `~/Downloads/`로 지정한다.

이 실험은 D-SDA의 절대 개선 조건만 `old_value - new_value > 1e-5`로 지정한다.
상대 개선 조건은 없고 동률 판단 및 Grid 목표 종료의 기존 `tol=1e-12`는 유지한다.
이웃 탐색, 방향 탐색 및 기존에 연결된 best_seen와 best_run 갱신에 같은 개선 조건을 적용한다.
관측 incumbent와 최종 성공 판정은 모든 callback에 기반한 기존 공통 기준을 유지한다.
Grid 1050건과 Process 140건을 실행하며 최신 CSTR30 초기화와 Column 도메인 `[8..15]×[1..8]` 및 예산 13을 유지한다.
구성별 저장 목적값과 상태만 읽으며 추가 NLP를 호출하거나 다른 최적화 방법을 재실행하지 않는다.
Process 미수용 응답은 1e6이고 예산 및 반복 평가 계산과 watchdog은 기존 설정을 유지한다.
원래 LD-SDA 구현 전체를 재현했다고 표현하지 않는다.

실행 직전에 CPU 2 우선 지정을 해제하고 허용된 CPU와 SMT 형제의 사용률을 다시 측정한다.
SMT 쌍이 모두 여유 있는 물리 코어를 찾으면 논리 CPU 하나에 고정하고 모든 수치 라이브러리를 1스레드로 제한한다.
완전히 여유 있는 물리 코어가 관측되지 않으면 본실험을 시작하지 않는다.
선택 기록과 실제 CPU는 manifest에 보존하며 독점 예약이나 실행 내내의 무경합을 주장하지 않는다.

`reference/`는 SHA256 `555445b52d2fb40c58cc6e4a4a5321592dd6f2bd5cb48ead6ca31fc8174a8964`의 검증된 반환 ZIP에서 보존한 입력 및 실행 소스 사본이다.
그 안의 과거 문서나 provenance에 남은 임시 경로는 당시 기록이며 이 워크플로의 실행 의존성이 아니다.
새 고정 소스는 새 입력 snapshot에 복사한 뒤 해시로 봉인하므로 실행 후 소스 변경에도 사용한 버전을 확인할 수 있다.
기존 반환 ZIP과 결과 및 원고 대표 결과는 변경하지 않는다.
설치와 준비 명령은 Git commit, push, PR 수정, 병합과 CI 실행을 수행하지 않는다.
