from datetime import datetime, timedelta
import json
import math
import os
from pathlib import Path
from typing import List, Dict, Optional

# ── Configuration ─────────────────────────────────────────────────────────────

class PriorityConfig:
    """SLURM Priority Configuration"""
    # Weights for each factor (Total should ideally be balanced, but here we use large integers like SLURM)
    WEIGHT_AGE = 1000        # Age weight
    WEIGHT_FAIRSHARE = 10000 # Fair-share weight (Dominant factor)
    WEIGHT_JOB_SIZE = 500    # Job size weight
    WEIGHT_PARTITION = 1000  # Partition weight
    WEIGHT_QOS = 10000       # QOS weight (Critical factor)

    # Normalization Constants
    MAX_AGE_SEC = 7 * 24 * 3600  # 1 week to reach max age factor
    FAIRSHARE_DECAY_NORM = 10.0  # Normalize usage (e.g., 10 GPU-hours = 0.5 factor)
    MAX_VRAM_REF = 80            # 80GB VRAM = 1.0 JobSize factor

    # Partition Scores (0.0 - 1.0)
    PARTITION_SCORES = {
        "debug": 1.0,    # High priority for quick tests
        "normal": 0.5,   # Standard
        "batch": 0.2     # Low priority for long batch jobs
    }

    # QOS Scores (0.0 - 1.0)
    QOS_SCORES = {
        "hil": 1.0,       # Hardware-in-Loop (Critical)
        "high": 0.8,      # High priority
        "standard": 0.5,  # Standard
        "low": 0.1        # Low priority
    }

# ── Usage Tracker (Mock DB) ───────────────────────────────────────────────────

class UsageTracker:
    """Tracks user resource usage for FairShare calculation"""
    def __init__(self, db_path: str = "usage_db.json"):
        self.db_path = db_path
        self.usage_data = self._load_db()

    def _load_db(self) -> Dict[str, float]:
        if os.path.exists(self.db_path):
            try:
                with open(self.db_path, "r") as f:
                    return json.load(f)
            except:
                return {}
        return {}

    def _save_db(self):
        with open(self.db_path, "w") as f:
            json.dump(self.usage_data, f)

    def get_usage(self, user: str) -> float:
        return self.usage_data.get(user, 0.0)

    def record_usage(self, user: str, vram_gb: int, duration_sec: float):
        """Record usage (VRAM-Hours approx)"""
        usage = (vram_gb * duration_sec) / 3600.0  # VRAM-Hours
        current = self.usage_data.get(user, 0.0)
        self.usage_data[user] = current + usage
        self._save_db()

    def decay_usage(self, factor: float = 0.95):
        """Periodic decay (half-life simulation)"""
        for user in self.usage_data:
            self.usage_data[user] *= factor
        self._save_db()

# Singleton Instance
usage_tracker = UsageTracker(os.path.join(os.path.dirname(__file__), "usage.json"))

# ── Priority Engine ──────────────────────────────────────────────────────────

