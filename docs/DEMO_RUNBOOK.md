# 데모 운영 대본 (DEMO RUNBOOK)

시연 순서: ①기본 제어 → ②LiDAR → ③자율주행 → ④제스처 대응.
각 시연은 "준비 → 실행 → 성공 확인 → 다음으로 전환"의 4단 구성.
녹화도 이 대본 그대로 진행하면 된다.

---

## 0. 공통 사전 준비 (데모 30분 전)

**하드웨어 체크리스트:**
- [ ] 로봇 배터리 만충 / 조종기 페어링 확인
- [ ] 노트북 **전원 어댑터 연결** (배터리 절전 = action 타임아웃 원흉)
- [ ] 유선 케이블: PC ↔ 로봇 (PC IP 192.168.123.51)
- [ ] 시연 공간: ③용 복도 확보, ④용 시연자 위치(전신 보이는 거리) 바닥 표시

**PC 확인 (아무 터미널):**
```bash
ip addr show | grep 192.168.123          # .51 잡혀 있나
ping -c 2 192.168.123.161                # 로봇 응답
ping -c 2 192.168.123.164                # Jetson 응답 (시연④용)
echo $ROS_DOMAIN_ID                      # 0 (비어있어도 됨)
```

**로봇 기동:** 전원 → 자세 안정 대기 → 조종기로 **Damp** 상태 확인.

**녹화하는 날이면:** 화면 녹화는 시연 직전에 켜기 (B안은 CPU 여유
검증됐지만, 습관적으로 시연 사이에는 끄기).

---

## 시연 ① 기본 제어 — Damp → 기립 → Regular → 상체 동작

**터미널 1개 (g1ros):**
```bash
g1ros
python3 ~/g1_real/g1_real_sequence.py --iface $G1_IFACE
```
스크립트가 단계마다 확인을 물으며 진행: FSM 0→1(Damp)→4(Lock
Stand)→501(Regular) → 상체 액션.

**성공 확인:** ✅ 각 전이마다 코드 0 응답 ✅ 기립 후 균형 유지
✅ 팔 동작 실행

**멘트 포인트:** "501 외 상태에서 팔 명령은 code=7404 로 거부됩니다 —
상태 사슬을 실기체로 검증했습니다."

**전환 → ②:** 로봇은 **501 그대로 유지** (이후 시연 전부 501 기반).
터미널도 그대로 둠 (④에서 재사용).

---

## 시연 ② LiDAR — 실시간 Point Cloud

**터미널 2개:**
```bash
# [lidar]
ros2 launch livox_ros_driver2 pc2_MID360s_launch.py
# ✅ "publish use PointCloud2 format"

# [rviz]
rviz2
```

**RViz 조작 (미리 연습해둘 것, 20초):**
1. Fixed Frame → `livox_frame` 입력
2. Add → By topic → `/livox/lidar` → PointCloud2
3. (보기 좋게) PointCloud2 → Size 0.03, Color Transformer → AxisColor

**성공 확인:** ✅ 복도·사람이 점구름으로 실시간 표시, 손 흔들면 점이
따라 움직임

**멘트 포인트:** "MID-360s, 360도 · 초당 10프레임. 이 원시 데이터가
③의 눈이 됩니다."

**전환 → ③:** **lidar 터미널은 그대로 유지** (③이 이어받음).
rviz 창만 닫기 (③이 자체 RViz를 띄움).

---

## 시연 ③ 자율주행 — B안 (내장 오도메트리 + Nav2)

### 기동 — 터미널 (통합 후 4개)

| # | 터미널 | 명령 | 성공 확인 |
|---|---|---|---|
| 1 | **tap ★** | `source ~/g1_real/tapenv.sh` → `bash ~/g1_real/run_taps.sh` | odom·joint 두 tap 로그 |
| 2 | 브리지 | `g1ros` → `python3 ~/g1_real/g1_cmdvel_bridge.py --iface $G1_IFACE` | 시작 배너 |
| 3 | **본체** | `ros2 launch ~/g1_real/g1_nav2_full.launch.py 2>&1 \| tee ~/g1_real/logs/navF_$(date +%H%M%S).log` | relay 2종 "정상" + **active 2회** + RViz 지도 위 G1 모형 |
| 4 | 예비 | (대기 — set_pose / clearmap) | — |

라이다는? → 본체에 포함 안 됨 — **기존처럼 별도 유지가 안전**하면 5번으로
`ros2 launch livox_ros_driver2 pc2_MID360s_launch.py` (시연②에서 이어짐).
모형 없이 가볍게: 본체에 `model:=false`.

### 주행 절차

