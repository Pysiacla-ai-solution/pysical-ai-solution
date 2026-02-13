from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from .dirs import DirLayout
from .gpu_monitor import GpuMonitor
from .process_runner import ProcessRunner


@dataclass
class Job:
    id: str
    script_path: Path
    user_id: str
    urgency: int
    vram_required: int
    created_at: float
    status: str = "QUEUED"
    assigned_gpu: Optional[int] = None
    pid: Optional[int] = None
    priority_score: float = 0.0


class InMemoryJobStore:
    """데모용 인메모리 작업 저장소 (향후 PostgreSQL 로 대체 가능)."""

    def __init__(self) -> None:
        self._jobs: Dict[str, Job] = {}
        self._lock = asyncio.Lock()

    async def add_job(self, job: Job) -> None:
        async with self._lock:
            self._jobs[job.id] = job

    async def list_jobs(self) -> List[Job]:
        async with self._lock:
            return list(self._jobs.values())

    async def get_job(self, job_id: str) -> Optional[Job]:
        async with self._lock:
            return self._jobs.get(job_id)

    async def update_job(self, job: Job) -> None:
        async with self._lock:
            self._jobs[job.id] = job


class GpuScheduler:
    """
    - fastgpu 스타일 디렉토리 기반 상태 머신
    - 비선점형 우선순위 스케줄링 + 에이징
    - GPU 상태를 고려한 작업 배치
    """

    def __init__(self, root_dir: Path) -> None:
        self.layout = DirLayout(root_dir)
        self.layout.setup_dirs()
        self.monitor = GpuMonitor()
        self.runner = ProcessRunner(self.layout.out)
        self.jobs = InMemoryJobStore()
        self._stop_event = asyncio.Event()
        self._poll_interval = 0.5  # 초

    async def submit_job(
        self,
        src_script: Path,
        user_id: str,
        urgency: int = 5,
        vram_required: int = 2 * 1024**9,
    ) -> Job:
        """
        사용자가 업로드한 스크립트를 to_run 디렉토리로 이동시키고 Job 생성.
        """
        job_id = str(uuid.uuid4())
        # 파일 이름에 job_id 를 포함시켜 fastgpu 스타일 정렬 우선순위 확보
        dst = self.layout.safe_rename(
            src_script, self.layout.to_run, new_name=f"{job_id}.py"
        )
        job = Job(
            id=job_id,
            script_path=dst,
            user_id=user_id,
            urgency=urgency,
            vram_required=vram_required,
            created_at=time.time(),
        )
        await self.jobs.add_job(job)
        return job

    async def list_jobs(self) -> List[Job]:
        return await self.jobs.list_jobs()

    async def get_job(self, job_id: str) -> Optional[Job]:
        return await self.jobs.get_job(job_id)

    def _compute_priority(self, job: Job) -> float:
        """
        P = (W_user * S_urgency) + α * T_wait - β * V_req

        데모에서는:
         - W_user = 1.0
         - α = 0.001
         - β = 1e-12
        """
        w_user = 1.0
        alpha = 0.001
        beta = 1e-12
        now = time.time()
        t_wait = now - job.created_at
        p = (w_user * job.urgency) + alpha * t_wait - beta * job.vram_required
        return p

    async def _pick_next_job(self) -> Optional[Job]:
        jobs = await self.jobs.list_jobs()
        # 아직 큐에 있고 실행 중이 아닌 작업만 대상
        candidates: List[Job] = [
            j for j in jobs if j.status in ("QUEUED", "HELD")
        ]
        if not candidates:
            return None

        for j in candidates:
            j.priority_score = self._compute_priority(j)

        # 비선점형 우선순위: 점수가 가장 높은 작업 선택
        candidates.sort(key=lambda j: j.priority_score, reverse=True)
        return candidates[0]

    def _find_available_gpu(self, vram_required: int) -> Optional[int]:
        metrics = self.monitor.list_gpus()
        for m in metrics:
            free_mem = m.memory_total - m.memory_used
            if not m.is_healthy:
                continue
            # fastgpu 처럼 "사용량이 1GB 미만" 기반으로 여유 판단
            if free_mem >= vram_required and m.memory_used < 1 * 1024**3:
                return m.gpu_id
        return None

    async def _launch_job(self, job: Job) -> None:
        gpu_id = self._find_available_gpu(job.vram_required)
        if gpu_id is None:
            return

        # 스크립트를 running 디렉토리로 이동
        new_script_path = self.layout.safe_rename(
            job.script_path, self.layout.running
        )
        job.script_path = new_script_path
        job.status = "RUNNING"
        job.assigned_gpu = gpu_id

        proc = self.runner.start_process(new_script_path, job.id, gpu_id)
        job.pid = proc.pid
        await self.jobs.update_job(job)

        async def waiter() -> None:
            return_code = await asyncio.get_event_loop().run_in_executor(
                None, proc.wait
            )
            # 종료 후 상태 디렉토리 이동
            if return_code == 0:
                self.layout.safe_rename(
                    new_script_path, self.layout.complete
                )
                job.status = "COMPLETED"
            else:
                self.layout.safe_rename(new_script_path, self.layout.fail)
                job.status = "FAILED"
            await self.jobs.update_job(job)

        asyncio.create_task(waiter())

    async def run_forever(self) -> None:
        """
        FastAPI lifespan 안에서 구동될 기본 스케줄러 루프.
        """
        try:
            while not self._stop_event.is_set():
                next_job = await self._pick_next_job()
                if next_job is not None:
                    await self._launch_job(next_job)
                await asyncio.sleep(self._poll_interval)
        finally:
            self.monitor.shutdown()

    async def stop(self) -> None:
        self._stop_event.set()

