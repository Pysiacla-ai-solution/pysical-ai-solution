import time


def main() -> None:
    """
    GPU 스케줄러 데모용 아주 단순한 작업.
    - 매 초마다 로그 한 줄씩 출력
    - 총 10초 동안 동작
    """
    for i in range(10):
        print(f"[DUMMY JOB] step={i}")
        time.sleep(1)

    print("[DUMMY JOB] finished")


if __name__ == "__main__":
    main()