1. **초기 위치**: RViz `2D Pose Estimate` — 실제 위치·방향 정확히.
   안 먹으면: 터미널⑥ `bash ~/g1_real/set_pose.sh <각도>` →
   RViz [Publish Point] 로 위치 클릭
2. 터미널⑥: `bash ~/g1_real/clearmap.sh`
3. **직진 목표** `2D Goal Pose` — **흰 자유공간 안쪽만**, 반환점은
   **복도 중앙(벽에서 1m+)**
4. 도착 → `clearmap.sh` → **복귀 목표**
5. 추종자(테더 든 사람)는 **대각선 측면**에서 — 정후방 금지(흔적 잔존)

**성공 확인:** ✅ 걷는 중 빨간 스캔이 지도 벽에 붙어 감 ✅ 180도
회전이 한 방향으로 매끈 ✅ 개입 없이 복귀 완료

**멘트 포인트:** "위치추정은 로봇 내장 오도메트리 51Hz + AMCL 지도
대조의 역할 분담 — 단기는 오도메트리, 장기 오차는 AMCL."

**주의 — 시연이 길어져 로봇을 세워뒀다 재개하면:** yaw 가 분당 ~1도
흘러 있으니 **초기 위치 재설정 후** 새 목표.

**전환 → ④:** 터미널 5(Nav2)만 Ctrl+C (RViz 같이 닫힘, CPU 확보).
1~4번 터미널은 그대로 둬도 무해. 로봇 위치는 그 자리에서 ④ 진행
가능(전신 보일 공간만 확보), 필요하면 조이스틱으로 이동.

---

## 시연 ④ 제스처 인식 → 대응 동작

**터미널 2개:**
```bash
# [jetson] — Jetson 에 접속해 카메라 서버
ssh unitree@192.168.123.164
python3 g1_cam_server.py
# ✅ 확인(선택): PC 브라우저에서 http://192.168.123.164:8080

# [pose] — PC (시연① 터미널 재사용 가능)
g1ros
python3 ~/g1_real/g1_pose_action.py --iface $G1_IFACE
# ✅ 영상 창 + 스켈레톤 표시
```

**시연자 요령 (사전 브리핑 필수):**
- 로봇 **FSM 501** 상태 (①③에서 이어졌으면 OK)
- **전신이 카메라 프레임에** — 바닥 표시 지점에 서기
- 동작을 **1초 유지** ("하나-둘" 세기) — 연속 프레임 판정 때문
- 한 동작 후 **몇 초 대기** (쿨다운) 후 다음 동작
- 인식 동작 5종: 한 손 들기 / 손 흔들기 / 양손 들기 / 키스 / 손가락 하트

**성공 확인:** ✅ 화면에 인식 결과 이름 표시 ✅ G1 이 대응 팔 동작

**멘트 포인트:** "오검출 방지(N프레임 연속+쿨다운)와 안전
화이트리스트(하체 동작 ID 원천 차단)를 걸어뒀습니다."

---

## 종료 절차 (전체)

1. 조종기로 로봇 제어권 회수 → 안전 위치로 → **Damp** → 전원 off
2. 터미널: Nav2 → 브리지 → relay → tap → lidar 순으로 Ctrl+C
3. (녹화했으면) 파일 백업

---

## 비상 대응 표

| 증상 | 즉각 조치 |
|---|---|
| launch 후 active 2회 안 뜸 | Ctrl+C → 재실행 1회. 연속 실패 시 전체 내리고 `rm -f /dev/shm/fastrtps*` 후 재기동 |
| 초기 위치가 안 찍힘 (TF 오류) | `set_pose.sh <각도>` + Publish Point |
| "Failed to create plan" | 목표를 흰 영역 안쪽으로 다시 / 출발점이 벽에 붙었으면 조이스틱로 0.5m 떼고 재설정 |
| patience exceeded / 0 poses | `clearmap.sh` → 재목표. 반복 시 위치 재설정 |
| 주행 중 멈추고 안 감 | 목표가 죽은 것 — Cancel → clearmap → 새 목표 (자동 재시도 없음) |
| tap 수신 0건 | 로봇 전원? / tap 터미널이 tapenv 인가? (`echo $ROS_DOMAIN_ID` → 0) |
| /odom 안 보임 | relay 터미널이 평소 세계인가? (`echo $RMW_IMPLEMENTATION` 비어야 정상) |
| 팔 액션 거부 (code 7404) | FSM 501 아님 — 조종기/시퀀스로 501 진입 |
| ④ 인식이 안 됨 | 전신 프레임인? 1초 유지했나? 쿨다운 중 아닌가? 조명 확인 |
| 로봇이 이상 거동 | **조종기 개입 최우선** → Damp |

---

*근거 기록: SESSION_2026-08-24/25.md · 설정 상세: docs/*
