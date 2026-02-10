# ffmpeg 설치 (리눅스 우분투)
sudo apt update
sudo apt install -y ffmpeg pkg-config

# 가상환경 활성화 상태에서
python -m pip install --upgrade pip setuptools wheel
python -m pip install -r requirements.txt