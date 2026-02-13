
from __future__ import annotations

import asyncio
import time
import uuid
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Literal

from .dirs import DirLayout
from .gpu_monitor import GpuMonitor
from .process_runner import ProcessRunner


@dataclass
class SlurmConfig:
    """
    SLURM 스타일 우선순위 가중치 설정.
    각 항목은 0~1.0 사이의 Factor와 곱해져 최종 점수가 됩니다.
    """
    # Weights (가중치)
    weight_age: float = 1000.0       # 대기 시간이 길수록 점수
    weight_fairshare: float = 10000.0 # 공정성 (사용량이 적을수록 점수) - 가장 큼
    weight_job_size: float = 500.0   # 작업 크기 (클수록 점수 or 작을수록 점수)
    weight_partition: float = 1000.0 # 파티션별 기본 점수
    weight_qos: float = 1000.0       # QOS 등급별 점수

    # Fair-share 설정
    # 반감기 등 복잡한 로직 대신, '평균 사용량' 대비 내 사용량이 2배면 점수 0.5배 되는 식의 감쇠 계수
    fairshare_decay_norm: float = 3600.0 * 10  # 10시간 사용을 기준으로 정규화

    # Partition / QOS 정의 (이름 -> 점수 0.0~1.0 Factor)
    partitions: Dict[str, float] = field(default_factory=lambda: {
        "debug": 1.0,    # 높은 우선순위
        "normal": 0.5,   # 기본
        "batch": 0.1     # 백그라운드
    })
    
    qos_levels: Dict[str, float] = field(default_factory=lambda: {
        "admin": 1.0,
        "premium": 0.8,
        "standard": 0.5,
        "guest": 0.1
    })


@dataclass
class Job:
    id: str
    script_path: Path
    user_id: str
    vram_required: int
    created_at: float
    
    # SLURM Factor 관련 필드 추가
    partition: str = "normal"
    qos: str = "standard"
    
    status: str = "QUEUED"
    assigned_gpu: Optional[int] = None
    pid: Optional[int] = None
    
    # 계산된 우선순위 점수 및 디버깅용 팩터
    priority_score: float = 0.0
    _debug_factors: Dict[str, float] = field(default_factory=dict)

    @property
    def time_waiting(self) -> float:
        return time.time() - self.created_at


class UserUsageTracker:
    """
    Fair-share 계산을 위한 사용자별 리소스 사용량 추적기.
    (메모리 내 저장, 실제 구현 시 DB 필요)
    """
    def __init__(self) -> None:
        # user_id -> total_gpu_seconds
        self._usage: Dict[str, float] = {}
        self._lock = asyncio.Lock()

    async def add_usage(self, user_id: str, duration_sec: float, gpu_count: int = 1) -> None:
        async with self._lock:
            current = self._usage.get(user_id, 0.0)
            # GPU 사용 시간 = 시간 * GPU 개수
            self._usage[user_id] = current + (duration_sec * gpu_count)

    async def get_usage(self, user_id: str) -> float:
        async with self._lock:
            return self._usage.get(user_id, 0.0)

    async def get_total_usage(self) -> float:
        async with self._lock:
            return sum(self._usage.values())


