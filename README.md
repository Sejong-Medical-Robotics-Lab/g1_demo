# G1 실기체 데모 — 파일 구성

로봇 연결 전에 준비한 파일들. `~/g1_real/` 에 두고 사용한다.

## 파일

| 파일 | 단계 | 역할 |
|---|---|---|
| `g1_env.sh` | 전체 | 터미널 준비 (venv + CYCLONEDDS_HOME + 인터페이스 자동 탐지) |
| `g1_common.py` | 전체 | 공통 래퍼 — FSM 전이·보행·팔 반납, 반환코드 검사 |
| `g1_stand_test.py` | 1 | Damp → 기립 → 균형 제어 단독 검증 |
| `g1_walk_test.py` | 2 | 보행 단독 검증 (데드맨 방식) |
| `g1_real_sequence.py` | 2·3 | 주 실행 파일 — 전이 + 상체 + (검증 후) 보행 |
| `g1_imu_view.py` | 전체 | 내장 IMU 실시간 확인 (읽기 전용) |
| `g1_audio_test.py` | 전체 | 스피커(TTS)·LED 확인 — 관절 명령 없음 |
| `g1_real_monitor.py` | 전체 | 기존 모니터 (precheck / baseline / watch) |
| `g1_fsm_probe.py` | 1 | FSM 번호를 하나씩 보내 전이 사슬을 실측 |
| `g1_arm_probe.py` | 1·2 | 팔 액션 진단 · 순회(`--tour`) |
| `g1_cam_server.py` | 4 | **Jetson 에 두고 실행** — RealSense → MJPEG 스트리밍 |
| `g1_pose_action.py` | 4 | **PC** — MediaPipe 자세 인식 → G1 팔 동작 |
| `g1_mapping_2d.launch.py` | Nav2 | **2D 지도 작성** (slam_toolbox + 루프 클로저) |
| `g1_nav2_localize.launch.py` | Nav2 | **자율주행** (고정 지도 + AMCL) |
| `nav2_g1_localize.yaml` | Nav2 | Nav2 + AMCL 파라미터 |
| `g1_mapping.rviz` | Nav2 | 지도 작성용 RViz 설정 |
| `g1_slam.launch.py` | — | (구) 오도메트리 없는 2D SLAM — 참고용 |
| `g1_nav2.launch.py` | — | (구) 지도 없이 주행 — 참고용 | 
| `g1_pose_action.py` | 4 | pose로 모션제어 |
| `g1_voice_action.py`| 4 | voice로 모션제어 |
| `g1_P_A_action.py`| 4 | pose와 voice 병합 |

문서: [PROGRESS.md](PROGRESS.md) 진행 상황·확정값 · [NAV2_GUIDE.md](NAV2_GUIDE.md) Nav2 실행 순서 ·
[POSE_GUIDE.md](POSE_GUIDE.md) 자세 인식 실행 순서 · [CAMERA_SETUP.md](CAMERA_SETUP.md) 카메라 연결 기록 ·
[SETUP.md](SETUP.md) 환경 구축 · [SDK_API.md](SDK_API.md) SDK 레퍼런스 ·
[OVERVIEW.md](OVERVIEW.md) 전체 개념과 흐름

## 터미널 구성

**터미널 A — 제어 (venv)**
```bash
source ~/g1_real/g1_env.sh
python3 ~/g1_real/g1_stand_test.py --iface $G1_IFACE
```

**터미널 B — 모니터 (venv)**
```bash
source ~/g1_real/g1_env.sh
python3 ~/g1_real/g1_real_monitor.py watch --iface $G1_IFACE
```

**터미널 C — LiDAR (venv 와 섞지 말 것)**
```bash
lidar
ros2 launch livox_ros_driver2 msg_MID360s_launch.py
```

**터미널 D — 3D SLAM**
```bash
slam
ros2 launch fast_lio mapping.launch.py config_file:=mid360s.yaml
```

## 진행 순서

```
1단계  g1_stand_test.py --dry-run          # 로봇 없이 계획 확인
       g1_stand_test.py --iface … --list-actions
       g1_stand_test.py --iface …          # 전이만
       g1_stand_test.py --iface … --with-arm
         ↓  관측 FSM 값을 TRANSITIONS 에 반영
2단계  g1_real_sequence.py --dry-run
       g1_real_sequence.py --iface … --operator 이름
         ↓
3단계  g1_walk_test.py --iface … --vx 0.2 --sec 3
       g1_walk_test.py --iface … --preset forward_stop_turn
         ↓
4단계  SEQUENCE 에 move/stop 행 추가
       g1_real_sequence.py --iface … --enable-walk
         ↓
5단계  g1_imu_view.py → LiDAR(RViz2) → 깊이 카메라(Jetson 경유)
```

