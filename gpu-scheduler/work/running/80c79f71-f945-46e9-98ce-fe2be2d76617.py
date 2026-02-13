"""
PyTorch GPU 사용 예시 스크립트.

- 이 스크립트는 torch가 설치되어 있어야 정상 동작합니다.
- GPU 스케줄러가 할당한 GPU만 보이도록 CUDA_VISIBLE_DEVICES 를 설정해 주므로,
  여기서는 평소처럼 "cuda" / "cuda:0" 만 사용하면 됩니다.
"""

import time

try:
    import torch
except ImportError:
    torch = None


def main() -> None:
    if torch is None:
        print("torch is not installed. CPU-only dummy run.")
        for i in range(5):
            print(f"[CPU DUMMY] step={i}")
            time.sleep(1)
        return

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print("Using device:", device)

    x = torch.randn(1000, 1000, device=device, requires_grad=True)
    w = torch.randn(1000, 1000, device=device, requires_grad=True)

    for step in range(20):
        y = x @ w
        loss = y.mean()
        loss.backward()
        print(f"[TRAIN] step={step}, loss={loss.item():.4f}")
        time.sleep(1)

    print("training finished")


if __name__ == "__main__":
    main()

