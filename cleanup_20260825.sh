#!/usr/bin/env bash
# cleanup_20260825.sh — B안 개통 후 폴더 정리 (한 번만 실행)
#
#   bash ~/g1_real/cleanup_20260825.sh
#
# 하는 일:
#   ① 용도 끝난 실험 파일 → archive/ 로 이동 (삭제 아님 — 기록 보존)
#   ② 로그를 깃에서 제외 (파일은 로컬에 유지)
#   ③ 루트 지도 사본을 maps/ 최신본과 동기화
#   ④ 파이썬 캐시 삭제
# 건드리지 않는 것: 팀원 파일(g1_P_A_action 등), 문서, 데모 코드 전부

set -e
cd ~/g1_real

echo "── ① 실험 파일 보관소로 이동 ──"
mkdir -p archive/dds_experiments archive/old_stack

# DDS 규명 실험 세트 (2026-08-25 저녁 — 결론 나서 은퇴)
for f in check_odomstate.py probe_odom.py probe_odom311.py \
         g1_odom_tap.py g1_odom_bridge.py g1_odom_direct.py \
         dds_env.sh venv311_setup.sh \
         test_dds_loopback.py test_dds_loopback_poll.py test_dds_crossver.py; do
    [ -f "$f" ] && mv "$f" archive/dds_experiments/ && echo "   → $f"
done

# 초기 스택 잔재 (SLAM+Nav 동시 실행 시절 / pcd 슬라이스 경로)
for f in g1_nav2.launch.py nav2_g1.yaml pcd_to_map.py; do
    [ -f "$f" ] && mv "$f" archive/old_stack/ && echo "   → $f"
done

echo "── ①-b 미사용 변형본 보관 ──"
mkdir -p archive/unused
for f in g1_P_A_action.py g1_pose_action_fingerheart3.py g1_voice_action.py; do
    [ -f "$f" ] && mv "$f" archive/unused/ && echo "   → $f"
done

echo "── ①-c 문서 → docs/ ──"
mkdir -p docs
for f in OVERVIEW.md PROGRESS.md NAV2_GUIDE.md SETUP.md POSE_GUIDE.md \
         CAMERA_SETUP.md SDK_API.md MOUNT_GUIDE.md ODOM_B_GUIDE.md \
         RELAY_GUIDE.md camera_task.md depth_camera.md; do
    [ -f "$f" ] && mv "$f" docs/ && echo "   → docs/$f"
done
# README 와 SESSION 일지 2개는 루트 유지

echo "── ② 로그를 깃에서 제외 ──"
grep -qx "logs/" .gitignore || echo "logs/" >> .gitignore
git rm -r --cached logs 2>/dev/null || true

echo "── ③ 루트 지도 사본 동기화 (저장소 등재용) ──"
cp maps/lab_2d.pgm  lab_2d.pgm
cp maps/lab_2d.yaml lab_2d.yaml

echo "── ④ 캐시 삭제 ──"
rm -rf __pycache__

echo ""
echo "완료. 남은 절차:"
echo "   git add -A"
echo "   git commit  (메시지는 SESSION_2026-08-25.md 하단 참고)"
echo "   git push"