## 원본에서 바꾼 것 (`g1_real_sequence.py`)

1. **전이가 실패해도 못 잡던 문제 수정.**
   `LocoClient.Damp()/Start()/Squat2StandUp()` 은 내부에서 `SetFsmId()` 를 부르지만
   **반환값이 없다(None).** 원본의 `check_code(self.loco.Damp(), ...)` 는 항상 통과했다.
   `TRANSITIONS` 를 메서드명 대신 FSM ID 로 바꾸고 `SetFsmId()` 를 직접 호출해
   반환 코드를 검사한다.

2. **`706` 토글 경고 명시.**
   `Squat2StandUp` 과 `StandUp2Squat` 은 **같은 ID(706)** 다. 이미 서 있는 상태에서
   다시 보내면 앉는다.

3. **팔 액션 뒤 `release arm`(ID 99) 자동 전송.** 보행 전·시퀀스 종료 전에도 호출.

4. **`move` / `stop` 행 지원** — 단, `--enable-walk` 없이는 거부된다.
   속도는 안전 상한(`vx 0.3 / vy 0.2 / vyaw 0.4`)으로 자동 clamp.

5. **`safe_damp` 에 `stop_move` + `release_arm` 선행.**

## 보행 데드맨 (중요)

`Move()` 를 쓰지 않는다.

- `Move(vx,vy,vyaw)` = `SetVelocity(..., duration=1)` → 1초만 걷고 멈춤
- `Move(..., continous_move=True)` = **duration 864000초(10일)** → 스크립트가 죽어도 계속 걸음

대신 `SetVelocity(vx, vy, vyaw, duration=0.5)` 를 **0.2초 주기로 재전송**한다.
프로세스가 죽거나 통신이 끊기면 0.5초 안에 로봇이 스스로 멈춘다.

## 실기체 확정값 (2026-08 실측)

| 항목 | 값 |
|---|---|
| 전이 사슬 | `0(전원) → 1 Damp → 4 Lock Stand → 501 레귤러 모드` |
| **레귤러 모드** | **FSM 501** — 보행 + 팔 액션이 모두 되는 상태 |
| FSM 200 | 보행은 되지만 **팔 액션은 거부(code=7404)** |
| `Start()` (=500) | **통하지 않음** — 전이 자체가 안 된다 |
| `Squat2StandUp()` (=706) | Damp 직후 거부됨 — 기립 경로는 4 |
| Lock Stand(4) | SDK 에 래퍼 없음 — `SetFsmId(4)` 직접 호출 |
| TTS | 한국어 미지원, 영어도 부정확 → **로봇 내장 음성 사용** |

### FSM 200 vs 501 — 7404 의 원인

`GetActionList` 응답을 보면 각 액션에 실행 조건이 붙어 있다:

```
{'fsm': [500, 501], 'id': 1, 'name': 'turn_back_wave'}
{'id': 20, 'mode_machine': [5, 6], 'name': 'make_heart_with_both_hands'}
```

팔 액션은 501 을 요구한다. FSM 200 에서 `ExecuteAction` 을 부르면
**code=7404** 로 거부된다 — arm 서비스가 죽은 것이 아니라 상태가 안 맞는 것이다
(`GetActionList` 자체는 200 에서도 code=0 으로 정상 응답한다).

### GetActionList 가 SDK action_map 보다 많다

실기체는 SDK 에 없는 액션도 보고한다:

| ID | 이름 |
|---|---|
| 28~30 | box_left/right/both_hand_win |
| 33 | right_hand_on_heart |
| 34 | both_hands_up_deviate_right |
| 36 | forward_push |

두 번째 배열은 댄스 모션이다 — `Waist_Drum_Dance`(9.5s), `Scratch_head`(8.1s),
`Spin_discs`(6.9s), `Throw_money`(8.1s). 데모에 쓸 수 있다.

## 음성 · LED (`--audio`)

`AudioClient` 로 TTS 와 RGB LED 를 제어한다. **오디오는 실패해도 제어 흐름을
막지 않는다** — 초기화나 호출이 실패하면 경고만 찍고 조용히 넘어간다.

