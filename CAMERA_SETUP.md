# 카메라(RealSense D435i) 연결 — 작업 기록과 설명

이 문서는 **"왜 이렇게 했는지"** 를 남기기 위한 것이다.
명령만 나열하면 다음에 조건이 조금만 달라져도 막힌다.

*작성: 2026-08-22*

---

## 0. 시작 전 알아야 할 구조

G1 안에는 컴퓨터가 **두 대** 있다.

| | 이름 | IP | 역할 | 우리 권한 |
|---|---|---|---|---|
| PC1 | 운동제어 유닛 | `192.168.123.161` | 보행 알고리즘 | ❌ Unitree 가 잠가둠 |
| PC2 | **Jetson** | `192.168.123.164` | 개발용 | ✅ SSH 접속 가능 |

**Jetson** 은 NVIDIA 가 만든 손바닥만 한 임베디드 보드다. 저전력 ARM CPU 라
노트북보다 훨씬 느리다(`uname -m` → `aarch64`, 우리 PC 는 `x86_64`).
로봇 안에 들어갈 만큼 작다는 게 장점이고, 빌드가 오래 걸리는 게 단점이다.

**RealSense 는 이 Jetson 에 USB 로 붙어 있다.**

```
    RealSense D435i ──USB── Jetson ──이더넷── 내 PC
```

LiDAR 는 이더넷에 직접 붙어 있어서 PC 에서 바로 받았지만, 카메라는
USB 라 로봇 안에서 끝난다. **Jetson 에서 드라이버를 돌리고 그 결과를
ROS 토픽으로 받아야 한다.**

---

## 1. 카메라가 아예 안 보였다

처음 `lsusb` 를 쳤을 때 Intel 장치가 하나도 없었다.

```
Bus 002 Device 002: ID 0bda:0411 Realtek ... 4-Port USB 3.0 Hub
Bus 001 Device 003: ID 0bda:a85b Realtek ...        ← 뭔지 모를 장치
Bus 001 Device 002: ID 0bda:5411 Realtek ... 4-Port USB 2.0 Hub
```

`/dev/video*` 도 없었다.

정체불명 장치를 확인해 보니 카메라가 아니었다:

```bash
lsusb -v -d 0bda:a85b 2>/dev/null | grep -i "bInterfaceClass"
#   bInterfaceClass  224 Wireless      ← 블루투스 어댑터였다
```

> **`lsusb` 읽는 법**
> `ID 벤더:제품` 형식이다. Intel 은 `8086`, Realtek 은 `0bda`.
> `bInterfaceClass` 는 장치 종류 — `14` = Video, `224` = Wireless.
> 벤더 ID 만 봐도 절반은 알 수 있다.

**원인: 케이블이 안 꽂혀 있었다.** 로봇에 모듈은 달려 있는데
Jetson USB 포트에 연결이 안 된 상태였다.

꽂으니 바로 잡혔다:

```
Bus 002 Device 006: ID 8086:0b3a Intel Corp.    ← RealSense D435i
```

### 어느 포트에 꽂느냐가 중요하다

처음엔 `Bus 001` 에 꽂혔다. 이건 **USB 2.0** 이다.

```
Bus 001 → USB 2.0   (480 Mbps)
Bus 002 → USB 3.0   (5 Gbps)
```

RealSense 는 컬러와 깊이를 동시에 보내면 대역폭을 많이 먹는다.
**USB 2.0 에 꽂으면 해상도·fps 를 크게 낮춰야 하고 아예 실행이 안 될 수도
있다.** 포트를 옮겨 `Bus 002` 로 만들었다.

> 꽂을 때마다 `Device` 번호가 올라가는 건 정상이다. 뺐다 꽂으면
> 새 번호가 붙는다.

---

## 2. 드라이버 설치가 두 번 막혔다

### 벽 ① — ROS 2 Foxy 저장소가 404

```bash
sudo apt install ros-foxy-realsense2-camera
# E: Unable to locate package
# Err: http://packages.ros.org/ros2/ubuntu focal Release  404 Not Found
```

**ROS 2 Foxy 는 2023년에 지원이 끝나(EOL) 패키지 서버에서 내려갔다.**
Jetson 에 Foxy 가 깔려 있는 건 예전에 받아둔 것이고, **새로 추가 설치는
불가능하다.**

→ apt 로는 못 받는다. **소스에서 직접 빌드**해야 한다.

