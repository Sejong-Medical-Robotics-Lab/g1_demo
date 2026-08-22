# Nav2 자율주행 — 실행 순서

주행 중에 지도까지 만드는 방식은 휴머노이드에서 불안정했다.
보행 진동으로 지도와 위치가 동시에 흔들려 로봇이 엉뚱한 방향으로 갔다.

그래서 **두 단계로 나눈다.**

```
1단계) 지도를 만든다        — slam_toolbox (루프 클로저), Nav2 없음
2단계) 그 지도로 주행한다   — 지도 고정, AMCL 이 위치만 찾음
```

지도가 변하지 않으므로 **주행 중 오차가 누적되지 않는다.**

### 왜 slam_toolbox 인가

FAST-LIO 만으로 지도를 만들면 **루프 클로저가 없어** 한 번 어긋난 위치를
되돌릴 수 없다. 회전 구간에서 어긋난 오차가 그대로 쌓여 지도가 무너진다.

slam_toolbox 는 이미 지나온 곳을 다시 보면 오차를 되돌린다. 그리고 2D 로
투영하므로 상하 진동이 위치 추정에 개입하지 못한다. 결과물이 Nav2 가
그대로 쓰는 점유격자라 **변환 단계도 사라진다.**

FAST-LIO 는 여전히 필요하다 — **오도메트리 제공** 역할이다.

    map ──(slam_toolbox: 루프 클로저)──> camera_init ──(FAST-LIO)──> body

---

## 파일 배치

| 파일 | 위치 | 용도 |
|---|---|---|
| `mid360s_mapping.yaml` | `~/ws_fastlio/src/FAST_LIO/config/` | 지도용 FAST-LIO |
| `mid360s.yaml` | `~/ws_fastlio/src/FAST_LIO/config/` | 주행용 FAST-LIO |
| `g1_mapping_2d.launch.py` | `~/g1_real/` | **2D 지도 작성** |
| `g1_mapping.rviz` | `~/g1_real/` | 지도 작성용 RViz 설정(자동 적용) |
| `g1_nav2_localize.launch.py` | `~/g1_real/` | 자율주행 |
| `nav2_g1_localize.yaml` | `~/g1_real/` | Nav2 + AMCL 설정 |
| `pcd_to_map.py` | `~/g1_real/` | (예비) 3D PCD → 2D 변환 |

설치:

```bash
sudo apt install -y ros-jazzy-slam-toolbox ros-jazzy-pointcloud-to-laserscan \
                    ros-jazzy-navigation2 ros-jazzy-nav2-bringup
```

config 를 넣은 뒤:

```bash
cd ~/ws_fastlio && colcon build --symlink-install
```

두 config 의 차이:

| | mapping (지도용) | 기본 (주행용) |
|---|---|---|
| `point_filter_num` | 2 | 3 |
| `max_iteration` | 5 | 3 |
| `filter_size_*` | 0.2 | 0.3 |

지도용은 Nav2 를 같이 안 돌리므로 CPU 여유가 있어 품질을 조금 더 올렸다.
**차이는 이 정도로만 둔다.**

> ### ★ 필터를 세게 걸면 안 된다
>
> 주행용 부하를 줄이려고 `point_filter_num: 4` + `filter_size: 0.5` +
> `blind: 0.8` + `det_range: 30` 을 한꺼번에 걸었더니
>
> ```
> No Effective Points!
> ```
>
> 이 매 프레임 떴다. **정합에 쓸 점이 남지 않아 FAST-LIO 가 위치 추정을
> 포기한 것**이다. TF 가 날뛰고 AMCL 도 함께 무너져 로봇이 튀었다.
>
> **오도메트리가 깨지는 것보다 CPU 를 더 쓰는 편이 낫다.**
> 부하가 문제면 `point_filter_num` 을 **한 번에 한 단계씩만** 올리고
> 매번 `ros2 topic hz /Odometry` 로 10Hz 를 확인한다.

---

# 1단계 — 2D 지도 만들기

## 터미널 구성

**① 로봇을 FSM 501 로**

```bash
g1
python3 g1_stand_test.py --iface $G1_IFACE
```

**출발 지점을 바닥에 표시해 둔다.** 주행할 때 같은 자리에서 시작하면
초기 위치를 잡기 훨씬 쉽다.

**② LiDAR**

```bash
lidar
ros2 launch livox_ros_driver2 msg_MID360s_launch.py
```

**③ FAST-LIO — 오도메트리 제공**

```bash
slam
ros2 launch fast_lio mapping.launch.py config_file:=mid360s_mapping.yaml
```

**④ 2D SLAM + RViz**

```bash
slam
ros2 launch /home/hong/g1_real/g1_mapping_2d.launch.py
```

