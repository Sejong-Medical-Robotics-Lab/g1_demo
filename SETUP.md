# SETUP — 개발 환경 구축

이 저장소의 스크립트를 실행하기 위한 환경 구축 절차.
스크립트 사용법은 [README.md](README.md) 참고.

## 대상 환경

| 항목 | 값 |
|---|---|
| OS | Ubuntu 24.04 |
| ROS | ROS 2 Jazzy |
| Python | 3.12 |
| 로봇 | Unitree G1 (EDU) |
| 통신 | Ethernet / DDS |

작업 디렉터리 구성:

```
~/g1_real/               # 이 저장소
~/unitree_sdk2_python/   # G1 제어 SDK (venv 포함)
~/cyclonedds/            # DDS 라이브러리
~/Livox-SDK2/            # LiDAR 통신 라이브러리
~/ws_livox/              # LiDAR ROS 2 워크스페이스
```

---

## 1. CycloneDDS

`unitree_sdk2_python` 이 이걸 요구한다. 먼저 빌드해야 SDK 설치가 통과한다.

```bash
cd ~
git clone https://github.com/eclipse-cyclonedds/cyclonedds -b releases/0.10.x
cd cyclonedds && mkdir build install && cd build
cmake .. -DCMAKE_INSTALL_PREFIX=../install
cmake --build . --target install
```

> `0.10.x` 브랜치를 지정하는 이유: SDK 가 `cyclonedds==0.10.2` 를 요구한다.
> 최신 버전을 받으면 파이썬 바인딩 설치에서 실패한다.

## 2. Unitree SDK2 Python

시스템 파이썬을 오염시키지 않도록 **venv 안에** 설치한다.

```bash
cd ~
git clone https://github.com/unitreerobotics/unitree_sdk2_python.git
cd unitree_sdk2_python

python3 -m venv .venv
source .venv/bin/activate

export CYCLONEDDS_HOME=~/cyclonedds/install
pip3 install -e .
```

확인:

```bash
python3 -c "import unitree_sdk2py; print('OK')"
```

`OK` 가 나오면 성공.

> **`Could not locate cyclonedds` 에러**가 나면 `CYCLONEDDS_HOME` 이 안 잡힌 것이다.
> 1번을 먼저 끝내고 export 한 뒤 다시 `pip3 install -e .`.

## 3. 이 저장소

```bash
cd ~
git clone https://github.com/Sejong-Medical-Robotics-Lab/g1_demo.git g1_real
```

터미널 준비 별칭 등록:

```bash
echo "alias g1='source ~/g1_real/g1_env.sh'" >> ~/.bashrc
source ~/.bashrc
```

이후 터미널을 열 때마다 `g1` 한 번이면 venv 활성화 + `CYCLONEDDS_HOME` 설정 +
인터페이스 자동 탐지 + 작업 폴더 이동이 끝난다.

`g1_env.sh` 상단의 `SDK_DIR` / `CYCLONE_DIR` / `WORK_DIR` 경로가 실제와
다르면 수정한다.

로봇 없이 확인:

```bash
g1
python3 g1_stand_test.py --dry-run
python3 g1_walk_test.py --dry-run --preset forward_stop_turn
python3 g1_real_sequence.py --dry-run
```

세 개 모두 실행 계획이 출력되면 배치 정상.

---

## 4. 네트워크

G1 은 `192.168.123.0/24` 대역을 쓴다. PC 유선 IP 를 이 대역의 빈 주소로 잡는다.

| 주소 | 용도 |
|---|---|
| `192.168.123.161` | 운동제어 유닛 (PC1) — **사용 금지** |
| `192.168.123.164` | 개발 계산 유닛 (Jetson, PC2) — **사용 금지** |
| LiDAR (기체별 상이) | MID-360 — **사용 금지** |
| `192.168.123.51` 등 | PC 에 배정 |

기존 인터넷 설정을 건드리지 않도록 별도 프로파일로 만든다:

```bash
nmcli con add type ethernet ifname enp2s0 con-name g1-wired \
  ipv4.method manual ipv4.addresses 192.168.123.51/24
```

`enp2s0` 은 `ip -o link show` 로 확인한 실제 인터페이스명으로 바꾼다.
로봇 사용 시 `nmcli con up g1-wired` 로 전환.

확인:

```bash
g1                          # G1_IFACE 가 잡히는지
ping 192.168.123.164        # Jetson 응답
```

### Jetson(PC2) 접속

```bash
ssh unitree@192.168.123.164
```