```bash
python3 g1_audio_test.py --iface $G1_IFACE          # 먼저 단독 확인
python3 g1_stand_test.py --iface $G1_IFACE --audio
python3 g1_real_sequence.py --iface $G1_IFACE --operator 이름 --audio
```

LED 색 규약:

| 색 | 상태 |
|---|---|
| 빨강 | Damp / 이상·중단 |
| 주황 | 기립 전이 중 |
| 초록 | 균형 제어(정상) |
| 파랑 | 상체 동작 중 |
| 보라 | 보행 중 |

**우리 TTS 는 기본으로 꺼져 있다.** 실기체에서 한국어는 재생되지 않고 영어도
발음이 부정확했다. 모드 전환 안내는 **로봇 자체 내장 음성**(레디/레귤러 등)에
맡기고, 스크립트는 LED 색만 바꾼다.

굳이 우리 문구를 읽히려면 `--tts` 를 준다(중국어는 정상 동작).
`g1_audio_test.py` 로 언어별 재생을 다시 확인할 수 있다.

**SDK 버그 우회:** `AudioClient.TtsMaker()` 안의 `tts_index += tts_index` 는
0 에서 시작해 영원히 0 이다(증가하지 않음). `tts_index = 1` 로 초기화해 두었다.

## CYCLONEDDS_URI 우회 (Ubuntu 24.04 필수)

`ChannelFactoryInitialize(domain, iface)` 처럼 **인터페이스 이름을 인자로 넘기면
C 레벨에서 죽는다** — `*** buffer overflow detected ***`.

원인: SDK 가 인터페이스 이름을 받았을 때 만드는 설정 XML
(`unitree_sdk2py/core/channel_config.py` 의 `ChannelConfigHasInterface`)에만
`<Tracing><OutputFile>/tmp/cdds.LOG</OutputFile></Tracing>` 블록이 있다.
인터페이스 없이 호출하는 `ChannelConfigAutoDetermine` 에는 이 블록이 없어서
정상 동작한다.

그래서 이 저장소의 스크립트는 **`CYCLONEDDS_URI` 가 설정되어 있으면 인터페이스
인자를 넘기지 않는다.** `g1_env.sh` 가 `G1_IFACE` 를 찾아 자동으로 export 한다.

```bash
g1                      # CYCLONEDDS_URI : 설정됨 (interface=...) 이 뜨면 정상
python3 g1_imu_view.py  # --iface 생략 가능
```

수동으로 지정하려면:

```bash
export CYCLONEDDS_URI='<CycloneDDS><Domain id="any"><General><Interfaces><NetworkInterface name="wlo1" priority="default" multicast="default"/></Interfaces></General></Domain></CycloneDDS>'
```

### ROS 2 와 같은 터미널을 쓰지 말 것

ROS 2 Jazzy 는 cyclonedds 0.10.4, Unitree SDK 는 0.10.2 를 쓴다. ROS 를 source 한
셸에서는 라이브러리가 섞여 같은 크래시가 난다. `~/.bashrc` 에서 ROS 워크스페이스
`setup.bash` 들을 모두 주석 처리하고, ROS 가 필요한 터미널에서만 직접 source 한다.
(워크스페이스 `setup.bash` 는 내부에서 기반 ROS 환경까지 불러오므로
`/opt/ros/jazzy` 줄만 막는 것으로는 부족하다.)

```bash
echo "[$ROS_DISTRO]"    # 제어 터미널에서는 [] 여야 한다
```

## 4단계 — 사람 자세 인식 → G1 대응 동작

**ROS 를 쓰지 않는다.** Jetson(Foxy)과 PC(Jazzy)는 DDS 규약이 달라 같은
도메인에 두면 노드가 죽는다. 영상만 HTTP 로 넘기고 인식은 PC 가 한다.

```
[Jetson] 카메라 → MJPEG (8080)  →  [PC] MediaPipe → 판별 → SDK → G1 팔
```

```bash
# Jetson
python3 g1_cam_server.py                    # 영상 확인: http://192.168.123.164:8080

# PC (로봇을 FSM 501 로 올린 뒤)
pip install "mediapipe==0.10.14"            # ★ 최신 1.0.x 에는 mp.solutions 가 없다
python3 ~/g1_real/g1_pose_action.py --dry-run          # 인식만
python3 ~/g1_real/g1_pose_action.py --iface $G1_IFACE  # 실전
```

| 사람 | G1 |
|---|---|
| 오른손 올림 | 오른손 올리기 (23) |
| 왼손 올림 | 손 흔들기 (26) |
| 양손 올림 | 양팔 올리기 (15) |

