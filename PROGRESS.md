# PROGRESS — 진행 상황

마지막 갱신: 2026-08-22

## 데모 시나리오 (B조 공식)

| 단계 | 내용 |
|---|---|
| 1 | G1 기본 기능 및 상태 전이 확인 |
| 2 | LiDAR 시각화 및 기본 보행 |
| 3 | 사전 생성 SLAM 지도 기반 Nav 자율주행 (3층 복도) |
| 4 | MediaPipe Pose 기반 사람 행동 인식 및 대응 동작 |

**3단계와 4단계는 동시에 수행하지 않는다.** 각각 독립된 단계로 시연한다.
4단계는 모방이 아니라 **미리 정의된 동작 대응**이다.

## 단계별 현황

| 단계 | 내용 | 상태 |
|---|---|---|
| 1 | 댐핑 → 기립 → 레귤러 모드 → 상체 동작 | ✅ 실기체 검증 완료 |
| 2 | 보행 (전진 / 회전 / 정지) | ❌ **미검증** |
| 3 | 보행 + 상체 동작 혼합 | ❌ 미착수 |
| 4 | 센서 시각화 (LiDAR → RViz2) | ✅ 완료 |
| 확장 | 3D SLAM (FAST-LIO) | ✅ 동작 확인, 맵 저장까지 |
| 확장 | `/cmd_vel` 브리지 | ✅ 로봇이 ROS 명령으로 걷는 것 확인 |
| 확장 | 2D SLAM (slam_toolbox) | ✅ 지도 생성 확인 |
| 확장 | **Nav2 자율주행** | 진행 중 — 좋은 2D 지도 확보가 관건 |
| 확장 | RealSense 카메라 연결 | ✅ MJPEG 스트리밍으로 PC 에서 영상 수신 |
| 확장 | MediaPipe 자세 인식 → 팔 동작 | ✅ 동작 확인 |

원래 목표였던 4단계를 넘어 SLAM 까지 왔지만, **2단계 보행이 비어 있다.**
SLAM 데모에서 로봇이 실제로 걸으려면 이것이 선행되어야 하고,
보행 진동으로 맵 품질이 달라지므로 SLAM 튜닝도 그 뒤에 하는 것이 순서다.

---

## Nav2 구조 — 2단계 방식

주행 중에 지도까지 만드는 방식(SLAM + Nav2 동시)은 휴머노이드에서 불안정했다.
보행 진동으로 지도와 위치가 동시에 흔들려 로봇이 엉뚱한 방향으로 갔다.

그래서 **지도 작성과 주행을 분리**한다.

```
1단계) slam_toolbox 로 2D 지도를 만들어 저장       (루프 클로저 O)
2단계) 그 지도를 고정하고 AMCL 이 위치만 찾는다     (오차 누적 X)
```

역할 분담:

| | 역할 |
|---|---|
| FAST-LIO | 오도메트리 (단기 정확, 장기 드리프트) |
| slam_toolbox | 지도 작성 + **루프 클로저**로 드리프트 보정 |
| AMCL | 주행 시 고정 지도에 스캔을 맞춰 위치 확정 |
| Nav2 | 경로 계획 → `/cmd_vel` |
| `g1_cmdvel_bridge.py` | `/cmd_vel` → `SetVelocity()` → 로봇 |

실행 순서는 `NAV2_GUIDE.md` 참고.

### 카메라·자세 인식 확정값

- **ROS 를 쓰지 않는다.** Jetson(Foxy 2020)과 PC(Jazzy 2024)를 같은 도메인에
  두면 `Deserialization of data failed → std::bad_alloc` 으로 카메라 노드가
  죽는다. **토픽 이름은 보이지만 데이터는 못 주고받는다.**
  → Jetson 이 MJPEG(HTTP 8080)으로 영상만 넘기고 PC 가 인식한다
- **MediaPipe 는 aarch64 에 설치가 어렵다.** 공식 wheel 이 x86_64 와
  라즈베리파이용뿐이다. PC(x86_64)에서는 `pip install` 한 줄
