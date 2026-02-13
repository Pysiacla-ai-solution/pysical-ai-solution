# job_lead.py 생성
import time
import os
import sys

def log(msg):
    print(f"[Lead/Debug] {msg}", flush=True)

log(f"🔥 긴급 디버깅 시작! (PID: {os.getpid()})")

try:
    import torch
    if torch.cuda.is_available():
        # 10GB VRAM 할당
        # 2,500,000,000 * 4 bytes ≈ 10GB
        tensor_size = 2_500_000_000
        try:
            data = torch.empty(tensor_size, dtype=torch.float32, device='cuda')
            log(f"✅ VRAM 10GB 확보 성공: {torch.cuda.get_device_name(0)}")
        except RuntimeError as e:
            log(f"❌ VRAM 부족 (OOM): {e}")
            sys.exit(1) # 실패 처리
    else:
        log("⚠️ CUDA 없음: CPU 모드")
except ImportError:
    log("⚠️ PyTorch 없음")

# 20초 만에 후딱 끝냄
total_time = 20
for i in range(total_time):
    log(f"버그 잡는 중... {i+1}/{total_time}초")
    time.sleep(1)

log("🎉 디버깅 완료 (서비스 정상화)")