### 벽 ② — Jetson 이 인터넷에 못 나간다

소스를 받으려면 `git clone` 이 필요한데:

```bash
ping -c 2 8.8.8.8
# Destination Host Unreachable

ping -c 2 google.com
# Temporary failure in name resolution
```

**Jetson 은 로봇 내부망(`192.168.123.x`)에만 있고 외부로 나가는 출구가
없었다.** 우리 PC 도 유선은 로봇 전용이고 인터넷은 WiFi 로 따로 쓴다.

> **`Destination Host Unreachable` vs `Temporary failure in name resolution`**
> 앞은 "그 IP 로 가는 길이 없다"(라우팅 문제),
> 뒤는 "도메인 이름을 IP 로 못 바꾼다"(DNS 문제).
> 둘 다 뜨면 애초에 밖으로 나갈 길이 없다는 뜻이다.

**해결: Jetson 의 내장 WiFi 를 썼다.**

```bash
nmcli device
# wlan0   wifi   disconnected   --      ← 쓸 수 있는 WiFi 가 있었다

sudo nmcli device wifi connect "sejong-guest" password "..."
```

```
eth0  → 192.168.123.164   로봇 내부망 (그대로 유지)
wlan0 → 학교 WiFi          인터넷용
```

**유선을 건드리지 않는 것이 핵심이다.** 로봇 통신은 `eth0` 이 그대로
담당하므로 LiDAR·제어에 영향이 없다.

> **`ping` 이 실패해도 인터넷이 될 수 있다**
> WiFi 연결 후에도 `ping 8.8.8.8` 은 계속 실패했다. 그런데
> ```bash
> curl -I http://github.com
> # HTTP/1.1 301 Moved Permanently   ← 정상 응답
> ```
> **`sejong-guest` 가 ICMP(ping)를 차단하고 HTTP 만 허용한 것이다.**
> 공용망에서 흔하다. ping 실패를 인터넷 불가로 단정하면 안 된다.

---

## 3. librealsense 빌드

```bash
# 의존성
sudo apt install -y git cmake libssl-dev libusb-1.0-0-dev pkg-config \
    libgtk-3-dev libglfw3-dev libgl1-mesa-dev libglu1-mesa-dev v4l-utils

# 소스
cd ~
git clone https://github.com/IntelRealSense/librealsense.git
cd librealsense
git checkout v2.55.1
```

> **왜 특정 태그(`v2.55.1`)를 쓰나**
> master 는 언제든 바뀐다. 나중에 같은 결과를 재현하려면 버전을 못 박아야
> 한다. FAST-LIO 때 태그를 잘못 골라 빌드가 깨진 적이 있으니
> **어떤 버전을 썼는지 반드시 기록한다.**

### udev 규칙 — 빠뜨리면 나중에 권한 오류가 난다

```bash
./scripts/setup_udev_rules.sh
# → "Remove all RealSense cameras attached. Hit any key when ready"
#    카메라 USB 를 뽑고 엔터. 규칙 설치 후 다시 꽂는다.
```

**udev 규칙**은 "이 USB 장치가 꽂히면 어떤 권한을 줄지" 정하는 리눅스
설정이다. 이게 없으면 일반 사용자가 카메라에 접근할 수 없어
`Permission denied` 가 난다. **꽂힌 상태에서는 새 규칙이 적용되지 않으므로
뽑았다 꽂아야 한다.**

### 빌드

```bash
mkdir build && cd build
cmake .. -DCMAKE_BUILD_TYPE=Release \
         -DBUILD_EXAMPLES=false -DBUILD_GRAPHICAL_EXAMPLES=false
```

예제와 GUI 도구를 빼서 빌드 시간을 줄였다. 우리는 ROS 로 쓸 것이라
`realsense-viewer` 같은 GUI 가 필요 없다.

```bash
sudo apt install -y tmux
tmux new -s rs        # ← SSH 가 끊겨도 빌드가 계속 돌게 한다
make -j4
```

> **왜 `tmux` 를 쓰나**
> SSH 세션이 끊기면 그 안에서 돌던 프로세스도 같이 죽는다. 30분~1시간짜리
> 빌드가 중간에 날아가면 처음부터다.
> tmux 안에서 돌리면 세션이 끊겨도 살아 있다.
> · 빠져나오기 `Ctrl+B` → `D`
> · 다시 들어가기 `tmux attach -t rs`