- **`mediapipe==0.10.14` 로 버전을 못 박는다.** 최신 1.0.x 에는
  `mp.solutions` 가 없다(Tasks API 로 이전)
- Jetson 은 유선(eth0)으로 인터넷이 안 된다. **내장 WiFi(wlan0)** 를 쓰면
  `git clone`·`apt` 가 된다. 단 **ROS 2 Foxy 저장소는 EOL 로 404** 라
  `ros-foxy-*` 패키지는 못 받고 소스 빌드로만 가능
- `librealsense v2.55.1`, `realsense-ros ros2-legacy` 브랜치
- RealSense 는 `/dev/video*` 를 여러 개 만든다. 컬러는 하나뿐이고
  나머지는 깊이·적외선이다. `g1_cam_server.py` 가 자동 판별한다
- 팔 액션은 **FSM 501** 에서만 동작. 200 이면 `code=7404` 거부

### Nav2 관련 확정값

- **`slam_toolbox` 는 라이프사이클 노드다.** 프로세스가 떠도 그것만으로는
  동작하지 않는다 — `lifecycle_manager` 로 activate 해야 `/scan` 을 구독하고
  `/map` 을 발행한다. **안 하면 에러 없이 아무 일도 안 일어난다.**
- **`navigation_launch.py` 는 우리가 안 쓰는 노드까지 전부 띄운다.**
  (`docking_server`, `route_server`, `waypoint_follower`, `collision_monitor`,
  `smoother_server`) 하나라도 설정이 없으면 `lifecycle_manager` 가
  "Failed to bring up all requested nodes" 로 **전체를 중단시킨다.**
  `nav2_g1_localize.yaml` 에 더미 설정을 넣어 해결.
- **rclpy 와 Unitree SDK 를 한 프로세스에서 쓰려면** `RMW_IMPLEMENTATION=rmw_fastrtps_cpp`.
  ROS 2 가 CycloneDDS 대신 FastDDS 를 쓰게 해서 SDK 것과의 충돌을 피한다.
- 브리지에도 데드맨을 넣었다. `/cmd_vel` 이 0.5초 이상 안 오면 자동 정지.
  **브리지 터미널 `Ctrl+C` 가 소프트웨어 비상 정지다.**

## 확정값 — 문서에 없어 실측으로 알아낸 것들

### FSM 전이 사슬

```
0 (전원 인가) → 1 Damp → 4 Lock Stand → 501 레귤러 모드
```

| FSM | 가능한 것 |
|---|---|
| 4 Lock Stand | 서 있기만 (관절 잠금) |
| 200 MainControl | 보행만. **팔 액션은 code=7404 거부** |
| **501 레귤러** | **보행 + 팔 액션 모두** |
| 500 Start | 이 기체에서는 전이 자체가 안 됨 |

- **4 와 501 은 SDK 에 래퍼가 없다** → `SetFsmId()` 를 직접 호출
- `Damp()`/`Start()` 등 래퍼는 **반환값이 없어**(None) 거부를 놓친다
- 반환 코드 0 이 전이 성공을 뜻하지 않는다 — `GetFsmId()` 로 확인하되
  최종 판정은 육안
- 706(`Squat2StandUp`)은 Damp 직후 거부됨. 기립 경로는 4 다

### LiDAR = MID-360s (일반 MID-360 아님)

- `MID360s_config.json` + `rviz_MID360s_launch.py` (SLAM 용은 `msg_` 쪽)
- **구분법**: `host_net_info` 가 배열이면 s, 객체(IP 4개)면 일반
- 잘못 쓰면 `Init lds lidar success!` 까지만 찍히고 조용히 멈춘다
- `lidar_type: 8` 은 프로토콜 인덱스다. 장치 타입이 아니므로 수정 금지
- `roll: 180` — 거꾸로 장착. **방향 보정은 여기서만 한다**

### 환경 우회

