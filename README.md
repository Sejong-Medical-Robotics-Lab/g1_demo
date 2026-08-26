# G1 실기체 데모 — 실행 코드

Unitree G1 휴머노이드: 기본 제어 · LiDAR · Nav2 자율주행 · MediaPipe
제스처 대응 동작. 세부 개념과 이력은 `docs/`, 날짜별 작업 기록은
`SESSION_*.md`.

## 자율주행 — 현재 표준 (B안: 내장 오도메트리, 2026-08-25 확정)

로봇 내장 오도메트리(51Hz, /state_estimator/odom_pelvis)를 기반으로
AMCL 위치추정 + Nav2 주행. FAST-LIO 는 지도 "제작" 때만 쓴다.

**기동 — 터미널 4+1개:**

| # | 터미널 | 명령 |
|---|---|---|
| 1 | lidar | `ros2 launch livox_ros_driver2 pc2_MID360s_launch.py` |
| 2 | tap ★특수 | `source ~/g1_real/tapenv.sh` → `bash ~/g1_real/run_taps.sh` |
| 3 | 브리지 | `g1ros` → `python3 ~/g1_real/g1_cmdvel_bridge.py --iface $G1_IFACE` |
| 4 | 본체 | `ros2 launch ~/g1_real/g1_nav2_full.launch.py 2>&1 \| tee ~/g1_real/logs/navF_$(date +%H%M%S).log` |
| 5 | 예비 | `set_pose.sh` · `clearmap.sh` |

(본체 = relay 2종 + G1 모형 + Nav2 통합. 모형 제외: `model:=false`)

RViz: 초기위치(안 되면 `set_pose.sh <각도>`) → `clearmap.sh` →
직진(반환점은 벽 1m+) → `clearmap.sh` → 복귀. 추종자는 대각선 측면.
오래 세워뒀다 재개하면 초기위치 재설정(yaw 편류 분당 ~1도).

**규칙:** tapenv 는 2번 터미널 전용(다른 ros2 명령 금지) /
FAST-LIO 는 이 구성에서 띄우지 않음.

## 파일 안내

**자율주행 (B안 스택):**
| 파일 | 역할 |
|---|---|
| `g1_odom_tap_ros.py` | 로봇 내장 오도메트리 구독(CycloneDDS) → UDP |
| `g1_odom_relay.py` | UDP → `/odom` + TF(odom→base_link) |
| `tapenv.sh` / `cyclonedds_g1.xml` / `ros_tap_setup.sh` | tap 환경·셋업 |
| `g1_cmdvel_bridge.py` | `/cmd_vel` → SetVelocity (데드맨·클램프·이중 실행하한 0.10/0.25) |
| `g1_nav2_odomB.launch.py` + `nav2_g1_odomB.yaml` | Nav2 (내장 odom 프레임) |
| `nav.sh` / `set_pose.sh` / `clearmap.sh` | 로그 자동저장 · 초기위치 · costmap 청소 |

**지도 (제작 시에만):** `g1_mapping_2d.launch.py`(slam_toolbox+루프클로저,
FAST-LIO 오도메트리) → `maps/`(로컬), 루트 `lab_2d.*` 는 깃 등재 사본.

**예비 (A안 — FAST-LIO 오도메트리 주행):** `g1_nav2_localize.launch.py`
+ `nav2_g1_localize.yaml` — B 안정화 검증 전까지 보관.

**기본 제어·시연:** `g1_real_sequence.py`(주 실행) · `g1_stand_test.py`
· `g1_fsm_probe.py` · `g1_arm_probe.py` · `g1_walk_test.py` ·
`g1_common.py`(공통 래퍼) · `g1_real_monitor.py` · `g1_imu_view.py`

**제스처 인식 (시연 4):** `g1_cam_server.py`(Jetson, MJPEG) →
`g1_pose_action.py`(PC, MediaPipe→팔 동작)

**기타:** `g1_speak.py`(TTS 합성 — 로봇 재생은 보류, 부활 후보) ·
`g1_audio_test.py` · `g1_env.sh` · `mid360s*.yaml` · `MID360s_config.json`

## 폴더

```
docs/       개념·가이드 문서 (OVERVIEW, SETUP, NAV2/POSE/RELAY/ODOM_B GUIDE …)
maps/       실행용 지도 (깃 제외 — 루트 사본이 등재본)
logs/       실행 로그 (깃 제외, nav.sh 가 자동 기록)
archive/    은퇴 코드 — dds_experiments(규명 실험) · old_stack · unused
```

## 날짜별 기록

- `SESSION_2026-08-24.md` — Nav2 실주행 1일차 (지도·AMCL·데드밴드)
- `SESSION_2026-08-25.md` — 회전 문제 종결 · DDS 규명 · **B안 개통,
  첫 자율 180도 왕복**
