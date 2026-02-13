from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Optional


class ProcessRunner:
    """
    subprocess.Popen 을 사용해 스크립트를 실행하고,
    stdout/stderr 를 로그 파일로 캡처한다.
    """

    def __init__(self, logs_dir: Path) -> None:
        self.logs_dir = Path(logs_dir)
        self.logs_dir.mkdir(parents=True, exist_ok=True)

    def start_process(
        self,
        script_path: Path,
        job_id: str,
        assigned_gpu_id: Optional[int] = None,
    ) -> subprocess.Popen:
        env = os.environ.copy()

        # CUDA 환경 격리: 할당된 GPU만 보이도록 설정
        if assigned_gpu_id is not None:
            env["CUDA_DEVICE_ORDER"] = "PCI_BUS_ID"
            env["CUDA_VISIBLE_DEVICES"] = str(assigned_gpu_id)

        log_file_path = self.logs_dir / f"{job_id}.log"
        log_fh = open(log_file_path, "wb")

        # 비차단 실행 + 실시간 로그 기록
        process = subprocess.Popen(
            ["python", str(script_path)],
            stdout=log_fh,
            stderr=subprocess.STDOUT,
            env=env,
            bufsize=1,
        )
        return process