| 문제 | 해결 |
|---|---|
| `buffer overflow detected` (DDS 초기화) | `CYCLONEDDS_URI` 로 인터페이스 지정, 인자로 넘기지 않음 |
| ROS 2 와 SDK 의 cyclonedds 버전 충돌 | 터미널 분리 (`g1` / `lidar` 를 같은 셸에서 쓰지 않음) |
| FAST-LIO Jazzy 빌드 실패 | `CMakeLists.txt` 의 C++14 → 17 |
| 무선에서 LiDAR 데이터 0 패킷 | USB-이더넷 어댑터로 유선 전환 |

### TTS

한국어 미지원, 영어도 부정확 → **로봇 내장 음성**을 쓰고 스크립트는 LED 만 제어.

---

## 네트워크

| 주소 | 장치 | 비고 |
|---|---|---|
| `192.168.123.51` | **우리 PC** | 유선 고정 (USB-이더넷) |
| `192.168.123.120` | LiDAR (MID-360s) | |
| `192.168.123.161` | 운동제어 유닛 (PC1) | |
| `192.168.123.164` | Jetson (PC2) | `unitree`/`123`, Ubuntu 20.04 + Foxy |

**PC 는 Jazzy, Jetson 은 Foxy** — 깊이 카메라를 붙일 때 배포판 차이가 변수다.

---

## 별칭 (`~/.bashrc`)

```bash
alias g1='source ~/g1_real/g1_env.sh'
alias lidar='source /opt/ros/jazzy/setup.bash && source ~/ws_livox/install/setup.sh && cd ~/ws_livox/src/livox_ros_driver2'
alias slam='source /opt/ros/jazzy/setup.bash && source ~/ws_livox/install/setup.sh && source ~/ws_fastlio/install/setup.bash'
alias savemap='ros2 service call /map_save std_srvs/srv/Trigger'
alias g1ros='source ~/g1_real/g1_env.sh; export RMW_IMPLEMENTATION=rmw_fastrtps_cpp; source /opt/ros/jazzy/setup.bash'
```

`g1ros` 는 브리지 전용이다 — venv 와 ROS 를 한 셸에 넣되 RMW 를 FastDDS 로
바꿔 DDS 충돌을 피한다. **RMW export 가 빠지면 첫날처럼 크래시난다.**

`slam` / `lidar` 에도 `export RMW_IMPLEMENTATION=rmw_fastrtps_cpp` 를
넣어 두는 편이 좋다 — 토픽을 주고받는 모든 노드가 같은 RMW 여야 한다.

**`g1` 과 `lidar` 를 같은 터미널에서 쓰지 않는다.**

---

## 자주 쓰는 실행

### 1단계 — 기립 + 상체

```bash
g1
python3 g1_stand_test.py --iface $G1_IFACE          # 전이만
python3 g1_stand_test.py --iface $G1_IFACE --with-arm
python3 g1_real_sequence.py --iface $G1_IFACE --arm-only
```

### 3D SLAM

```bash
# 터미널 1
lidar
ros2 launch livox_ros_driver2 msg_MID360s_launch.py

# 터미널 2
slam
ros2 launch fast_lio mapping.launch.py config_file:=mid360s.yaml

# 터미널 3 — 맵이 잘 나왔을 때
slam
savemap        # → ~/g1_real/maps/lab.pcd
```

맵 확인:

```bash
pcl_viewer ~/g1_real/maps/lab.pcd
```

### 2D 지도 작성 (Nav2 용)

```bash
# 터미널 1  g1     → python3 g1_stand_test.py --iface $G1_IFACE
# 터미널 2  lidar  → ros2 launch livox_ros_driver2 msg_MID360s_launch.py
# 터미널 3  slam   → ros2 launch fast_lio mapping.launch.py config_file:=mid360s_mapping.yaml
# 터미널 4  slam   → ros2 launch /home/hong/g1_real/g1_mapping_2d.launch.py
# 터미널 5  조이스틱으로 조종 (회전은 원호로, 출발점 복귀)

ros2 run nav2_map_server map_saver_cli -f ~/g1_real/maps/lab_2d
```

