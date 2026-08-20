# PROGRESS — 진행 상황

마지막 갱신: 2026-08-20

## 단계별 현황

| 단계 | 내용 | 상태 |
|---|---|---|
| 1 | 댐핑 → 기립 → 레귤러 모드 → 상체 동작 | ✅ 실기체 검증 완료 |
| 2 | 보행 (전진 / 회전 / 정지) | ❌ **미검증** |
| 3 | 보행 + 상체 동작 혼합 | ❌ 미착수 |
| 4 | 센서 시각화 (LiDAR → RViz2) | ✅ 완료 |
| 확장 | 3D SLAM (FAST-LIO) | ✅ 동작 확인, 맵 저장까지 |
| 확장 | 깊이 카메라 (RealSense) | ❌ 미착수 |
| 확장 | Nav2 자율주행 | ❌ 미착수 |

원래 목표였던 4단계를 넘어 SLAM 까지 왔지만, **2단계 보행이 비어 있다.**
SLAM 데모에서 로봇이 실제로 걸으려면 이것이 선행되어야 하고,
보행 진동으로 맵 품질이 달라지므로 SLAM 튜닝도 그 뒤에 하는 것이 순서다.

---

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
```

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

**종료는 `Ctrl+C`.** `Ctrl+Z` 는 프로세스를 백그라운드에 남겨 포트를 점유하므로
다음 실행이 조용히 실패한다.

---

## 다음에 할 것

**우선순위 순.**

1. **보행 검증 (2단계)** — `g1_walk_test.py --vx 0.2 --sec 3` 부터.
   행어 · 진행 방향 공간 · 리모컨 대기 확인 후.
2. **보행 + 상체 (3단계)** — 검증 후 `SEQUENCE` 에 `move`/`stop` 행 추가,
   `--enable-walk` 로 실행
3. **걸으면서 SLAM** — 보행 진동 조건에서 맵 품질 재확인·재튜닝
4. 팔 액션 22개 순회 확인 — `g1_arm_probe.py --tour`
5. 깊이 카메라 — Jetson 에서 노드 실행 후 PC 에서 구독.
   `ROS_DOMAIN_ID`(현재 33) 와 RMW 를 양쪽에서 맞춰야 함
6. Nav2 — 별도 프로젝트 규모

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
