import os
from pathlib import Path
from typing import Literal


DirStatus = Literal["to_run", "running", "complete", "fail", "out"]


class DirLayout:
    """
    fastgpu 스타일 디렉토리 기반 상태 머신.

    root/
      to_run/   : 대기 중(Pending) 작업 스크립트
      running/  : 실행 중(Active) 작업 스크립트
      complete/ : 성공(Success) 종료 스크립트
      fail/     : 실패(Failed) 종료 스크립트
      out/      : 각 작업의 stdout/stderr 로그
    """

    def __init__(self, root: Path) -> None:
        self.root = Path(root).resolve()
        self.to_run = self.root / "to_run"
        self.running = self.root / "running"
        self.complete = self.root / "complete"
        self.fail = self.root / "fail"
        self.out = self.root / "out"

    def setup_dirs(self) -> None:
        """필요한 디렉토리 생성."""
        for d in (self.to_run, self.running, self.complete, self.fail, self.out):
            d.mkdir(parents=True, exist_ok=True)

    def get_dir(self, status: DirStatus) -> Path:
        return getattr(self, status)

    def safe_rename(self, src: Path, dst_dir: Path, new_name: str | None = None) -> Path:
        """
        원자적 파일 이동. 파일 이름 충돌 시 접미사 숫자를 증가시키며 회피.
        """
        src = Path(src)
        dst_dir = Path(dst_dir)
        dst_dir.mkdir(parents=True, exist_ok=True)

        if new_name is None:
            new_name = src.name

        target = dst_dir / new_name
        base, ext = os.path.splitext(new_name)
        counter = 1
        while target.exists():
            target = dst_dir / f"{base}_{counter}{ext}"
            counter += 1

        src.replace(target)
        return target

