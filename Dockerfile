FROM python:3.11-slim

# 시스템 패키지
RUN apt-get update \
 && apt-get install -y --no-install-recommends ffmpeg libgomp1 \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 의존성만 먼저 복사해 캐시 활용
COPY requirements.txt ./
RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir -r requirements.txt

# 애플리케이션 소스
COPY . /app

# (옵션) 프로덕션에서는 --reload 제거 권장
CMD ["uvicorn","app.main:app","--host","0.0.0.0","--port","8008","--reload"]
