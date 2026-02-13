"""
SLURM Service - Interface to mock SLURM scheduler via Docker
+ Priority Engine integration (non-preemptive)
"""

import json
import subprocess
from typing import List, Dict, Optional

from app.services.priority_engine import sort_jobs_by_priority

SLURM_CONTAINER_NAME = "slurm-mock"

class SlurmService:
    """Service for interacting with mock SLURM container"""
    
    @staticmethod
    def submit_job(job_name: str, script: str, qos: str = "", user_name: str = "unknown", 
                   gpu_count: int = 1, partition: str = "normal", vram_gb: int = 2) -> Dict:
        """
        Submit a job to SLURM with extended parameters
        """
        # Build sbatch command with all parameters
        # Note: --comment is used to store VRAM info for our mock engine
        cmd = [
            "docker", "exec", SLURM_CONTAINER_NAME, "sbatch",
            f"--job-name={job_name}",
            f"--user={user_name}",
            f"--partition={partition}",
            f"--gpus={gpu_count}",
            f"--comment=vram:{vram_gb}"
        ]
        
        if qos:
            cmd.append(f"--qos={qos}")
        
        # For mock, we just pass a dummy script path
        cmd.append("/tmp/script.sh")
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=True
            )
            
            # Parse output: "Submitted batch job 1001"
            output = result.stdout.strip()
            if "Submitted batch job" in output:
                job_id = output.split()[-1]
                return {
                    "job_id": job_id,
                    "message": output,
                    "status": "submitted"
                }
            else:
                raise ValueError(f"Unexpected sbatch output: {output}")
        
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"sbatch failed: {e.stderr}")
    
    @staticmethod
    def get_jobs() -> List[Dict]:
        """
        Get all jobs from queue, sorted by priority (non-preemptive).
        RUNNING jobs first, then PENDING sorted by score, then COMPLETED.
        
        Returns:
            List of job dictionaries with priority_score field
        """
        cmd = ["docker", "exec", SLURM_CONTAINER_NAME, "squeue", "--format=json"]
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=True
            )
            
            jobs = json.loads(result.stdout)
            # 우선순위 기반 정렬 (비선점: 정렬만, RUNNING은 건드리지 않음)
            return sort_jobs_by_priority(jobs)
        
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"squeue failed: {e.stderr}")
        except json.JSONDecodeError as e:
            raise RuntimeError(f"Failed to parse squeue output: {e}")
    
    @staticmethod
    def get_job(job_id: str) -> Optional[Dict]:
        """
        Get specific job by ID
        
        Args:
            job_id: Job ID to retrieve
        
        Returns:
            Job dictionary or None if not found
        """
        jobs = SlurmService.get_jobs()
        
        for job in jobs:
            if job.get("job_id") == str(job_id):
                return job
        
        return None