자세한 순서는 [POSE_GUIDE.md](POSE_GUIDE.md).

## Nav2 자율주행

주행 중에 지도까지 만들면 보행 진동으로 위치가 흔들려 로봇이 엉뚱한 곳으로
간다. **지도 작성과 주행을 분리**한다.

```
1단계) slam_toolbox 로 2D 지도 작성 → 저장   (루프 클로저로 오차 보정)
2단계) 그 지도를 고정하고 AMCL 로 위치 추정   (오차 누적 없음)
```

```bash
# 지도 작성
ros2 launch /home/hong/g1_real/g1_mapping_2d.launch.py
ros2 run nav2_map_server map_saver_cli -f ~/g1_real/maps/lab_2d

# 자율주행 (브리지를 먼저 띄운 뒤)
ros2 launch /home/hong/g1_real/g1_nav2_localize.launch.py
```

**RViz 에서 `2D Pose Estimate` 로 초기 위치를 반드시 찍는다.**
**브리지 터미널 `Ctrl+C` 가 비상 정지다.**

자세한 순서는 [NAV2_GUIDE.md](NAV2_GUIDE.md).

## 3D SLAM — FAST-LIO

MID-360s 포인트 + 내장 IMU 로 오도메트리를 스스로 만들어낸다. G1 의 보행
오도메트리 없이도 위치 추정이 되므로 휴머노이드에 적합하다.

```bash
# 터미널 C
lidar
ros2 launch livox_ros_driver2 msg_MID360s_launch.py    # ← msg_ (CustomMsg)

# 터미널 D
slam
ros2 launch fast_lio mapping.launch.py config_file:=mid360s.yaml
```

핵심 세 가지:

- **Jazzy 빌드는 C++17 로 올려야 한다** — 저장소가 C++14 기준이라 `rclcpp` 와 충돌
- **입력은 CustomMsg** — `rviz_` 가 아니라 **`msg_`** launch 를 쓴다
- **방향 보정은 드라이버 `roll: 180` 에서만** — FAST-LIO 의 `extrinsic_R` 로는
  맵 방향이 바뀌지 않는다

방향 확인은 **팔을 흔들어서** 한다. 위로 올렸을 때 맵에서도 위로 그려지면 맞다.
RViz 화면의 좌우로 판단하면 카메라 위치 때문에 거울처럼 뒤집혀 보인다.

자세한 내용은 [SETUP.md](SETUP.md) 6장.

## LiDAR — MID-360s 다

이 기체의 LiDAR 는 일반 MID-360 이 **아니라 MID-360s** 다. 설정 파일과 launch
파일이 서로 다르고, 잘못 쓰면 드라이버가 `Init lds lidar success!` 까지만 찍고
조용히 멈춘다(RViz 비어 있음).

```bash
ros2 launch livox_ros_driver2 rviz_MID360s_launch.py     # ← s 가 붙는다
```

확정값: LiDAR `192.168.123.120` / 호스트 `192.168.123.51` / `roll: 180`(거꾸로 장착)
/ `lidar_type: 8` 고정(프로토콜 인덱스, 수정 금지).
자세한 내용과 문제 해결 순서는 [SETUP.md](SETUP.md) 5장.

| 토픽 | 주파수 |
|---|---|
| `/livox/lidar` (PointCloud2) | 10 Hz |
| `/livox/imu` | 200 Hz |

## 로봇 연결 후 확정해야 할 값

- [ ] 기립 완료 시 실제 FSM 관측값 (`4` 인지 `706` 인지)
- [ ] 균형 제어 진입 시 실제 FSM 관측값 (`500` 인지 `200` 인지)
- [ ] `GetActionList` 실기체 응답 ↔ SDK `action_map` 대조
- [ ] 관절 수 (`g1_real_monitor.py --joints`, 기본 29)
- [x] LiDAR IP → `192.168.123.120`, 모델 → **MID-360s**
- [x] Jetson(`192.168.123.164`) → Ubuntu 20.04 + ROS Foxy
- [x] TTS → 한국어 미지원, 영어도 부정확 → 로봇 내장 음성 사용
- [x] 3D SLAM (FAST-LIO) 동작 확인 — 정지 상태 맵 생성까지
- [ ] 보행하면서 맵이 확장되는지 (2단계 보행 검증이 선행되어야 함)
- [ ] 깊이 카메라(RealSense) — Jetson 쪽 노드 실행 후 PC 에서 구독, 미검증
