"""
GPU Router - API endpoints for GPU job scheduling via SLURM
"""

from fastapi import APIRouter, Depends, HTTPException, status, Cookie
from jose import jwt, JWTError
from pydantic import BaseModel, Field
from typing import List, Optional

from app.services.slurm_service import SlurmService

router = APIRouter()

# JWT configuration (same as assistant_router)
SECRET_KEY = "RANDOM_SECRET_KEY"
ALGORITHM = "HS256"
ISSUER = "simple-auth-server"

def get_current_user(
    access_token: str | None = Cookie(default=None, alias="ACCESS_TOKEN")
):
    """JWT authentication dependency"""
    if access_token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated (no ACCESS_TOKEN cookie)",
        )

    try:
        payload = jwt.decode(
            access_token,
            SECRET_KEY,
            algorithms=[ALGORITHM],
            issuer=ISSUER,
        )
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )

    user_id = payload.get("sub")
    username = payload.get("username")

    if user_id is None or username is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
        )

    return {"id": user_id, "username": username}


# Pydantic models
class JobSubmitRequest(BaseModel):
    """Job submission request model"""
    job_name: str
    script: str
    vram_gb: int = 2
    partition: str = "normal"
    qos: str = "standard"


class JobInfo(BaseModel):
    """Job information model"""
    job_id: str
    job_name: str
    user: str = "unknown"
    status: str  # PENDING, RUNNING, COMPLETED
    qos: str
    partition: str = "normal"
    gpu_count: int = 1  # Derived from VRAM (approx)
    priority_score: float = 0.0
    submitted_at: str
    started_at: Optional[str] = None
    completed_at: Optional[str] = None


class JobSubmitResponse(BaseModel):
    """Response model for job submission"""
    job_id: str
    message: str
    status: str


# API endpoints
@router.post("/jobs", response_model=JobSubmitResponse)
async def submit_job(
    request: JobSubmitRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Submit a new GPU job to SLURM
    
    - **job_name**: Name for the job
    - **script**: Script or command to execute
    - **vram_gb**: VRAM requested in GB (default 2)
    - **partition**: SLURM partition (normal, debug, batch)
    - **qos**: Quality of Service (standard, high, hil)
    """
    try:
        # Pydantic 모델에 gpu_count 필드가 없다면 기본값 1 사용
        # VRAM 16GB = 1 GPU 단위로 임시 계산 (데모용)
        # 실제로는 GPU 단위 할당이지만, 여기선 VRAM 요구량을 기록
        
        result = SlurmService.submit_job(
            job_name=request.job_name,
            script=request.script,
            qos=request.qos,
            user_name=current_user["username"],
            gpu_count=max(1, request.vram_gb // 16), # Simple conversion for sbatch --gpus
            partition=request.partition,
            vram_gb=request.vram_gb
        )
        return result
    
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to submit job: {str(e)}"
        )


@router.get("/jobs", response_model=List[JobInfo])
async def get_jobs(current_user: dict = Depends(get_current_user)):
    """
    Get all jobs from SLURM queue
    
    Returns list of jobs with their current status
    """
    try:
        jobs = SlurmService.get_jobs()
        return jobs
    
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get jobs: {str(e)}"
        )


@router.get("/jobs/{job_id}", response_model=JobInfo)
async def get_job(
    job_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Get specific job by ID
    
    - **job_id**: Job ID to retrieve
    """
    try:
        job = SlurmService.get_job(job_id)
        
        if job is None:
            raise HTTPException(
                status_code=404,
                detail=f"Job {job_id} not found"
            )
        
        return job
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get job: {str(e)}"
        )
