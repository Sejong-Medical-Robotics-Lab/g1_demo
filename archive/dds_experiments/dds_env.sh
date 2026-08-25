# dds_env.sh — 구독이 되는 환경(venv_dds) 진입 헬퍼
#
# 배경: 기존 venv 의 cyclonedds 0.10.x 는 Python 3.12 에서 "구독자 생성"
# 이 buffer overflow 로 죽는다 (2026-08-25 루프백 실험으로 확정).
# venv_dds + cyclonedds 11.0.1 조합만 구독이 된다.
#
# ★ 반드시 지킬 것:
#   - 이 환경에서는 g1ros 별칭을 실행하지 말 것 (옛 라이브러리 경로를
#     다시 물려서 크래시 재발)
#   - 구독이 필요한 코드(g1_odom_bridge, probe 류)만 여기서 실행
#   - 기존 코드(cmdvel 브리지, 팔동작 등)는 평소처럼 g1ros 터미널에서
#
# 사용:  source ~/g1_real/dds_env.sh

source ~/venv_dds/bin/activate

# 옛 커스텀 빌드(0.10.2)의 흔적 제거 — 휠에 번들된 11.x 라이브러리를 쓰게
unset CYCLONEDDS_HOME
unset CYCLONEDDS_URI
unset LD_LIBRARY_PATH

# 인터페이스 자동 탐지
G1_IFACE=$(ip -o link show | awk -F': ' '/enx/{print $2; exit}')
if [ -n "$G1_IFACE" ]; then
    export G1_IFACE
    IP=$(ip -o -4 addr show "$G1_IFACE" | awk '{print $4}')
    echo "  [dds_env] venv_dds + cyclonedds 11.x"
    echo "  [dds_env] G1_IFACE=$G1_IFACE (${IP:-IP 없음 — 유선 설정 확인})"
else
    echo "  [dds_env] enx 인터페이스 미검출 — 케이블 확인 후:"
    echo "            export G1_IFACE=enx..."
fi