**⑤ 로봇 조종** — 조이스틱이 편하다. 코드로 한다면:

```bash
g1ros
python3 ~/g1_real/g1_cmdvel_bridge.py --iface $G1_IFACE
```

## RViz

**설정은 자동이다.** `g1_mapping.rviz` 가 함께 로드되어 Fixed Frame(map),
Map(`/map`), LaserScan(`/scan`), Odometry 가 이미 켜져 있고 시점도
위에서 내려다보는 뷰로 맞춰져 있다. 손으로 Add 할 필요가 없다.

FAST-LIO 의 3D 지도(`CloudMap3D`)는 꺼둔 상태로 들어 있다 —
발표 화면에 넣고 싶으면 체크만 하면 된다.

FAST-LIO 쪽 RViz 가 같이 떠서 겹치면 그쪽을 끈다:

```bash
ros2 launch fast_lio mapping.launch.py config_file:=mid360s_mapping.yaml rviz:=false
```

**볼 것**: 빨간 스캔 점이 지도의 검은 벽선과 **겹쳐야** 한다.
어긋나면 그 순간 위치 추정이 흔들린 것이다.

## 걷는 방법 — 지도 품질을 좌우한다

**① 회전을 원호로** ← 가장 효과가 크다

제자리 회전이 위치 추정을 가장 크게 흔든다. 방향을 바꿀 때
**멈춰서 돌지 말고 전진하면서 완만하게 돌아간다.**

```bash
ros2 topic pub -r 10 /cmd_vel geometry_msgs/msg/Twist \
  "{linear: {x: 0.12}, angular: {z: 0.1}}"     # 전진 + 약한 회전 = 원호
```

**② 천천히, 끊김 없이**

`vx` 0.15 이하. 급출발·급정지가 IMU 를 흔든다.

**③ ★ 출발점으로 되돌아온다** — 루프 클로저가 작동하는 순간

한 바퀴 돌아 처음 자리로 오면 **쌓인 오차가 한 번에 보정된다.**
RViz 에서 지도가 살짝 튕기며 정렬되는 것이 보인다.

이것이 FAST-LIO 단독으로는 못 하던 일이고, slam_toolbox 를 얹은 이유다.
**경로를 짤 때 반드시 출발점으로 돌아오게 설계한다.**

**④ 환경**

- 사람이 없는 시간에 한다
- 유리벽·거울 구간은 빨리 지나간다

## 감시

```bash
slam
ros2 topic hz /Odometry     # 10Hz 유지 확인
ros2 topic hz /map          # 지도가 갱신되는지
```

`/Odometry` 가 10Hz 아래로 떨어지면 계산이 밀리는 것이다.
그 구간에서 속도를 줄이거나 `mid360s_mapping.yaml` 을 한 단계 낮춘다.

## 저장

지도가 깔끔하면(벽이 한 겹으로 보이면):

```bash
slam
ros2 run nav2_map_server map_saver_cli -f ~/g1_real/maps/lab_2d
```

→ `lab_2d.pgm` + `lab_2d.yaml`. **이것을 주행에 그대로 쓴다.**

3D PCD 도 남기고 싶으면 FAST-LIO 쪽에서 따로:

```bash
savemap
```

## 확인

```bash
eog ~/g1_real/maps/lab_2d.pgm
```

**벽이 검은 선, 다닌 곳이 흰색이면 정상.**

| 증상 | 조정 |
|---|---|
| 벽이 여러 겹으로 겹친다 | 루프 클로저가 못 잡은 것. 더 천천히, 출발점으로 확실히 복귀 |
| 바닥이 장애물로 찍힌다 | `g1_mapping_2d.launch.py` 의 `min_height` 를 올린다 (-0.9 등) |
| 벽이 안 잡힌다 | `max_height` 를 올린다 (0.5 등) |
| 지도가 거의 안 생긴다 | `ros2 topic hz /scan` 확인. 10Hz 안 나오면 앞단 문제 |

**여러 번 시도해서 제일 잘 나온 것을 쓴다.**

```bash
ros2 run nav2_map_server map_saver_cli -f ~/g1_real/maps/try1
ros2 run nav2_map_server map_saver_cli -f ~/g1_real/maps/try2
```

---

# 2단계 — 자율주행

## 실행 — 터미널 5개

**① 로봇을 FSM 501 로**

```bash
g1
python3 g1_stand_test.py --iface $G1_IFACE
```

**지도를 만들 때 출발했던 자리 근처에 둔다.**

**② LiDAR**

```bash
lidar
ros2 launch livox_ros_driver2 msg_MID360s_launch.py
```

**③ FAST-LIO (주행 설정 — 가벼운 쪽)**

