# 사람 인식 파트 작업 계획 (웹캠만으로)

**담당**: 사람 인식 노드 개발
**필요한 것**: 노트북 + 웹캠. **로봇은 쓰지 않는다**
**목표**: 로봇이 사람을 보고 반응하게 하는 것의 **인식 쪽 절반**

---

## 0. 전체 그림 — 내 작업이 어디에 들어가나

```
    [Nav2 자율주행]  ── 목표 지점까지 이동           ← 다른 팀원
            ↓
    ★ [사람 인식]  ── "2m 앞 왼쪽에 사람이 있다"     ← 내 담당
            ↓
    [반응 모션]     ── 손 흔들기 등                  ← 다른 팀원
```

두 파트는 **`/person_detected` 토픽 하나로만** 연결된다(3장).
서로의 코드를 볼 필요가 없고, 각자 따로 테스트할 수 있다.

**로봇이 한 대뿐이라 자율주행 쪽이 계속 쓰고 있다.**
그래서 이 작업은 처음부터 끝까지 노트북 웹캠으로 진행한다.
나중에 카메라 토픽 이름만 바꾸면 로봇의 RealSense 로 그대로 넘어간다.

---

## 1. 무엇을 만드나

**입력**: 카메라 영상 토픽
**출력**: 사람의 위치(앞쪽 거리, 좌우 거리)를 담은 토픽

```
/image_raw  ──>  [내가 만들 노드]  ──>  /person_detected
 (웹캠)                                   (거리 · 방향)
```

노드 하나가 전부다. 검출 → 좌표 계산 → 발행.

---

## 2. 작업 순서

### 2-1. 환경 준비 (30분)

```bash
sudo apt install -y ros-jazzy-usb-cam ros-jazzy-cv-bridge
pip install ultralytics
```

웹캠이 뜨는지 확인:

```bash
source /opt/ros/jazzy/setup.bash
ros2 run usb_cam usb_cam_node_exe
```

다른 터미널에서:

```bash
source /opt/ros/jazzy/setup.bash
ros2 topic list                            # /image_raw 가 보이는가
ros2 run rqt_image_view rqt_image_view     # 영상이 보이는가
```

여기까지 되면 준비 끝.

### 2-2. 사람 검출 (반나절)

**YOLO 를 쓴다.** `ultralytics` 패키지로 몇 줄이면 된다.

```python
from ultralytics import YOLO
model = YOLO("yolov8n.pt")             # n = nano, 가장 가벼운 모델
results = model(frame, classes=[0])    # 0번 클래스 = person
```

먼저 **ROS 없이** 웹캠 영상만으로 사람이 잡히는지 확인한다.
`cv2.VideoCapture(0)` 로 직접 읽어 박스를 그려보면 된다.

여기서 확인할 것:
- 검출이 되는가
- 몇 fps 나오는가 (GPU 없으면 느릴 수 있다)
- 여러 명이 있을 때 어떻게 나오는가
- **상반신만 보일 때도 잡히는가** ← 나중에 중요해진다(6장)

> 너무 느리면 MediaPipe Pose 로 바꾼다. 가볍고 빠르지만 한 명만 검출된다.

### 2-3. ROS 노드로 만들기 (반나절)

`/image_raw` 를 구독해 검출하고 `/person_detected` 를 발행하는 노드.

```python
class PersonDetector(Node):
    def __init__(self):
        super().__init__("person_detector")
        self.create_subscription(Image, "/image_raw", self.on_image, 10)
        self.pub = self.create_publisher(PoseStamped, "/person_detected", 10)

    def on_image(self, msg):
        frame = self.bridge.imgmsg_to_cv2(msg, "bgr8")
        # YOLO 검출
        # 가장 가까운(= 박스가 가장 큰) 사람 하나 선택
        # 좌표 계산 → 발행
```

**주의**: 검출은 무겁다. 매 프레임 돌리면 밀린다.
2~3 프레임에 한 번만 처리하거나, 최신 프레임만 쓰고 밀린 건 버린다.

### 2-4. 위치 계산 — 이 작업의 핵심 (1일)

박스가 화면 어디 있는지에서 **실제 위치**를 추정해야 한다.

**좌우 방향 (y)** — 웹캠으로도 정확히 된다.

박스 중심의 x 픽셀 위치로 "카메라 중심에서 몇 도 벗어났는가"를 구한다.
카메라 수평 화각(FOV)을 알면 계산된다. 노트북 웹캠은 대개 60~70도.

```python
angle = (cx - width / 2) / (width / 2) * (FOV / 2)
```

**앞쪽 거리 (x)** — 웹캠에는 깊이 정보가 없다. **추정해야 한다.**

사람 키가 대략 일정하다는 가정을 쓴다. 멀수록 박스 높이(픽셀)가 작아지므로
역산할 수 있다.

```python
# 실제 사람 키 ≈ 1.7m 로 가정
distance = (1.7 * focal_length_px) / bbox_height_px
```

**한계를 알고 쓸 것:**
- 앉아 있거나 상반신만 보이면 크게 틀린다
- 키 차이만큼 오차가 난다
- 그래도 "2m 인가 5m 인가" 정도는 구분된다 → **데모에는 충분**

**보정 방법**: 줄자로 2m, 3m, 5m 를 재고 각 지점에서 박스 높이를 기록해
실제 값으로 맞춘다. 이게 제일 확실하다. **기록해서 문서에 남길 것.**

> 나중에 RealSense 를 붙이면 이 추정은 실제 측정값으로 대체된다.
> 그래서 **거리 계산은 함수 하나로 분리해두면** 교체가 쉽다.
>
> ```python
> def estimate_distance(bbox, depth_image=None):
>     if depth_image is not None:
>         return depth_from_sensor(bbox, depth_image)   # 나중에
>     return depth_from_bbox_height(bbox)               # 지금
> ```

