#!/usr/bin/env python3
"""
Job Manager Daemon - Priority-based job lifecycle transitions
Non-preemptive: RUNNING 작업은 절대 중단하지 않음.
PENDING 작업 중 우선순위가 가장 높은 것부터 RUNNING 전환.

Priority = (W_fair × F_fair) + (W_age × F_age) + (W_phys × F_phys)
         + (W_res × F_res) + (W_HIL × F_HIL)
"""

import json
import time
from pathlib import Path
from datetime import datetime

JOBS_DIR = Path("/slurm/jobs")
CHECK_INTERVAL = 2   # seconds
MAX_CONCURRENT = 2   # 동시 실행 가능한 최대 작업 수

# ── 우선순위 가중치 ──
W_FAIR = 1.0
W_AGE  = 1.0
W_PHYS = 2.0
W_RES  = 1.0
W_HIL  = 10.0

PHYS_KEYWORDS = {"physics", "sim", "simulation", "isaac", "robot", "mujoco"}


def compute_priority(job, all_jobs):
    """단일 작업의 우선순위 점수 계산"""
    # F_fair
    user = job.get("user", "")
    if user:
        active = sum(1 for j in all_jobs
                     if j.get("user", "") == user and j.get("status") in ("PENDING", "RUNNING"))
        f_fair = 1.0 / max(active, 1)
    else:
        f_fair = 1.0

    # F_age (분 단위)
    try:
        sub = datetime.fromisoformat(job.get("submitted_at", "").replace("Z", ""))
        f_age = max((datetime.utcnow() - sub).total_seconds() / 60.0, 0.0)
    except (ValueError, TypeError):
        f_age = 0.0

    # F_phys
    text = (job.get("job_name", "") + " " + job.get("script", "")).lower()
    f_phys = 1.0 if any(kw in text for kw in PHYS_KEYWORDS) else 0.0

    # F_res
    f_res = 1.0 / max(job.get("gpu_count", 1), 1)

    # F_hil
    f_hil = 1.0 if job.get("qos", "").lower() == "hil" else 0.0

    return round(
        W_FAIR * f_fair + W_AGE * f_age + W_PHYS * f_phys
        + W_RES * f_res + W_HIL * f_hil, 2
    )


def load_all_jobs():
    """모든 job JSON 파일 로드 → (job_data, job_file) 리스트"""
    results = []
    if not JOBS_DIR.exists():
        return results
    for jf in JOBS_DIR.glob("*.json"):
        if jf.name.startswith("."):
            continue
        try:
            with open(jf, "r") as f:
                results.append((json.load(f), jf))
        except Exception as e:
            print(f"Error reading {jf}: {e}")
    return results


def save_job(job_data, job_file):
    with open(job_file, "w") as f:
        json.dump(job_data, f, indent=2)


def process_jobs():
    """
    비선점 스케줄링:
    1. RUNNING → COMPLETED (실행 시간 10 초 초과)
    2. PENDING 중 우선순위 높은 순으로 빈 슬롯에 RUNNING 전환
    """
    entries = load_all_jobs()
    if not entries:
        return

    now = datetime.utcnow()
    all_jobs = [j for j, _ in entries]

    # ── 1) RUNNING → COMPLETED ───────────────────
    for job, jf in entries:
        if job.get("status") != "RUNNING":
            continue
        started_str = job.get("started_at")
        if not started_str:
            continue
        try:
            started = datetime.fromisoformat(started_str.replace("Z", ""))
            if (now - started).total_seconds() >= 30:
                job["status"] = "COMPLETED"
                job["completed_at"] = now.isoformat() + "Z"
                save_job(job, jf)
                print(f"Completed job {job['job_id']}")
        except (ValueError, TypeError):
            pass

    # ── 2) 현재 RUNNING 수 확인 ──────────────────
    running_count = sum(1 for j, _ in entries if j.get("status") == "RUNNING")
    available_slots = MAX_CONCURRENT - running_count

    if available_slots <= 0:
        return

    # ── 3) PENDING 작업을 우선순위 내림차순 정렬 ──
    pending = [(j, jf) for j, jf in entries if j.get("status") == "PENDING"]
    for j, _ in pending:
        j["priority_score"] = compute_priority(j, all_jobs)
    pending.sort(key=lambda x: x[0]["priority_score"], reverse=True)

    # ── 4) 높은 우선순위부터 RUNNING 전환 (비선점) ─
    for job, jf in pending:
        if available_slots <= 0:
            break

        job["status"] = "RUNNING"
        job["started_at"] = now.isoformat() + "Z"
        save_job(job, jf)
        print(f"Started job {job['job_id']}  (priority={job['priority_score']}, qos={job.get('qos','')})")
        available_slots -= 1


def main():
    print("Job Manager Daemon started  [priority-based, non-preemptive]")
    print(f"  jobs dir     : {JOBS_DIR}")
    print(f"  interval     : {CHECK_INTERVAL}s")
    print(f"  max concurrent: {MAX_CONCURRENT}")
    print("-" * 50)

    JOBS_DIR.mkdir(parents=True, exist_ok=True)

    while True:
        try:
            process_jobs()
            time.sleep(CHECK_INTERVAL)
        except KeyboardInterrupt:
            print("\nJob Manager Daemon stopped")
            break
        except Exception as e:
            print(f"Unexpected error: {e}")
            time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()
