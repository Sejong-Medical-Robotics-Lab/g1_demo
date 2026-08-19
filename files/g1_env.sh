#!/usr/bin/env bash
# g1_env.sh — G1 실기체 작업 터미널 준비 (source 로 실행할 것)
#
#   사용:  source ~/g1_real/g1_env.sh
#          source ~/g1_real/g1_env.sh enp2s0     # 인터페이스 직접 지정
#
# 이 스크립트는 SDK 제어용 터미널 전용이다.
# ROS 2(Jazzy) 작업은 '다른 터미널'에서 한다 — venv 와 /opt/ros 를 같은 셸에서
# source 하면 PYTHONPATH 가 섞여 문제가 생긴다.

# ── 사용자 환경에 맞게 여기만 수정 ────────────────────────────────────
SDK_DIR="$HOME/unitree_sdk2_python"
CYCLONE_DIR="$HOME/cyclonedds/install"
WORK_DIR="$HOME/g1_real"      # 스크립트가 있는 작업 폴더 — 마지막에 여기로 이동
DEFAULT_IFACE=""          # 예: "enp2s0" — 비워두면 자동 탐지 시도
# ─────────────────────────────────────────────────────────────────────

if [ "${BASH_SOURCE[0]}" = "${0}" ]; then
    echo "[오류] 이 스크립트는 source 로 실행해야 합니다:  source ${0}"
    exit 1
fi

export CYCLONEDDS_HOME="$CYCLONE_DIR"

if [ ! -d "$SDK_DIR/.venv" ]; then
    echo "[오류] venv 를 찾을 수 없습니다: $SDK_DIR/.venv"
    return 1
fi

# venv 활성화는 현재 위치와 무관하므로 절대경로로 source 한다.
# shellcheck disable=SC1091
source "$SDK_DIR/.venv/bin/activate" || return 1

# ── 로봇이 붙은 인터페이스 추정 (192.168.123.x 대역을 가진 NIC) ──
#    유선 직결이든 공유기 경유 무선이든 이 대역을 가진 인터페이스면 잡는다.
G1_IFACE="${1:-$DEFAULT_IFACE}"
if [ -z "$G1_IFACE" ]; then
    G1_IFACE=$(ip -o -4 addr show 2>/dev/null \
               | awk '$4 ~ /^192\.168\.123\./ {print $2; exit}')
fi
export G1_IFACE
export G1_DOMAIN="${G1_DOMAIN:-0}"

echo "────────────────────────────────────────────────────────"
echo " venv        : $(python3 -c 'import sys; print(sys.prefix)')"
echo " CYCLONEDDS  : $CYCLONEDDS_HOME"
if python3 -c "import unitree_sdk2py" 2>/dev/null; then
    echo " SDK import  : OK"
else
    echo " SDK import  : 실패 — venv/설치 확인 필요"
fi
if [ -n "$G1_IFACE" ]; then
    MYIP=$(ip -o -4 addr show "$G1_IFACE" | awk '{print $4}')
    echo " G1_IFACE    : $G1_IFACE  ($MYIP)"
else
    echo " G1_IFACE    : (미검출) — 유선 IP 를 192.168.123.x 로 설정하세요."
    echo "               .161(운동제어 PC1) / .164(개발 PC2) 는 사용 금지"
fi
echo " G1_DOMAIN   : $G1_DOMAIN"
echo "────────────────────────────────────────────────────────"

# ── CYCLONEDDS_URI ───────────────────────────────────────────────────
# Ubuntu 24.04 + cyclonedds 0.10.2 에서 SDK 에 인터페이스 이름을 인자로 넘기면
# C 레벨에서 죽는다("buffer overflow detected"). SDK 가 그때 만드는 설정 XML 의
# <Tracing>(/tmp/cdds.LOG) 블록이 원인이다. 인터페이스 지정을 이 환경변수로
# 대신하면 스크립트는 인자 없이 초기화할 수 있어 문제를 피한다.
if [ -n "$G1_IFACE" ]; then
    export CYCLONEDDS_URI="<CycloneDDS><Domain id=\"any\"><General><Interfaces><NetworkInterface name=\"$G1_IFACE\" priority=\"default\" multicast=\"default\"/></Interfaces></General></Domain></CycloneDDS>"
    echo " CYCLONEDDS_URI : 설정됨 (interface=$G1_IFACE)"
else
    unset CYCLONEDDS_URI
fi

# 작업 폴더로 이동 — 이후 ./g1_stand_test.py 처럼 바로 실행 가능
if cd "$WORK_DIR" 2>/dev/null; then
    echo " 작업 폴더    : $WORK_DIR"
    echo " 예:  python3 g1_stand_test.py --iface \$G1_IFACE"
else
    echo " [경고] 작업 폴더 없음: $WORK_DIR (스크립트를 여기로 옮기세요)"
fi