### 2-5. 다듬기 (반나절)

**떨림 억제** — 검출 결과가 프레임마다 튄다. 이동평균 등으로 부드럽게.

**놓침 처리** — 잠깐 끊겨도 바로 "사람 없음"으로 바꾸지 않는다.
0.5초 정도는 이전 위치를 유지하는 편이 낫다.

**여러 명** — 가장 가까운(박스가 가장 큰) 한 명만 발행한다.

---

## 3. ★ 인터페이스 — 이것만 지키면 된다

다른 파트와의 유일한 접점.

```
토픽 이름 : /person_detected
메시지    : geometry_msgs/msg/PoseStamped
발행 조건 : 사람이 검출된 동안만. 없으면 발행하지 않는다
발행 주기 : 10 Hz

내용:
    header.frame_id    = "base_link"      (로봇 몸통 기준)
    header.stamp       = 검출 시각
    pose.position.x    = 앞쪽 거리 [m]     (양수 = 앞)
    pose.position.y    = 좌우 거리 [m]     (양수 = 왼쪽)
    pose.position.z    = 0.0
    pose.orientation.w = 1.0               (나머지 0, 사용 안 함)
```

**웹캠 단계에서도 이 형식을 그대로 지킨다.** 거리가 추정값일 뿐이다.

### 확인 방법

내 노드가 잘 내보내는지:

```bash
ros2 topic echo /person_detected
ros2 topic hz /person_detected
```

상대 파트를 테스트해주고 싶을 때 (가짜 값 발행):

```bash
ros2 topic pub -r 10 /person_detected geometry_msgs/msg/PoseStamped \
  "{header: {frame_id: 'base_link'}, pose: {position: {x: 2.0, y: 0.5}}}"
```

---

## 4. 산출물

| | 내용 |
|---|---|
| 코드 | `g1_person_detect.py` — 카메라 구독 → `/person_detected` 발행 |
| 문서 | 사용한 모델, 웹캠 FOV, 거리 보정 실측값, 검출 성능(fps) |
| 확인 | 웹캠 앞에서 움직일 때 값이 따라 변하는 영상/스크린샷 |

**저장소**: `Sejong-Medical-Robotics-Lab/g1_demo`
시작 전에 `OVERVIEW.md` 를 읽어볼 것 — 전체 개념과 지금까지의 흐름이 있다.

---

## 5. 일정 감각

| 단계 | 예상 |
|---|---|
| 2-1 환경 준비 | 30분 |
| 2-2 검출 확인 | 반나절 |
| 2-3 ROS 노드화 | 반나절 |
| 2-4 위치 계산 | 1일 |
| 2-5 다듬기 | 반나절 |

**전부 로봇 없이 가능하다.** 자율주행 쪽과 일정이 겹치지 않는다.

---

## 6. 나중에 (로봇이 여유 생기면)

지금은 안 하지만 언젠가 필요한 것들. **미리 알고 설계하면 나중이 편하다.**

**① 깊이 카메라(RealSense) 연결**
로봇 머리에 Intel D435i 가 달려 있지만 아직 한 번도 안 켜봤다.
Jetson(로봇 안 컴퓨터)에 USB 로 붙어 있어서, 거기서 노드를 띄우고
토픽만 우리 PC 에서 받아야 한다. **Jetson 은 Ubuntu 20.04 + ROS Foxy,
우리 PC 는 Jazzy** 라 배포판이 달라 이게 만만찮다.

→ 붙으면 2-4 의 거리 추정이 **실제 측정값**으로 바뀐다.

**② 카메라 조건 차이**
로봇 카메라는 높이 1.3m 에 있다. 노트북 웹캠(책상 위)과 시야가 다르고,
가까운 사람은 상반신만 보인다. 걸을 때 흔들리기도 한다.

→ **2-2 에서 상반신만 나오는 경우를 미리 테스트해두면** 나중에 덜 놀란다.

---

## 7. 이 프로젝트에서 지켜온 것

기존 코드와 문서에 일관되게 들어가 있는 원칙들.

**① 기능을 하나씩 독립적으로 검증한 뒤 통합한다.**
2-2(검출) → 2-3(ROS) → 2-4(좌표) 를 한꺼번에 만들지 말고 각각 확인하며 쌓는다.

**② 알아낸 값은 즉시 문서에 남긴다.**
공식 문서에 없는 값이 많았다(FSM 번호, LiDAR 모델 구분법 등).
다시 찾으려면 며칠이 걸린다. **웹캠 FOV, 거리 보정값도 반드시 기록할 것.**

**③ 에러 없이 조용히 실패하는 경우를 조심한다.**
LiDAR 도, 기립 실패도 에러 메시지가 없었다.
"성공한 것 같은데 아무 일도 안 일어나는" 상황이 제일 오래 걸린다.
`ros2 topic hz` 로 데이터가 실제로 흐르는지 확인하는 습관을 들일 것.

**④ 추측보다 관찰이 빠르다.**
LiDAR 문제로 세 시간을 썼는데, 원인을 추측해 계속 뭔가 바꿨기 때문이다.
"어떤 파일·옵션이 준비돼 있나"를 먼저 봤으면 10분이면 끝났다.

---

## 8. 막히면

- **반나절 이상 같은 곳에서 막히면 공유할 것.** 혼자 오래 붙잡지 않기
- 2-4(거리 추정)가 제일 애매한 부분이다. 정확도에 너무 매달리지 말 것 —
  **"가까이 있나 멀리 있나"만 구분되면 데모에는 충분하다**
