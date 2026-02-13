## GPU Scheduler 데모

이 디렉토리는 **fastgpu 스타일 디렉토리 상태 머신**과 **FastAPI 기반 백엔드**를 결합한
소규모 GPU 우선순위 스케줄링 데모 구현입니다.

### 디렉토리 구조

- `gpu_scheduler/`
  - `dirs.py` : `to_run / running / complete / fail / out` 디렉토리 관리
  - `gpu_monitor.py` : `pynvml` 기반 GPU 상태 조회 (없으면 CPU-only 모드로 동작)
  - `scheduler.py` : 우선순위 점수 계산 + 백그라운드 스케줄러 루프
  - `process_runner.py` : `subprocess.Popen` 으로 스크립트 실행 및 로그 캡처
  - `api.py` : FastAPI 라우터 (작업 제출 / 큐 조회 / GPU 메트릭 / 로그 스트리밍)
- `main.py` : FastAPI 애플리케이션 엔트리 포인트 (lifespan 에서 스케줄러 실행)

### 설치

```bash
cd gpu-scheduler
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 실행

```bash
uvicorn main:app --reload
```

서버가 실행되면:

- `POST /api/v1/jobs/submit` : Python 스크립트 업로드 및 큐 등록
- `GET  /api/v1/jobs/queue` : 현재 큐/실행 중인 작업 정보
- `GET  /api/v1/gpu/metrics` : GPU/가상 GPU 상태
- `GET  /api/v1/jobs/{job_id}/logs` : 로그 스트리밍

현재 버전은 **파일 시스템 기반 상태 머신**을 중심으로 동작하며,
PostgreSQL 통합 및 고급 메타데이터 관리는 이후 단계에서 확장 가능하도록
구조를 나누어 두었습니다.