class PriorityEngine:
    def __init__(self):
        self.config = PriorityConfig()
        self.usage_tracker = usage_tracker

    def calculate_priority(self, job: Dict) -> float:
        """
        SLURM Multi-factor Priority Calculation
        Priority = Age + Fair-share + JobSize + Partition + QOS
        """
        # Parse Job Info
        user = job.get("user", "unknown")
        qos = job.get("qos", "standard").lower() or "standard"
        partition = job.get("partition", "normal").lower() or "normal"
        vram_gb = job.get("vram_gb", 2)
        
        # Parse Timestamps
        submitted_at_str = job.get("submitted_at", "")
        if submitted_at_str:
            submitted_at = datetime.fromisoformat(submitted_at_str.replace("Z", ""))
        else:
            submitted_at = datetime.utcnow()
        
        wait_time_sec = (datetime.utcnow() - submitted_at).total_seconds()

        # 1. Age Factor: Normalized waiting time
        #    Example: 1 week waiting = 1.0
        age_factor = min(wait_time_sec / self.config.MAX_AGE_SEC, 1.0)
        
        # 2. Fair-share Factor: Inverse of usage
        #    F = 1 / (1 + (UserUsage / DecayNorm))
        #    Heavy users get closer to 0, light users closer to 1
        user_usage = self.usage_tracker.get_usage(user)
        fs_factor = 1.0 / (1.0 + (user_usage / self.config.FAIRSHARE_DECAY_NORM))
        
        # 3. Job Size Factor: Normalized VRAM usage
        #    Standard SLURM can favor large or small jobs. 
        #    Here we favor LARGER jobs slightly to encourage efficient packing? 
        #    Actually usually Small jobs are favored for throughput, OR Large jobs for utilization.
        #    Let's favor Large jobs (Classic HPC policy) as per user request example '80GB ref'
        size_factor = min(vram_gb / self.config.MAX_VRAM_REF, 1.0)
        
        # 4. Partition Factor
        part_factor = self.config.PARTITION_SCORES.get(partition, 0.5)
        
        # 5. QOS Factor
        qos_factor = self.config.QOS_SCORES.get(qos, 0.5)
        
        # Calculate Weighted Sum
        priority = (
            (self.config.WEIGHT_AGE * age_factor) +
            (self.config.WEIGHT_FAIRSHARE * fs_factor) +
            (self.config.WEIGHT_JOB_SIZE * size_factor) +
            (self.config.WEIGHT_PARTITION * part_factor) +
            (self.config.WEIGHT_QOS * qos_factor)
        )
        
        # Store factors for debugging (Optional: job dict update not persisted here but useful if returned)
        job["_debug_factors"] = {
            "Age": f"{age_factor:.2f}",
            "FairShare": f"{fs_factor:.2f}",
            "Size": f"{size_factor:.2f}",
            "Partition": f"{part_factor:.2f}",
            "QOS": f"{qos_factor:.2f}",
            "Usage": f"{user_usage:.2f}"
        }
        
        return priority

# ── Main Interface ───────────────────────────────────────────────────────────

engine = PriorityEngine()

# Keep track of jobs already processed for usage statistics
processed_job_ids = set()

def sort_jobs_by_priority(jobs: List[Dict]) -> List[Dict]:
    """
    Sort jobs:
    1. RUNNING (Keep running)
    2. PENDING (Sort by Priority Score DESC)
    3. COMPLETED (By completion time DESC)
    """
    running = []
    pending = []
    completed = []
    other = []

    for job in jobs:
        status = job.get("status", "PENDING")
        job_id = job.get("job_id")
        
        # Calculate Priority for all jobs (for display/debug)
        prio = engine.calculate_priority(job)
        job["priority_score"] = prio
        
        # Usage Tracking for FairShare
        # If job is COMPLETED and not yet processed, record usage
        if status == "COMPLETED" and job_id not in processed_job_ids:
            # Calculate duration
            try:
                start_str = job.get("started_at", "")
                end_str = job.get("completed_at", "")
                if start_str and end_str:
                    start = datetime.fromisoformat(start_str.replace("Z", ""))
                    end = datetime.fromisoformat(end_str.replace("Z", ""))
                    duration = (end - start).total_seconds()
                    
                    user = job.get("user", "unknown")
                    vram = job.get("vram_gb", 2)
                    
                    engine.usage_tracker.record_usage(user, vram, duration)
                    processed_job_ids.add(job_id)
            except Exception as e:
                print(f"Error recording usage for job {job_id}: {e}")
        
        if status == "RUNNING":
            running.append(job)
        elif status == "PENDING":
            pending.append(job)
        elif status == "COMPLETED":
            completed.append(job)
        else:
            other.append(job)

    # Sort PENDING by Priority DESC
    pending.sort(key=lambda x: x["priority_score"], reverse=True)
    
    # Sort COMPLETED by end time DESC (Newest first)
    completed.sort(key=lambda x: x.get("completed_at", ""), reverse=True)

    return running + pending + completed + other

def compute_priority_for_job(job: Dict) -> float:
    """Helper for external use if needed"""
    return engine.calculate_priority(job)
