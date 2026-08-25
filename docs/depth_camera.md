# 로봇 카메라 연결 작업 계획

**목표**: G1 머리에 달린 RGB 카메라 영상을 **내 PC 의 ROS 2 토픽으로 받는 것**
**필요한 것**: 로봇 (전원 켜고 유선 연결된 상태)

---

## 0. 왜 이게 간단하지 않은가 — 먼저 알아둘 것

LiDAR 는 이더넷에 직접 붙어 있어서 PC 에서 바로 받았다.
**카메라는 다르다.**

```
    RealSense D435i ──USB── Jetson (로봇 안 컴퓨터) ──이더넷── 내 PC
```

USB 는 로봇 안에서 끝난다. 그래서 **Jetson 에서 카메라 노드를 띄우고,
그 결과를 ROS 토픽으로 네트워크 너머 받아야** 한다.

**그리고 ROS 배포판이 다르다.**

| | OS | ROS |
|---|---|---|
| 내 PC | Ubuntu 24.04 | **Jazzy** |
| Jetson | Ubuntu 20.04 | **Foxy** |

`sensor_msgs/Image` 같은 표준 메시지는 정의가 안정적이라 보통 통하지만,
**아직 아무도 검증하지 않았다.** 이 작업의 가장 큰 불확실 요소다.

> 배포판이 다르면 **DDS 구현(RMW)** 을 양쪽에서 맞춰야 한다.
> Foxy 기본은 FastDDS, Jazzy 기본은 CycloneDDS 라 그냥 두면 서로 못 본다.
> 3-3 에서 다룬다.

---

## 1. 접속 정보

| 항목 | 값 |
|---|---|
| Jetson IP | `192.168.123.164` |
| 계정 / 비번 | `unitree` / `123` |
| 내 PC IP | `192.168.123.51` (유선 고정) |
| `ROS_DOMAIN_ID` | **33** (양쪽 동일해야 함) |

로봇이 켜져 있고 유선이 연결돼 있어야 한다. 부팅에 1~2분 걸린다.

```bash
ping -c 3 192.168.123.164        # 응답 확인 후 진행
```

---

## 2. ★ 먼저 현재 상태부터 파악한다

**Unitree 가 이미 뭔가 띄워놨을 수 있다.** 그러면 설치를 건너뛴다.
설치부터 시작하지 말고 **반드시 이걸 먼저 한다.**

```bash
ssh unitree@192.168.123.164
```

로그인하면 ROS 환경 선택 프롬프트가 뜬다 → **`1` (foxy)** 입력.

접속 후 아래를 순서대로 실행하고 **결과를 전부 기록**한다.

```bash
# 1) 시스템
lsb_release -a
uname -m                         # aarch64 (arm64) 확인
df -h /                          # 저장 공간 여유

# 2) ROS
ls /opt/ros/
echo $ROS_DISTRO

# 3) 카메라가 물리적으로 인식되는가
lsusb | grep -i intel
ls /dev/video*

# 4) realsense 관련이 이미 있는가
ros2 pkg list | grep -i realsense
which realsense-viewer
ps aux | grep -i realsense       # 노드가 이미 돌고 있는가

# 5) 이미 떠 있는 토픽
export ROS_DOMAIN_ID=33
ros2 topic list

# 6) Unitree 가 제공하는 프로그램
ls ~/
ls /unitree 2>/dev/null
```

### 결과에 따라 갈리는 길

| 상황 | 다음 |
|---|---|
| `ros2 topic list` 에 `/camera/...` 가 이미 있다 | **3-3 으로 바로** |
| `realsense2_camera` 패키지가 있다 | **3-2 로** |
| 아무것도 없다 | **3-1 부터** |
| `lsusb` 에 Intel 장치가 없다 | **여기서 멈추고 공유** — 카메라가 안 붙어 있거나 케이블 문제 |

---

## 3. 작업

### 3-1. realsense-ros 설치 (Jetson 안에서)

```bash
sudo apt update
sudo apt install -y ros-foxy-realsense2-camera
```

**arm64 라 패키지가 없을 수 있다.** 그 경우 `librealsense2` 부터 소스 빌드해야
하는데 시간이 오래 걸린다(1~3시간). **그 상황이 되면 먼저 공유할 것** —
다른 방법을 같이 찾는다.

> 저장 공간을 확인하고 시작한다. Jetson 은 보통 여유가 많지 않다.

### 3-2. 카메라 노드 실행 (Jetson 안에서)

```bash
source /opt/ros/foxy/setup.bash
export ROS_DOMAIN_ID=33
export RMW_IMPLEMENTATION=rmw_fastrtps_cpp

ros2 launch realsense2_camera rs_launch.py \
    rgb_camera.profile:=640x480x15 \
    enable_depth:=false
```

**RGB 만, 낮은 해상도로 시작한다.**

- `enable_depth:=false` — 깊이는 나중에. 지금 켜면 대역폭이 두 배
- `640x480x15` — 1280x720x30 은 네트워크를 먹는다. 되는 걸 확인하고 올린다

Jetson 쪽에서 토픽이 나오는지 먼저 확인:

```bash
# Jetson 에서 새 터미널(또는 ssh 하나 더)
source /opt/ros/foxy/setup.bash
export ROS_DOMAIN_ID=33
ros2 topic list
ros2 topic hz /camera/camera/color/image_raw
```

토픽 이름은 realsense-ros 버전에 따라 다르다
(`/camera/color/image_raw` 일 수도 있음). **실제 이름을 기록할 것.**

