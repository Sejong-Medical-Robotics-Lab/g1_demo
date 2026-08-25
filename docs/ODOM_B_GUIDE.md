# B안 — 내장 오도메트리 이식 가이드

목표: 오도메트리를 FAST-LIO(라이다 10Hz)에서 **로봇 내장**(관절+IMU,
고주파)으로 교체 → 라이다 파이프라인 지연이 위치추정에 전파되던
구조를 제거. AMCL·지도·costmap·브리지·절차는 전부 그대로.

받을 파일 4개: check_odomstate.py / g1_odom_bridge.py /
g1_nav2_odomB.launch.py / nav2_g1_odomB.yaml → 전부 ~/g1_real/ 에.
(기존 파일은 안 건드림 — A안과 나란히 시험 가능)

---

## 0단계 — 펌웨어가 내장 오도메트리를 쏘는지 확인 (1분, 필수)

```bash
python3 ~/g1_real/check_odomstate.py --iface $G1_IFACE
```
- [성공] + 로봇을 살짝 밀면 pos 값이 변함 → 진행
- [실패] 10초 무수신 → **여기서 중단**, 결과 공유 (다른 토픽명 조사 필요)

## 1단계 — 라이다 PointCloud2 출력판 만들기 (한 번만)

FAST-LIO 없이 원시 점구름을 쓰려면 드라이버가 표준 형식
(PointCloud2)으로 내보내야 한다 (기존 msg_판은 FAST-LIO 전용 형식):

```bash
cd ~/ws_livox/src/livox_ros_driver2/launch_ROS2
cp msg_MID360s_launch.py pc2_MID360s_launch.py
grep -n "xfer_format" pc2_MID360s_launch.py     # 값이 1 인 줄 확인
sed -i 's/xfer_format = 1/xfer_format = 0/' pc2_MID360s_launch.py
cd ~/ws_livox && colcon build --packages-select livox_ros_driver2 && source install/setup.bash
```

확인:
```bash
ros2 launch livox_ros_driver2 pc2_MID360s_launch.py   # 띄워두고 다른 터미널에서
ros2 topic info /livox/lidar     # → Type: sensor_msgs/msg/PointCloud2 여야 함
```

## 2단계 — 기동 (터미널 4개)

```
lidar → ros2 launch livox_ros_driver2 pc2_MID360s_launch.py
g1    → python3 ~/g1_real/g1_odom_bridge.py --iface $G1_IFACE
g1ros → python3 ~/g1_real/g1_cmdvel_bridge.py --iface $G1_IFACE
slam  → ros2 launch ~/g1_real/g1_nav2_odomB.launch.py
```
(FAST-LIO 는 안 띄운다!)

건강 확인:
```bash
ros2 topic hz /odom      # 수십 Hz 이상
ros2 topic hz /scan      # ~10Hz
```

## 3단계 — 스캔 방향 검증 (첫 실행 때 필수, 2분)

RViz 에서 초기 위치를 찍기 **전에**, Fixed Frame 을 base_link 로
잠깐 바꾸고 스캔을 본다:

- 로봇 정면의 벽/복도가 스캔에서도 **앞쪽**에 있는가?
- 로봇 오른쪽 벽이 스캔에서도 **오른쪽**인가? (거울 반전 체크)

**뒤집혀 보이면**: launch 파일의 base_to_livox 노드를 roll 180 판
(파일 안 주석에 있음)으로 교체 후 재시작. 맞으면 Fixed Frame 을
map 으로 되돌리고 진행.

## 4단계 — 평소 절차로 시험

초기 위치(안 되면 set_pose.sh) → clearmap → 직진 → clearmap → 복귀.

**판정: 회전 중 스캔이 벽에 붙은 채 매끈하게 도는가.**
내장 오도메트리는 지연이 거의 없어서, A안의 "회전 중 보정 동결"
없이도(nav2_g1_odomB.yaml 은 update_min_a 를 원래 감각으로 되돌려
써도 됨) 톱니가 사라지는 게 기대 동작이다. 일단은 현재 값(6.28,
동결)이 복사돼 있으니 그대로 첫 판 → 매끈하면 성공.

---

## 정직한 주의사항

- **왜곡보정(deskew) 상실**: FAST-LIO 가 해주던 스캔 왜곡보정이
  없어진다. 0.12m/s·0.3rad/s 저속에선 프레임당 1~2cm/1.7도 수준이라
  AMCL 허용 범위지만, 고속으로 올리면 다시 검토 필요.
- **내장 오도메트리의 드리프트 특성은 우리 로봇에서 미검증**
  (erasers G1 에선 검증됨). 보행 미끄러짐이 크면 AMCL 보정 부담이
  늘 수 있다 — 0단계에서 조이스틱로 1m 걷게 하고 pos 가 실제
  이동량과 비슷한지 눈대중 확인해두면 좋다.
- livox_frame 의 z(0.50)는 대략값 — 2D 매칭엔 yaw 만 중요해서
  z 오차는 무해. 3단계의 좌우 반전 체크가 진짜 관문이다.
