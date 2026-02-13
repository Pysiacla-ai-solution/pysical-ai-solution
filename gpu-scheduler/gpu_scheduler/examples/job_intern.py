# job_intern.py 생성
import time
import os
import sys

def log(msg):
    print(f"[Intern/Batch] {msg}", flush=True)

log(f"💤 배치 작업 시작 (PID: {os.getpid()})")

try:
    import torch
    if torch.cuda.is_available():
        # 1GB VRAM 할당 (float32는 4바이트, 약 2.5억개 요소)
        # 250,000,000 * 4 bytes ≈ 1GB
        tensor_size = 250_000_000
        data = torch.empty(tensor_size, dtype=torch.float32, device='cuda')
        log(f"✅ VRAM 1GB 할당 완료: {torch.cuda.get_device_name(0)}")
    else:
        log("⚠️ CUDA 없음: CPU 모드로 1GB 흉내만 냅니다.")
except ImportError:
    log("⚠️ PyTorch 없음: 메모리 할당 없이 진행합니다.")

# 60초 동안 천천히 실행 (다른 작업이 대기하게 만듦)
total_time = 60
for i in range(total_time):
    log(f"열심히 일하는 중... {i+1}/{total_time}초")
    time.sleep(1)

log("🎉 배치 작업 완료!")