### Nav2 자율주행

```bash
# 터미널 1  g1     → python3 g1_stand_test.py --iface $G1_IFACE
# 터미널 2  lidar  → ros2 launch livox_ros_driver2 msg_MID360s_launch.py
# 터미널 3  slam   → ros2 launch fast_lio mapping.launch.py config_file:=mid360s.yaml
# 터미널 4  g1ros  → python3 ~/g1_real/g1_cmdvel_bridge.py --iface $G1_IFACE
# 터미널 5  slam   → ros2 launch /home/hong/g1_real/g1_nav2_localize.launch.py

# RViz 에서 2D Pose Estimate 로 초기 위치 지정 → 2D Goal Pose 로 목표
```

**브리지 터미널 `Ctrl+C` 가 비상 정지다.**

### 4단계 — 자세 인식 → 팔 동작

```bash
# 터미널 1  Jetson  → ssh unitree@192.168.123.164 ; python3 g1_cam_server.py
# 터미널 2  g1      → python3 g1_stand_test.py --iface $G1_IFACE
# 터미널 3  g1      → python3 ~/g1_real/g1_pose_action.py --dry-run   # 인식만
#                    python3 ~/g1_real/g1_pose_action.py --iface $G1_IFACE
```

영상 확인: 브라우저에서 `http://192.168.123.164:8080`
자세한 내용은 `POSE_GUIDE.md`.

**종료는 `Ctrl+C`.** `Ctrl+Z` 는 프로세스를 백그라운드에 남겨 포트를 점유하므로
다음 실행이 조용히 실패한다.

---

## 다음에 할 것

**우선순위 순.**

1. **좋은 2D 지도 확보** — 회전을 원호로, 출발점 복귀로 루프 클로저 유도.
   여러 번 시도해 제일 나은 것을 쓴다
2. **Nav2 주행 검증** — 초기 위치 지정 후 2~3m 직선 목표부터
3. **보행 + 상체 (3단계)** — `SEQUENCE` 에 `move`/`stop` 행 추가,
   `--enable-walk` 로 실행
4. 팔 액션 22개 순회 확인 — `g1_arm_probe.py --tour`
5. **카메라** — Jetson USB 에 안 잡히는 원인 파악(케이블/미장착).
   최악의 경우 USB 웹캠을 로봇에 장착하고 **PC 에 직접 연결**하면
   Jetson 배포판 문제를 통째로 우회할 수 있다
6. 왼손 "흔들기" 판별 정교화 (현재는 "든 상태"로 단순화)

---

## 미해결 / 확인 필요

- FAST-LIO 는 **루프 클로저가 없다.** 한 바퀴 돌아와도 드리프트 보정 불가.
  넓은 공간에서 필요해지면 FAST-LIO-SAM 계열 검토
- IMU 가속도가 **g 단위**로 들어온다(`z ≈ -0.99`). 현재는 FAST-LIO 가
  초기화 때 정규화해 문제없지만, 맵이 이상하면 의심할 지점
- `SetTaskId(99)` 가 loco 쪽 팔 제어 해제인지 **미검증** (추정값)
- 댄스 모션 4종(`Waist_Drum_Dance` 등)은 `GetActionList` 에 이름만 있고
  ID 가 없다 — 호출 방법 미확인
- 기립 완료 시 관측 FSM 값이 조회마다 흔들린 적이 있다(통신 품질).
  유선 전환 후 개선됨
- Jetson 카메라는 **케이블이 안 꽂혀 있던 것**이었다. USB 3.0 포트(Bus 002)에
  꽂아야 한다 — 2.0 에 꽂으면 대역폭이 부족하다
- Nav2 주행 시 위치가 튀는 현상. 지도/주행의 스캔 높이 구간이 달랐던 것이
  한 원인 — 양쪽 `min_height`/`max_height` 를 맞출 것