**Jetson 안에서도 안 나오면** 네트워크 문제가 아니라 카메라/드라이버 문제다.

### 3-3. ★ 내 PC 에서 받기 — 여기가 최대 난관

```bash
source /opt/ros/jazzy/setup.bash
export ROS_DOMAIN_ID=33
export RMW_IMPLEMENTATION=rmw_fastrtps_cpp

ros2 topic list | grep camera
ros2 topic hz /camera/camera/color/image_raw
```

영상 보기:

```bash
ros2 run rqt_image_view rqt_image_view
```

### 안 보일 때 확인 순서

**① 양쪽 `ROS_DOMAIN_ID` 가 같은가**

```bash
echo $ROS_DOMAIN_ID     # 양쪽에서 33 이어야 한다
```

ROS 2 는 도메인 번호가 다르면 서로를 아예 못 본다. 제일 흔한 원인.

**② 양쪽 RMW 가 같은가** ← 배포판이 다를 때 핵심

```bash
echo $RMW_IMPLEMENTATION    # 양쪽에서 rmw_fastrtps_cpp
```

Jetson(Foxy) 기본은 FastDDS, PC(Jazzy) 기본은 CycloneDDS 다.
**둘 다 FastDDS 로 맞춘다.** Jazzy 에 FastDDS 가 없으면:

```bash
sudo apt install -y ros-jazzy-rmw-fastrtps-cpp
```

**③ 네트워크에서 실제로 오는가**

```bash
sudo tcpdump -i <인터페이스> -n host 192.168.123.164 -c 20
```

패킷이 아예 없으면 DDS 가 통신을 시작조차 못한 것 →  ①②를 다시 본다.

**④ 멀티캐스트가 되는가**

ROS 2 는 상대를 찾을 때 멀티캐스트를 쓴다.

```bash
# PC 에서
ros2 multicast receive
# Jetson 에서
ros2 multicast send
```

PC 쪽에 메시지가 뜨면 정상.

### 3-4. 느릴 때

`ros2 topic hz` 가 나오는데 값이 낮거나 끊기면:

- 해상도·fps 를 더 낮춘다 (`424x240x6`)
- **compressed 토픽을 쓴다** — 원본 대신 압축본을 받는다

  ```bash
  ros2 topic list | grep compressed
  ```

  `image_transport` 가 자동으로 만들어주는 경우가 많다.
  압축본을 받으면 대역폭이 크게 준다.

---

## 4. 성공 기준

- [ ] Jetson 에서 카메라 노드가 뜬다
- [ ] Jetson 안에서 `ros2 topic hz` 로 영상 토픽이 흐른다
- [ ] **내 PC 에서 같은 토픽이 보인다**
- [ ] `rqt_image_view` 로 영상이 실제로 보인다
- [ ] 몇 Hz 나오는지 기록했다

---

## 5. 기록할 것 (이게 산출물이다)

이 프로젝트에서는 **공식 문서에 없는 값이 많았다.**
(로봇 FSM 번호, LiDAR 모델 구분법 등 — 전부 실측으로 알아냈다)
다시 찾으려면 며칠이 걸리므로 **알아낸 즉시 적는다.**

| 항목 | 값 |
|---|---|
| Jetson OS / ROS 버전 | |
| realsense-ros 설치 방법 (apt / 소스) | |
| 카메라 노드 실행 명령 (전체) | |
| **실제 토픽 이름** | |
| 사용한 해상도 / fps | |
| PC 에서 측정한 Hz | |
| RMW 설정 (양쪽) | |
| 겪은 문제와 해결 방법 | |

저장소 `Sejong-Medical-Robotics-Lab/g1_demo` 에 문서로 남긴다.

---

## 6. 다음 단계 (이게 되면)

**① 깊이(depth) 켜기**

```bash
ros2 launch realsense2_camera rs_launch.py \
    rgb_camera.profile:=640x480x15 \
    depth_module.profile:=640x480x15 \
    align_depth.enable:=true
```

`align_depth` 는 컬러 픽셀과 깊이 픽셀을 맞춰준다.
"화면의 이 사람이 몇 미터인가"를 계산하려면 필요하다.

**② 사람 인식 노드를 이 토픽에 연결**

웹캠으로 개발한 노드의 구독 토픽만 바꾸면 된다.
거리 추정도 박스 높이 방식에서 **실제 깊이 값**으로 대체한다.

---

## 7. 주의사항

**로봇을 쓰는 작업은 혼자 하지 않는다.** 팀 규칙이다.
로봇 사용 전에 미리 알린다 — 한 대뿐이라 자율주행 파트와 겹칠 수 있다.

**반나절 이상 같은 곳에서 막히면 공유한다.**
특히 3-3 은 검증되지 않은 조합이라 안 될 가능성이 실재한다.
안 되면 대안(웹캠을 로봇에 임시 장착 등)을 같이 찾는다.

**에러 없이 조용히 실패하는 경우를 조심한다.**
이 프로젝트에서 제일 오래 걸린 문제들은 전부 에러 메시지가 없었다.
"노드는 떴는데 토픽에 아무것도 안 흐르는" 상황이 그렇다.
**`ros2 topic hz` 로 데이터가 실제로 흐르는지 매번 확인하는 습관.**

**추측보다 관찰이 빠르다.**
2장(현재 상태 파악)을 건너뛰고 설치부터 시작하지 말 것.
이미 준비된 것이 있는데 모르고 다시 만드는 게 제일 아깝다.
