# 로봇 듣기 최종 구조 — ROS C-계층 tap + UDP relay

## 결론까지의 실험 기록 (2026-08-25)

| 시도 | 결과 |
|---|---|
| 파이썬 바인딩 0.10.x (3.12/3.11, 소스빌드) | 구독자 생성 크래시 — **로컬 libddsc 빌드 불량이 공통 원인** |
| 파이썬 바인딩 11.0.1 (깨끗한 조립휠) | 루프백 OK, 그러나 로봇 세대(0.10)와 짝맺기 불가 |
| PyPI 의 3.11용 0.10.x 조립휠 | 존재하지 않음 (11.0.1 뿐) |

→ 파이썬 바인딩 경로 폐기. **배포판이 제대로 조립한 ROS 의
CycloneDDS C 계층**으로 로봇을 직접 듣는다 (erasers 실전 방식).

```
[tapenv 터미널]      g1_odom_tap_ros.py   로봇 ROS 토픽 구독 → UDP:17777
[평소 터미널(ROS)]   g1_odom_relay.py     UDP → /odom + TF(odom→base_link)
```

tap 터미널만 CycloneDDS 로 돌고(로봇과 같은 세대), 평소
스택(FastDDS)은 무손상 — 둘 사이는 UDP 라 RMW 혼용 문제 없음.
(venv311/venv_dds/sdk2py tap 은 전부 폐기 — 참고용 보관만)

## 1단계 — 준비 (한 번만, ~10분)

```bash
bash ~/g1_real/ros_tap_setup.sh
```
(rmw-cyclonedds apt 설치 + 유니트리 메시지 정의 빌드 + XML 생성.
 sudo 비번 물어봄)

## 2단계 — 전등 스위치: 로봇이 쏘는 토픽 전부 보기 (로봇 켜고)

```bash
# 새 터미널 (venv 없이!)
source ~/g1_real/tapenv.sh
ros2 topic list | grep -Ei "odom|state|sport|low"
```
**여기서 나오는 목록이 하루 종일 찾던 정답지다.** /odommodestate 가
보이면:
```bash
ros2 topic echo /odommodestate --once     # 실제 값 눈으로 확인
```

## 3단계 — tap + relay 가동 (터미널 2개)

```bash
# 터미널 A (tapenv):
source ~/g1_real/tapenv.sh
python3 ~/g1_real/g1_odom_tap_ros.py

# 터미널 B (평소처럼, venv 없이):
python3 ~/g1_real/g1_odom_relay.py
```
검증: `ros2 topic hz /odom` (평소 터미널에서) — 수십 Hz.
조이스틱으로 1m 걷게 → /odom 의 x 가 ~1.0 변하는지.

## 4단계 — B안 내비 기동 (ODOM_B_GUIDE 나머지 그대로)

라이다 PointCloud2 판 + tap/relay + cmdvel 브리지(g1ros)
+ `ros2 launch ~/g1_real/g1_nav2_odomB.launch.py`
→ 스캔 좌우반전 체크 → 왕복 판정.

## 부록 — 오늘 실험이 남긴 것

- 오디오(TTS) 크래시도 같은 뿌리(0.10.x×3.12 구독 크래시)일 가능성 큼
  → venv311 에서 g1_speak 재생부를 돌려보면 부활할 수 있음 (데모 후)
- venv_dds(11.x)는 "로봇 없는 PC 간 DDS" 용도로만 유효 — 로봇과는 불통
