#!/usr/bin/env bash
# venv311_setup.sh — 로봇을 "들을 수 있는" Python 3.11 환경 구축 (한 번만)
#
# 배경: 이 PC(3.12)에선 0.10 바인딩=크래시 / 11.x=로봇과 짝맺기 불가.
# 공식 지원 조합(3.11 + cyclonedds 0.10.2)만 로봇 구독이 가능하다.
#
# 사용:  bash ~/g1_real/venv311_setup.sh
#        (중간에 sudo 비밀번호 물어봄, 전체 5~10분)

set -e

echo "── ① Python 3.11 설치 (deadsnakes PPA) ──"
sudo add-apt-repository -y ppa:deadsnakes/ppa
sudo apt update
sudo apt install -y python3.11 python3.11-venv python3.11-dev

echo "── ② 전용 venv 생성 ──"
python3.11 -m venv ~/venv311

echo "── ③ cyclonedds 0.10.2 + sdk2py 설치 ──"
source ~/venv311/bin/activate
# sdist 빌드가 필요할 경우 기존 0.10.2 C 라이브러리를 참조하도록
export CYCLONEDDS_HOME="$HOME/cyclonedds/install"
pip install --upgrade pip
pip install cyclonedds==0.10.2
pip install -e ~/unitree_sdk2_python

echo "── ④ 자가 검증: 리스너 루프백 (로봇 불필요) ──"
IFACE=$(ip -o link show | awk -F': ' '/enx/{print $2; exit}')
if [ -z "$IFACE" ]; then
    echo "  enx 인터페이스 미검출 — 케이블 연결 후 수동으로:"
    echo "    source ~/venv311/bin/activate"
    echo "    python3 ~/g1_real/test_dds_loopback.py --iface enx..."
    exit 0
fi
python3 ~/g1_real/test_dds_loopback.py --iface "$IFACE"

echo ""
echo "위에 [수신 OK] 가 떴으면 3.11 환경 완성 — RELAY_GUIDE.md 2단계로."