class InMemoryJobStore:
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
    def __init__(self, root_dir: Path) -> None:
        self.layout = DirLayout(root_dir)
        self.layout.setup_dirs()
        self.monitor = GpuMonitor()
        self.runner = ProcessRunner(self.layout.out)
        self.jobs = InMemoryJobStore()
        self.usage_tracker = UserUsageTracker() # Fair-share용
        self.config = SlurmConfig()
        
        self._stop_event = asyncio.Event()
        self._poll_interval = 1.0

    async def submit_job(
        self,
        src_script: Path,
        user_id: str,
        vram_required: int = 2 * 1024**3,
        partition: str = "normal",
        qos: str = "standard",
    ) -> Job:
        job_id = str(uuid.uuid4())
        # to_run 디렉토리로 이동
        dst = self.layout.safe_rename(
            src_script, self.layout.to_run, new_name=f"{job_id}.py"
        )
        
        job = Job(
            id=job_id,
            script_path=dst,
            user_id=user_id,
            vram_required=vram_required,
            partition=partition,
            qos=qos,
            created_at=time.time(),
        )
        await self.jobs.add_job(job)
        return job

    async def list_jobs(self) -> List[Job]:
        return await self.jobs.list_jobs()

    async def get_job(self, job_id: str) -> Optional[Job]:
        return await self.jobs.get_job(job_id)

    # --------------------------------------------------------------------------
    # SLURM Priority Logic
    # --------------------------------------------------------------------------
    async def _calculate_slurm_priority(self, job: Job) -> float:
        """
        SLURM Multi-factor Priority Calculation
        Priority = Age + Fair-share + JobSize + Partition + QOS
        """
        # 1. Age Factor: 대기 시간 (최대 1주일 대기 기준 1.0)
        max_age_sec = 7 * 24 * 3600
        age_factor = min(job.time_waiting / max_age_sec, 1.0)

        # 2. Fair-share Factor: 사용량이 많을수록 0에 수렴
        # F = 1 / (1 + (UserUsage / DecayNorm))
        user_usage = await self.usage_tracker.get_usage(job.user_id)
        fs_factor = 1.0 / (1.0 + (user_usage / self.config.fairshare_decay_norm))
        
        # 3. Job Size Factor: VRAM 요구량 기준 (큰 작업 선호 시)
        # 예: 80GB가 1.0이 되도록 정규화
        max_vram_ref = 80 * 1024**3
        size_factor = min(job.vram_required / max_vram_ref, 1.0)

        # 4. Partition Factor: 설정된 파티션 점수
        part_factor = self.config.partitions.get(job.partition, 0.5)

        # 5. QOS Factor: 설정된 QOS 점수
        qos_factor = self.config.qos_levels.get(job.qos, 0.5)

        # 최종 점수 계산
        prio = (
            (self.config.weight_age * age_factor) +
            (self.config.weight_fairshare * fs_factor) +
            (self.config.weight_job_size * size_factor) +
            (self.config.weight_partition * part_factor) +
            (self.config.weight_qos * qos_factor)
        )

        # 디버깅/로깅을 위해 팩터 저장
        job._debug_factors = {
            "Age": age_factor,
            "FairShare": fs_factor,
            "Size": size_factor,
            "Partition": part_factor,
            "QOS": qos_factor,
            "RawUsage": user_usage
        }
        
        return prio

    async def _pick_next_job(self) -> Optional[Job]:
        """우선순위가 가장 높은 작업 선택"""
        jobs = await self.jobs.list_jobs()
        candidates: List[Job] = [
            j for j in jobs if j.status == "QUEUED"
        ]
        if not candidates:
            return None

        # 모든 후보 작업의 우선순위 재계산 (시간 경과, 사용량 변화 반영)
        for j in candidates:
            j.priority_score = await self._calculate_slurm_priority(j)

        # 점수 내림차순 정렬
        candidates.sort(key=lambda j: j.priority_score, reverse=True)
        return candidates[0]

# 기존 _find_available_gpu 함수를 이걸로 교체하세요.
    async def _find_available_gpu(self, vram_required: int) -> Optional[int]:
        metrics = self.monitor.list_gpus()
        
        # [수정] 현재 실행 중인 작업이 있는지 확인
        jobs = await self.jobs.list_jobs()
        running_jobs = [j for j in jobs if j.status == "RUNNING"]
        
        for m in metrics:
            if not m.is_healthy:
                continue

            # [수정] 가상 GPU(virtual-gpu-0) 특수 처리
            # 실제 GPU는 메모리 사용량을 보고 판단하지만, 
            # 가상 GPU는 메모리 사용량이 항상 0이므로, 실행 중인 작업 개수로 판단해야 함.
            if m.name == "virtual-gpu-0" and len(running_jobs) > 0:
                # 이미 누군가 돌고 있다면 바쁜 것으로 간주하고 스킵
                continue

            # (실제 GPU용 로직) 메모리 잔여량 체크
            free_mem = m.memory_total - m.memory_used
            if free_mem >= vram_required and m.memory_used < 1 * 1024**3:
                return m.gpu_id
                
        return None

    async def _launch_job(self, job: Job) -> None:
        gpu_id = await self._find_available_gpu(job.vram_required)

        if gpu_id is None:
            return

        # 상태 변경
        start_time = time.time()
        new_script_path = self.layout.safe_rename(
            job.script_path, self.layout.running
        )
        job.script_path = new_script_path
        job.status = "RUNNING"
        job.assigned_gpu = gpu_id
        
        proc = self.runner.start_process(new_script_path, job.id, gpu_id)
        job.pid = proc.pid
        await self.jobs.update_job(job)

        # 백그라운드 태스크로 종료 대기 및 후처리
        asyncio.create_task(self._wait_and_finalize(job, proc, start_time))

    async def _wait_and_finalize(self, job: Job, proc, start_time: float) -> None:
        """프로세스 종료 대기 및 Fair-share 업데이트"""
        return_code = await asyncio.get_event_loop().run_in_executor(
            None, proc.wait
        )
        
        duration = time.time() - start_time
        
        # Fair-share: 사용량 업데이트 (성공/실패 여부 상관없이 점유 시간만큼 부과)
        await self.usage_tracker.add_usage(job.user_id, duration)

        if return_code == 0:
            self.layout.safe_rename(job.script_path, self.layout.complete)
            job.status = "COMPLETED"
        else:
            self.layout.safe_rename(job.script_path, self.layout.fail)
            job.status = "FAILED"
            
        await self.jobs.update_job(job)

    async def run_forever(self) -> None:
        print("🔄 [SCHEDULER] 스케줄러 루프 시작")
        try:
            while not self._stop_event.is_set():
                next_job = await self._pick_next_job()

                if next_job is not None:
                    await self._launch_job(next_job)
                    # 작업이 없으면 조금 더 길게 대기
                await asyncio.sleep(self._poll_interval)
        finally:
            self.monitor.shutdown()

    async def stop(self) -> None:
        self._stop_event.set()