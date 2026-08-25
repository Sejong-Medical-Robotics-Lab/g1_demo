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
| LiDAR | **Livox MID-360s** (MID-360 아님 — 5장 참고) |
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
| `192.168.123.1` | 공유기 (공유기 경유 구성일 때) |
| `192.168.123.120` | **LiDAR (MID-360s)** — 사용 금지 |
| `192.168.123.161` | 운동제어 유닛 (PC1) — 사용 금지 |
| `192.168.123.164` | 개발 계산 유닛 (Jetson, PC2) — 사용 금지 |
| `192.168.123.51` | **우리 PC (고정)** |

로봇 쪽 주소는 전부 Unitree 가 출하 시 고정해 둔 값이라 바뀌지 않는다.
PC 만 우리가 정한다. **DHCP 로 받으면 재부팅마다 주소가 바뀌어 LiDAR config 를
매번 고쳐야 하므로 반드시 고정한다.**

기존 인터넷 설정을 건드리지 않도록 별도 프로파일로 만든다:

```bash
ip -o link show | grep -v lo:      # 인터페이스명 확인
nmcli con add type ethernet ifname <인터페이스명> con-name g1-wired \
  ipv4.method manual ipv4.addresses 192.168.123.51/24 ipv4.gateway 192.168.123.1
nmcli con up g1-wired
```

USB-이더넷 어댑터를 쓴다면 이름이 `enx` + MAC 형태다(예: `enx2c16dba6a7dc`).
어댑터가 `ip link` 에 안 보이면 `lsusb` 로 인식 여부부터 확인한다.

무선과 유선이 동시에 같은 대역에 있으면 경로가 헷갈리므로 무선은 끈다:

```bash
nmcli radio wifi off
```

확인:

```bash
g1                          # G1_IFACE 가 잡히는지
ping 192.168.123.161        # 운동제어 유닛 — 유선이면 0.3ms 수준
ping 192.168.123.120        # LiDAR
```

> **무선(공유기 경유)으로는 LiDAR 를 못 쓴다.** 제어 명령과 상태 스트림은
> 무선으로도 동작하지만, 포인트 클라우드는 초당 수십 MB 를 UDP 로 밀어내기
> 때문에 무선 구간에서 전부 유실된다(`tcpdump` 로 0 패킷 확인).

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

## 5. LiDAR (MID-360s)

> ### ★ 이 기체는 MID-360 이 아니라 **MID-360s** 다
>
> 겉모습과 포트 번호가 같아서 구분이 어렵지만 **config 형식과 launch 파일이
> 다르다.** 일반 MID-360 설정으로 실행하면 드라이버가
> `Init lds lidar success!` 까지는 찍고 **그 이후 아무 일도 일어나지 않는다** —
> RViz 는 비어 있고 `/livox/lidar` 토픽에 데이터가 없다.
>
> 반드시 `MID360s_config.json` + `rviz_MID360s_launch.py` 를 쓴다.

