from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.responses import HTMLResponse, FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from .dirs import DirLayout
from .gpu_monitor import GpuMonitor
from .scheduler import GpuScheduler, Job


_scheduler_singleton: GpuScheduler | None = None


def get_scheduler() -> GpuScheduler:
    global _scheduler_singleton
    if _scheduler_singleton is None:
        root = Path("./work")
        _scheduler_singleton = GpuScheduler(root)
    return _scheduler_singleton


router = APIRouter(prefix="/api/v1", tags=["gpu-scheduler"])


@router.post("/jobs/submit")
async def submit_job(
    file: Annotated[UploadFile, File(...)],
    user_id: str = "anonymous",
    urgency: int = 5,
    vram_required: int = 2 * 1024**30,
    scheduler: GpuScheduler = Depends(get_scheduler),
) -> Job:
    """
    Python 스크립트 업로드 후 to_run 큐에 등록.
    """
    temp_dir = Path("./uploads")
    temp_dir.mkdir(parents=True, exist_ok=True)
    temp_path = temp_dir / file.filename
    content = await file.read()
    temp_path.write_bytes(content)

    job = await scheduler.submit_job(
        temp_path, user_id=user_id, urgency=urgency, vram_required=vram_required
    )
    return job


@router.get("/jobs/queue")
async def list_jobs(
    scheduler: GpuScheduler = Depends(get_scheduler),
) -> list[Job]:
    return await scheduler.list_jobs()


@router.get("/gpu/metrics")
async def gpu_metrics() -> list[dict]:
    monitor = GpuMonitor()
    metrics = monitor.list_gpus()
    monitor.shutdown()
    return [m.__dict__ for m in metrics]


@router.get("/jobs/{job_id}/logs")
async def stream_logs(
    job_id: str,
    scheduler: GpuScheduler = Depends(get_scheduler),
):
    job = await scheduler.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    layout = DirLayout(Path("./work"))
    logs_dir = layout.out
    log_file = logs_dir / f"{job_id}.log"

    if not log_file.exists():
        raise HTTPException(status_code=404, detail="Log file not found yet")

    async def log_streamer():
        # 간단한 tail -f 스타일 스트리머
        with open(log_file, "rb") as f:
            while True:
                chunk = f.read(1024)
                if chunk:
                    yield chunk
                else:
                    # 작업이 끝났고 더 이상 쓸 내용이 없으면 종료
                    j = await scheduler.get_job(job_id)
                    if j is not None and j.status in ("COMPLETED", "FAILED"):
                        break
                    await asyncio.sleep(0.5)

    return StreamingResponse(log_streamer(), media_type="text/plain")


def create_app() -> FastAPI:
    app = FastAPI(title="GPU Scheduler (fastgpu-style)")

    # 정적 파일 (GPU 스케줄링 대시보드)
    app.mount("/static", StaticFiles(directory="static"), name="static")

    @app.get("/gpu.html", response_class=HTMLResponse)
    async def gpu_page() -> FileResponse:
        return FileResponse("static/gpu.html")

    @app.get("/", response_class=HTMLResponse)
    async def root() -> str:
        # 간단한 안내 페이지
        return """
        <html>
          <head><title>GPU Scheduler</title></head>
          <body>
            <h1>GPU Scheduler (fastgpu-style)</h1>
            <p>FastAPI + 디렉토리 기반 GPU 스케줄러 데모입니다.</p>
            <ul>
              <li><a href="/docs">/docs (Swagger UI)</a></li>
              <li><code>POST /api/v1/jobs/submit</code> - 스크립트 제출</li>
              <li><code>GET /api/v1/jobs/queue</code> - 작업 큐 조회</li>
              <li><code>GET /api/v1/gpu/metrics</code> - GPU 메트릭</li>
            </ul>
          </body>
        </html>
        """

    @app.on_event("startup")
    async def startup_event() -> None:
        # lifespan 대신 이벤트 훅으로 간단히 구현
        scheduler = get_scheduler()
        app.state.scheduler_task = asyncio.create_task(scheduler.run_forever())

    @app.on_event("shutdown")
    async def shutdown_event() -> None:
        scheduler = get_scheduler()
        await scheduler.stop()
        task = getattr(app.state, "scheduler_task", None)
        if task is not None:
            task.cancel()

    app.include_router(router)
    return app

