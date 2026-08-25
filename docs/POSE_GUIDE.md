# 4단계 — 사람 자세 인식과 대응 동작

시나리오 4단계. **모방이 아니라 대응**이다 — 사람의 관절 각도를 로봇 관절에
실시간으로 복사하는 것이 아니라, 미리 정한 몇 가지 행동을 판별해서
그에 맞는 G1 의 사전 정의 동작을 실행한다.

자율주행(3단계)과는 **독립된 단계**다. 이 단계에서 로봇은 제자리에 서 있고
팔만 움직인다. Nav2 도 보행도 쓰지 않는다.

---

## 구조

```
[Jetson]  RealSense → JPEG → MJPEG (HTTP 8080)
              ↓
[PC]      영상 → MediaPipe Pose → 관절 좌표 → 행동 판별
              ↓
          Unitree SDK → G1 팔 액션
```

**ROS 를 쓰지 않는다.** Jetson 은 Foxy(2020), PC 는 Jazzy(2024)라 같은
도메인에 두면 DDS 규약 차이로 노드가 죽는다. 그리고 MediaPipe 는
aarch64(Jetson)에 설치하기 어렵고 x86_64(PC)에서는 한 줄로 끝난다.
**영상만 HTTP 로 넘기고 무거운 일은 PC 가 한다.**

자세한 경위는 [CAMERA_SETUP.md](CAMERA_SETUP.md) 4장.

---

## 동작 대응표

| 사람 행동 | G1 동작 | 액션 ID |
|---|---|---|
| 오른손 올림 | 오른손 올리기 | 23 `right_hand_up` |
| 왼손 올림/흔듦 | 손 흔들기 | 26 `wave_above_head` |
| 양손 올림 | 양팔 올리기 | 15 `both_hands_up` |
| (종료 시) | 팔 제어권 반납 | 99 `release arm` |

**팔 액션은 FSM 501(레귤러 모드)에서만 동작한다.** 200 에서 부르면
`code=7404` 로 거부된다.

---

## 준비 (한 번만)

### Jetson

```bash
sudo apt install -y python3-opencv
```

파일 전송 (PC 에서):

```bash
scp ~/g1_real/g1_cam_server.py unitree@192.168.123.164:~/
```

### PC

```bash
g1
pip install opencv-python
pip install "mediapipe==0.10.14"
```

> **★ 버전을 못 박는다.** `pip install mediapipe` 로 받는 최신(1.0.x)에는
> `mp.solutions` 가 없다. 최신 MediaPipe 는 Tasks API 로 옮겨가면서 예전
> 방식을 뺐다. Tasks API 는 모델 파일을 따로 받아야 해서 번거롭다.

---

## 실행 — 터미널 3개

### ① Jetson 카메라 서버

```bash
ssh unitree@192.168.123.164        # 비번 123, ROS 프롬프트에 1
cd ~
python3 g1_cam_server.py
```

컬러 장치를 자동으로 찾는다. 잘못 고르면 `--device N` 으로 지정한다.

**확인**: PC 브라우저에서 `http://192.168.123.164:8080`

### ② 로봇 기립

```bash
g1
python3 g1_stand_test.py --iface $G1_IFACE
```

FSM 501 까지. 조이스틱으로 이미 레귤러 모드면 생략한다.

### ③ 자세 인식

**먼저 인식만** (로봇 팔은 안 움직인다):

```bash
g1
python3 ~/g1_real/g1_pose_action.py --dry-run
```

여기서 **카메라 각도를 맞춘다.** 사람 상반신(어깨~손)이 화면에 들어와야 한다.

**실전**:

```bash
python3 ~/g1_real/g1_pose_action.py --iface $G1_IFACE
```

`q` 또는 `Esc` 로 종료. 종료 시 팔 제어권을 자동 반납한다.

---

## 판정 방식

- 같은 자세가 **6프레임 연속**(약 0.5초) 잡혀야 인정한다 — 순간 오검출 차단
- 동작 실행 후 **8초간** 새 명령을 받지 않는다 — G1 팔 액션이 3~8초 걸린다
- 관절 신뢰도(`visibility`)가 0.6 미만이면 무시한다
- 화면 상단에 판별 결과, 그 아래 진행 막대, 하단에 쿨다운이 표시된다

### 좌우 주의

MediaPipe 의 `LEFT`/`RIGHT` 는 **사람 기준**이다. 거울처럼 보이는 화면상의
좌우와 반대다. 사람이 오른손을 들면 G1 도 오른손을 든다.

### 높이 판정

MediaPipe 좌표계는 **y 가 아래로 갈수록 커진다.**
"손이 어깨보다 위" = `wrist.y < shoulder.y` 다.

---

## 안전

- 로봇은 제자리에 서 있고 **팔만** 움직인다. 보행 명령을 보내지 않는다
- **팔이 크게 움직이므로 주변에 사람이 없어야 한다.** 행어도 확인한다
- 한 동작이 끝날 때까지 다음 동작을 받지 않는다
- 종료 시 팔 제어권을 반납한다(액션 99)

---

## 문제 해결

| 증상 | 확인 |
|---|---|
| `module 'mediapipe' has no attribute 'solutions'` | 버전이 1.0.x다. `pip install "mediapipe==0.10.14"` |
| `프레임 수신 실패` 반복 | Jetson 에서 `g1_cam_server.py` 가 떠 있는지. 브라우저로 먼저 확인 |
| 웹캠(`--source 0`)이 안 열림 | `ls /dev/video*` — PC 에 웹캠이 없을 수 있다. 로봇 카메라로 진행 |
| 뼈대가 안 그려짐 | 사람 상반신이 화면에 들어오는지. 카메라 각도 조정 |
| 판별은 되는데 팔이 안 움직임 | FSM 501 인지 확인. 200 이면 `code=7404` 로 거부된다 |
| 영상이 느림 | `--quality 50`, 해상도 축소. 또는 유선 연결 확인 |
| Jetson 카메라 장치를 잘못 고름 | `python3 g1_cam_server.py --list` 로 후보 확인 후 `--device N` |

---

## 확장 여지

**왼손 "흔들기"는 현재 단순화되어 있다.** 흔드는 움직임을 판별하려면
시간에 따른 손목 x 좌표의 진동을 봐야 하는데, 지금은 "왼손을 든 상태"로
처리한다. 필요하면 `classify()` 에 최근 N 프레임의 `wrist.x` 변화를
추가로 검사하면 된다.

**동작을 늘리려면** `ACTION_MAP` 에 항목을 추가하고 `classify()` 에 판별
조건을 넣는다. 쓸 수 있는 팔 액션 22종은 [SDK_API.md](SDK_API.md) 참고.

**깊이(depth)** 는 현재 쓰지 않는다. 사람이 카메라 앞에 서 있으면 되고
거리 판단이 필요 없기 때문이다. 필요해지면 Jetson 쪽에서 깊이 스트림을
켜고 별도 채널로 넘기면 된다.