> **왜 `-j4` 인가**
> `-j` 는 동시에 컴파일할 개수다. `-j$(nproc)` 으로 코어를 다 쓰면 빠르지만
> 메모리를 많이 먹어 빌드가 죽을 수 있다. Jetson 메모리는 15GB 로
> 넉넉한 편이지만 안전하게 4로 제한했다.

```bash
sudo make install
sudo ldconfig            # 새로 설치한 라이브러리를 시스템이 찾게 한다
```

### 확인

```bash
rs-enumerate-devices
```

카메라 정보(시리얼, 펌웨어 버전, 지원 스트림)가 나오면 성공이다.
여기까지가 **ROS 와 무관한 카메라 자체의 동작 확인**이다.

---

## 4. 다음 단계 (예정)

### realsense-ros — ROS 2 래퍼

```bash
mkdir -p ~/ws_rs/src && cd ~/ws_rs/src
git clone https://github.com/IntelRealSense/realsense-ros.git -b ros2-legacy
cd ~/ws_rs
source /opt/ros/foxy/setup.bash
colcon build --symlink-install
```

`ros2-legacy` 브랜치가 Foxy 용이다. 최신 브랜치는 Humble 이상을 요구한다.

### 실행

```bash
source ~/ws_rs/install/setup.bash
export ROS_DOMAIN_ID=33
export RMW_IMPLEMENTATION=rmw_fastrtps_cpp

ros2 launch realsense2_camera rs_launch.py \
    rgb_camera.profile:=640x480x15 \
    enable_depth:=false
```

**RGB 만, 낮은 해상도로 시작한다.** 깊이까지 켜면 대역폭이 두 배가 된다.
되는 것을 확인하고 나서 올린다.

### ★ 남은 최대 관문 — Foxy ↔ Jazzy

| | OS | ROS |
|---|---|---|
| Jetson | Ubuntu 20.04 | **Foxy** |
| 내 PC | Ubuntu 24.04 | **Jazzy** |

**배포판이 다른 두 대 사이에 토픽이 오갈지는 아직 검증되지 않았다.**

`sensor_msgs/Image` 같은 표준 메시지는 정의가 안정적이라 보통 통하지만,
DDS 구현(RMW)이 다르면 서로를 못 본다.

- Foxy 기본 = FastDDS
- Jazzy 기본 = CycloneDDS

→ **양쪽을 FastDDS 로 맞춰본다.**

```bash
export ROS_DOMAIN_ID=33                      # 양쪽 동일
export RMW_IMPLEMENTATION=rmw_fastrtps_cpp   # 양쪽 동일
```

안 보이면 확인 순서:

```bash
echo $ROS_DOMAIN_ID $RMW_IMPLEMENTATION   # 양쪽에서 같은가
ros2 multicast send                        # Jetson
ros2 multicast receive                     # PC — 메시지가 오는가
sudo tcpdump -i <인터페이스> -n host 192.168.123.164 -c 20
```

---

## 5. 이 작업에서 배운 것

**① 설치부터 시작하지 않는다.**
`lsusb`, `ls /opt/ros/`, `ros2 topic list` 로 **지금 뭐가 있는지** 부터 본다.
LiDAR 때 이 단계를 건너뛰고 원인을 추측하며 설정을 바꾸다가 세 시간을 썼다.
필요한 파일은 처음부터 폴더에 있었다.

**② 에러 메시지를 정확히 읽는다.**
`Destination Host Unreachable`(라우팅)과
`Temporary failure in name resolution`(DNS)은 다른 문제다.
`404 Not Found` 는 "서버가 그 경로를 모른다"는 뜻이지 네트워크 문제가 아니다.

**③ 한 가지 신호로 단정하지 않는다.**
`ping` 이 안 된다고 인터넷이 없다고 결론 내렸으면 여기서 막혔을 것이다.
`curl` 로 다시 확인해서 **ICMP 만 막힌 것**임을 알았다.

**④ 무엇을 건드리지 않을지 정한다.**
PC 라우팅을 고쳐 인터넷을 공유하는 방법도 있었지만, 그러면 잘 되고 있는
로봇 통신에 영향이 갈 수 있었다. Jetson 내장 WiFi 를 쓰는 쪽이
**기존에 동작하는 것을 하나도 건드리지 않는다.**

**⑤ 버전을 기록한다.**
`librealsense v2.55.1`, `realsense-ros ros2-legacy`.
"어떻게든 됐다"로 끝내면 다음에 재현할 수 없다.