```
MID-360s ──UDP──> Livox-SDK2 ──> livox_ros_driver2 ──> /livox/lidar ──> RViz2
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

**master 를 쓴다.** MID-360s 지원(`mid360s_command_handler.cpp`)이 태그 릴리스에는
없다. v1.2.5 등 예전 태그로 내리면 드라이버가 요구하는 심볼
(`kLivoxLidarTypeMid360s`, `kLivoxLidarDoubleEchoData`)이 없어 빌드가 실패한다.

### 5-2. livox_ros_driver2

경로가 중요하다. 반드시 `[워크스페이스]/src/livox_ros_driver2` 여야 한다.

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

### 5-3. config 설정

**`MID360s_config.json` 을 편집한다** (`MID360_config.json` 아님).

```bash
nano ~/ws_livox/src/livox_ros_driver2/config/MID360s_config.json
```

우리 기체 확정값:

```json
{
  "lidar_summary_info" : { "lidar_type": 8 },
  "Mid360s": {
    "lidar_net_info" : { ... 포트는 그대로 ... },
    "host_net_info" : [
      { "host_ip" : "192.168.123.51", ... }
    ]
  },
  "lidar_configs" : [
    {
      "ip" : "192.168.123.120",
      "pcl_data_type" : 1,
      "pattern_mode" : 0,
      "extrinsic_parameter" : { "roll": 180.0, "pitch": 0.0, "yaw": 0.0, "x": 0, "y": 0, "z": 0 }
    }
  ]
}
```

주의할 점:

- **`lidar_type: 8` 은 건드리지 않는다.** 장치 타입이 아니라 프로토콜 인덱스다
  (드라이버 README: "please don't revise this value"). 9(=MID360 장치 타입)로
  바꿔도 증상은 그대로다.
- **`host_net_info` 가 배열**이고 `host_ip` 하나만 받는다. 일반 MID-360 은
  객체에 IP 4개(`cmd_data_ip`/`point_data_ip`/…)를 각각 적는 형식이라 다르다.
  이 차이가 두 모델을 구분하는 가장 확실한 표시다.
- **`roll: 180`** — G1 의 LiDAR 는 거꾸로 장착되어 있다. 이걸 안 하면
  포인트 클라우드가 뒤집혀 나온다.
- 포트 번호(56100/56200/56300/56400/56500)는 그대로 둔다.

**config 를 고친 뒤에는 반드시 재빌드한다.** launch 가 읽는 것은 `install/` 쪽
사본이라 `src/` 만 고치면 반영되지 않는다.

```bash
cd ~/ws_livox/src/livox_ros_driver2 && ./build.sh jazzy
```

### 5-4. 실행

```bash
lidar
ros2 launch livox_ros_driver2 rviz_MID360s_launch.py
```

정상이면 로그가 여기까지 진행된다:

```
Init lds lidar success!
GetFreeIndex key:livox_lidar_...
set pcl data type / set scan pattern
begin to change work mode to 'Normal'
successfully change work mode
successfully enable Livox Lidar imu
livox/lidar publish use PointCloud2 format
```

**`GetFreeIndex` 에서 멈추면 핸드셰이크 실패다** — config 모델이 안 맞는 것이다.

확인:

```bash
ros2 topic hz /livox/lidar   # 10 Hz
ros2 topic hz /livox/imu     # 200 Hz
```

퍼블리시되는 토픽:

| 토픽 | 타입 | 주파수 |
|---|---|---|
| `/livox/lidar` | `sensor_msgs/PointCloud2` | 10 Hz |
| `/livox/imu` | `sensor_msgs/Imu` (LiDAR 내장 IMU) | 200 Hz |

> `xfer_format` (launch 파일 내): `0` = PointCloud2 (RViz2 시각화용),
> `1` = Livox 커스텀 포맷 (FAST-LIO 등 SLAM 패키지가 요구). 기본 `0`.

### 5-5. 문제 해결 순서

증상별로 어디를 봐야 하는지:

| 증상 | 원인 |
|---|---|
| `bind failed` | config 의 `host_ip` 가 PC 의 실제 IP 와 다름 |
| `Init lds lidar success!` 이후 멈춤 | **config 모델 불일치** — MID360s 용을 쓸 것 |
| 토픽은 있는데 `hz` 0 | 포인트 데이터가 PC 에 도달하지 않음(무선 구간 등) |
| `hz` 는 나오는데 RViz 비어 있음 | RViz 의 Fixed Frame 을 `livox_frame` 으로 |
| 포인트가 뒤집힘 | `roll: 180` 누락 |

진단 도구:

```bash
# LiDAR 가 브로드캐스트를 보내고 있는가 (1초 주기, 48바이트)
sudo tcpdump -i <인터페이스> -n port 56000 -c 5

# 우리 PC 가 LiDAR 에 명령을 보내고 있는가 — 안 보내면 핸드셰이크 실패
sudo tcpdump -i <인터페이스> -n port 56100 -c 10

# 포인트 데이터가 실제로 도착하는가
sudo tcpdump -i <인터페이스> -n udp port 56300 -c 20

# 이전 프로세스가 포트를 붙들고 있지 않은가 (Ctrl+Z 로 멈춘 launch 주의)
sudo ss -unlp | grep 56000
pkill -9 -f livox_ros_driver2; pkill -9 -f rviz2
```

**launch 종료는 `Ctrl+C` 로 한다.** `Ctrl+Z` 는 프로세스를 백그라운드에 남겨
포트를 계속 점유하므로, 다음 실행이 조용히 실패한다.

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
- [ ] (로봇 연결 후) `ping 192.168.123.164` 응답, `ping 192.168.123.120` 응답
- [ ] `ros2 topic hz /livox/lidar` → 10 Hz
- [ ] `ros2 topic hz /livox/imu` → 200 Hz

## Jetson 쪽 확인 결과 (2026-08 실측)

| 항목 | 값 |
|---|---|
| OS | Ubuntu 20.04.6 LTS (aarch64, Tegra) |
| ROS | Foxy / Noetic 선택 프롬프트가 로그인 시 뜬다 |
| IP | `192.168.123.164` (eth0 고정) |
| 계정 | `unitree` / `123` |

**PC 는 Jazzy, Jetson 은 Foxy 로 배포판이 다르다.** 깊이 카메라(RealSense)를
쓰려면 Jetson 에서 노드를 띄우고 토픽만 PC 에서 구독해야 하는데, 이때
`ROS_DOMAIN_ID` 와 RMW 구현을 양쪽에서 맞춰야 한다. 아직 검증하지 않은 항목이다.
