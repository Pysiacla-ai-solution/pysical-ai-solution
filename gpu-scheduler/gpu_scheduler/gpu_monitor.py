from __future__ import annotations

from dataclasses import dataclass
from typing import List


try:
    import pynvml  # type: ignore[import]
except Exception:  # pragma: no cover - GPU 없는 환경 대비
    pynvml = None  # type: ignore[assignment]


@dataclass
class GpuMetrics:
    gpu_id: int
    name: str
    memory_total: int
    memory_used: int
    temperature: int | None
    utilization: int | None
    is_healthy: bool


class GpuMonitor:
    """
    NVML(pynvml)을 사용해 GPU 상태를 조회.
    NVML 사용 불가 시, 단일 가상 "GPU 0" 만 있는 것처럼 동작.
    """

    def __init__(self) -> None:
        self._nvml_available = False
        if pynvml is not None:
            try:
                pynvml.nvmlInit()
                self._nvml_available = True
            except Exception:
                self._nvml_available = False

    def shutdown(self) -> None:
        if self._nvml_available:
            try:
                pynvml.nvmlShutdown()
            except Exception:
                pass

    def list_gpus(self) -> List[GpuMetrics]:
        if not self._nvml_available:
            # CPU-only 환경용 더미 메트릭
            return [
                GpuMetrics(
                    gpu_id=0,
                    name="virtual-gpu-0",
                    memory_total=16 * 1024**3,
                    memory_used=0,
                    temperature=None,
                    utilization=None,
                    is_healthy=True,
                )
            ]

        metrics: List[GpuMetrics] = []
        count = pynvml.nvmlDeviceGetCount()
        for idx in range(count):
            handle = pynvml.nvmlDeviceGetHandleByIndex(idx)
            name = pynvml.nvmlDeviceGetName(handle).decode("utf-8")
            mem = pynvml.nvmlDeviceGetMemoryInfo(handle)
            try:
                temp = pynvml.nvmlDeviceGetTemperature(
                    handle, pynvml.NVML_TEMPERATURE_GPU
                )
            except Exception:
                temp = None

            try:
                util = pynvml.nvmlDeviceGetUtilizationRates(handle).gpu
            except Exception:
                util = None

            is_healthy = True
            if temp is not None and temp >= 85:
                is_healthy = False

            metrics.append(
                GpuMetrics(
                    gpu_id=idx,
                    name=name,
                    memory_total=mem.total,
                    memory_used=mem.used,
                    temperature=temp,
                    utilization=util,
                    is_healthy=is_healthy,
                )
            )
        return metrics