```bash
slam
ros2 launch fast_lio mapping.launch.py config_file:=mid360s.yaml
```

여기서는 FAST-LIO 가 **오도메트리 역할만** 한다. 지도는 안 쓴다.

**④ 브리지** ← 로봇을 실제로 움직이는 노드. **끄면 비상 정지.**

```bash
g1ros
python3 ~/g1_real/g1_cmdvel_bridge.py --iface $G1_IFACE
```

**이 터미널을 화면 앞쪽, 손이 닿기 쉬운 곳에 둔다.**

**⑤ Nav2 + AMCL**

```bash
slam
ros2 launch /home/hong/g1_real/g1_nav2_localize.launch.py
```

다른 지도를 쓰려면:

```bash
ros2 launch /home/hong/g1_real/g1_nav2_localize.launch.py \
    map:=/home/hong/g1_real/maps/try2.yaml
```

## ★ 초기 위치 지정 — 절대 건너뛰지 않는다

RViz 는 Nav2 기본 설정(`nav2_default_view.rviz`)으로 자동 구성된다.
Map / LaserScan / particlecloud / 경로 표시와 **2D Pose Estimate·2D Goal Pose
도구**가 이미 준비되어 있다. (끄려면 `rviz:=false`)

**`2D Pose Estimate`** 버튼 → 로봇의 실제 위치를 클릭하고
바라보는 방향으로 드래그

**성공 판정**: 화살표 뭉치(`/particlecloud`)가 로봇 주변으로 모이고,
`/scan` 의 빨간 점들이 지도의 검은 벽선과 겹친다.

퍼져 있거나 스캔이 벽과 어긋나면 **다시 찍는다.** 이게 맞아야 나머지가 된다.

## 목표 주기

**`2D Goal Pose`** 버튼 → 목표 지점 클릭 → 도착해서 볼 방향으로 드래그.

- **클릭한 지점이 목표다.** 화살표를 길게 끌어도 더 멀리 가지 않는다
  (드래그는 방향만 정한다)
- `xy_goal_tolerance: 0.35` — 35cm 안에 들어오면 도착으로 친다

**첫 시도는 2~3m 앞, 직선 경로, 사람 없는 곳.**

---

# 정지 방법

| 순서 | 방법 | 속도 |
|---|---|---|
| 1 | **리모컨** (사람이 소지) | 가장 확실 |
| 2 | **브리지 터미널 `Ctrl+C`** | 즉시 + 데드맨 0.5초 |
| 3 | RViz 의 Nav2 패널 → Cancel | 느림 |

브리지를 끄면 정지 명령이 5회 나가고, 그마저 실패해도
**명령이 끊긴 지 0.5초 후 로봇이 스스로 멈춘다**(데드맨).

---

# 문제 해결

| 증상 | 확인 |
|---|---|
| 로봇이 엉뚱한 방향으로 간다 | 초기 위치를 안 찍었거나 잘못 찍음. 다시 찍는다 |
| 출발하자마자 멈춘다 | `ros2 topic echo /collision_monitor_state` — `stop` 이면 스캔에 자기 몸이 잡히는 것 |
| 경로를 못 찾는다 | 지도의 자유공간(흰색)이 부족하다. 지도를 다시 만들거나 `inflation_radius` 를 낮춘다 |
| 목표 근처에서 뱅뱅 돈다 | `xy_goal_tolerance` 를 0.5 로 올린다 |
| 지도와 스캔이 안 맞는다 | 지도를 만든 뒤 공간이 바뀌었을 수 있다. 다시 만든다 |
| 걷다가 위치를 잃는다 | `ros2 topic hz /Odometry` 가 10Hz 인지. 낮으면 CPU 부하 |
| **`No Effective Points!`** | FAST-LIO 가 정합할 점을 못 찾는 것. `point_filter_num`·`filter_size_*`·`blind` 를 낮추고 `det_range` 를 키운다 |
| TF 축이 날뛴다 | 위와 같은 원인. FAST-LIO 오도메트리가 깨진 것이다 |

**AMCL 이 위치를 잃었을 때**는 로봇을 멈추고 `2D Pose Estimate` 로
다시 찍으면 회복된다.

---

# 현실적인 기대치

| 시나리오 | 가능성 |
|---|---|
| 직선 5m 앞 목표 | 높음 |
| 모퉁이 돌아 10m | 중간 |
| 좁은 통로(폭 2m 이하) | 낮음 — `inflation_radius` 조정 필요 |
| 움직이는 사람 피하기 | 낮음 |

**데모 경로를 미리 정하고 그 경로만 확실히 되게 만드는 것**을 권한다.
임의의 목표를 모두 소화하려 하면 끝이 없다.