기본 계정 `unitree` / 비밀번호 `123` (변경되었을 수 있음).
깊이 카메라(RealSense)는 이 Jetson 에 USB 로 붙어 있어서, 카메라 노드는
Jetson 쪽에서 실행하고 토픽만 PC 에서 구독한다.

접속 후 확인할 것:

```bash
lsb_release -a                    # Ubuntu 버전
ls /opt/ros/                      # ROS 배포판
lsusb | grep -i intel             # D435i 인식
ros2 pkg list | grep realsense    # realsense-ros 설치 여부
ros2 topic list                   # 이미 떠 있는 토픽
```

---

## 5. LiDAR (MID-360)

MID-360 은 자체 UDP 프로토콜을 쓴다. ROS 2 로 보려면 드라이버가 필요하다.

```
MID-360 ──UDP──> Livox-SDK2 ──> livox_ros_driver2 ──> /livox/lidar ──> RViz2
```

### 5-1. Livox-SDK2

```bash
sudo apt install -y cmake build-essential git python3-colcon-common-extensions
cd ~
git clone https://github.com/Livox-SDK/Livox-SDK2.git
cd Livox-SDK2 && mkdir build && cd build
cmake .. && make -j$(nproc)
sudo make install
```

### 5-2. livox_ros_driver2

**경로가 중요하다.** 반드시 `[워크스페이스]/src/livox_ros_driver2` 여야 한다.

```bash
cd ~
git clone https://github.com/Livox-SDK/livox_ros_driver2.git ws_livox/src/livox_ros_driver2
cd ~/ws_livox/src/livox_ros_driver2
source /opt/ros/jazzy/setup.sh
./build.sh jazzy
```

`colcon build` 가 아니라 `./build.sh jazzy` 다.
`Finished <<< livox_ros_driver2` 가 나오면 성공 (CMake 경고와 unused variable
경고는 무시해도 된다).

라이브러리 경로 등록:

```bash
echo 'export LD_LIBRARY_PATH=${LD_LIBRARY_PATH}:/usr/local/lib' >> ~/.bashrc
```

### 5-3. IP 설정 (로봇 필요)

`~/ws_livox/src/livox_ros_driver2/config/MID360_config.json` 수정:

- `host_net_info` 의 IP → **내 PC IP** (4-1 에서 정한 값)
- `lidar_configs` 의 `ip` → **LiDAR IP**
- 포트 번호는 건드리지 않는다

기본값이 `192.168.1.x` 대역이므로 전부 `192.168.123.x` 로 바꿔야 한다.

LiDAR IP 찾는 법 (MID-360 은 시리얼 번호로 끝자리가 정해져 고정값이 없다):

```bash
sudo apt install -y arp-scan
sudo arp-scan --interface=$G1_IFACE 192.168.123.0/24
```

### 5-4. 실행

```bash
source ~/ws_livox/install/setup.sh
ros2 launch livox_ros_driver2 rviz_MID360_launch.py
```

점이 안 보이면 RViz 의 Fixed Frame 을 `livox_frame` 으로 바꾼다.

퍼블리시되는 토픽:

| 토픽 | 타입 |
|---|---|
| `/livox/lidar` | `sensor_msgs/PointCloud2` |
| `/livox/imu` | `sensor_msgs/Imu` (MID-360 내장 IMU) |

> `xfer_format` (launch 파일 내): `0` = PointCloud2 (RViz2 시각화용),
> `1` = Livox 커스텀 포맷 (FAST-LIO 등 SLAM 패키지가 요구). 기본 `0`.

---

## 터미널 분리 규칙

**venv 와 ROS 2 를 같은 터미널에서 source 하지 않는다.** `PYTHONPATH` 가 섞인다.

| 터미널 | 준비 | 용도 |
|---|---|---|
| A | `g1` | 로봇 제어 스크립트 |
| B | `g1` | `g1_real_monitor.py watch` |
| C | `source /opt/ros/jazzy/setup.bash` | LiDAR / 카메라 / RViz2 |

---

## 설치 확인 체크리스트

- [ ] `python3 -c "import unitree_sdk2py; print('OK')"` → OK
- [ ] `g1` 실행 시 venv · CYCLONEDDS · 작업 폴더 표시
- [ ] `--dry-run` 3종 정상 출력
- [ ] `ros2 pkg list | grep livox` → `livox_ros_driver2`
- [ ] (로봇 연결 후) `g1` 에서 `G1_IFACE` 검출
- [ ] (로봇 연결 후) `ping 192.168.123.164` 응답
