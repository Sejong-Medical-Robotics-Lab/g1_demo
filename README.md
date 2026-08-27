## 젯슨 접속 및 depth camera server on

```jsx
 $ ssh unitree@192.168.123.164
 #pw: 123 , foxy(1)
 $ PYTHONPATH=$HOME/librealsense/build/Release python3 ~/g1_rgbd_server.py
```

- pose

!Screenshot from 2026-08-25 15-13-55.png

```python
# MediaPipe Pose 랜드마크 번호
NOSE = 0
MOUTH_LEFT, MOUTH_RIGHT = 9, 10
L_SHOULDER, R_SHOULDER = 11, 12
L_ELBOW, R_ELBOW = 13, 14
L_WRIST, R_WRIST = 15, 1
```

- hand

!Screenshot from 2026-08-25 15-12-06.png

```python

# MediaPipe Hands 랜드마크 번호 (Holistic 의 left_hand_landmarks/right_hand_landmarks)
HAND_WRIST = 0
HAND_THUMB_TIP = 4
HAND_INDEX_TIP = 8
HAND_INDEX_MCP = 5
HAND_MIDDLE_TIP = 12
HAND_MIDDLE_MCP = 9
HAND_RING_TIP = 16
HAND_RING_MCP = 13
HAND_PINKY_TIP = 20
HAND_PINKY_MCP = 17
```

- holistic

!image.png

## ID	SDK 이름	실기체 이름

```python
11	two-hand kiss	blow_kiss_with_both_hands
12	left kiss	blow_kiss_with_left_hand
13	right kiss	blow_kiss_with_right_hand
15	hands up	both_hands_up
17	clap	clamp
18	high five	high_five
19	hug	hug
20	heart	make_heart_with_both_hands
21	right heart	make_heart_with_right_hand
22	reject	refuse
23	right hand up	right_hand_up
24	x-ray	ultraman_ray
25	face wave	wave_under_head
26	high wave	wave_above_head
27	shake hand	shake_hand
99	release arm	release_arm
```

# g1_interaction_controller.py

- 기존 pose_action.py에 음성 출력 과 음성인식을 병합함
- 안전거리 판별 알고리즘을 추가함.

g1_pose_action.py 와 g1_speech.py, g1_person_distance.py는 동일파일에 있어야함.

# 포즈 맵

```python
POSE_ACTION_MAP = {
    "right_hand_up":   (ACTION_RIGHT_HAND_UP, "G1 오른손 올리기"),
    "right_hand_wave": (ACTION_WAVE,          "G1 오른손 흔들기"),
    "left_hand_up":    (ACTION_LEFT_HAND_UP,  "G1 왼손 올리기 (오른손 액션으로 대신 실행)"),
    "left_hand_wave":  (ACTION_WAVE,          "G1 왼손 흔들기 (오른손 액션으로 대신 실행)"),
    "both_hands_up":   (ACTION_BOTH_HANDS_UP, "G1 양팔 올리기"),
    "two_hand_kiss":   (ACTION_TWO_HAND_KISS, "G1 양손 뽀뽀"),
    "left_kiss":       (ACTION_LEFT_KISS,     "G1 왼손 뽀뽀"),
    "right_kiss":      (ACTION_RIGHT_KISS,    "G1 오른손 뽀뽀"),
    "two_hand_heart":  (ACTION_TWO_HAND_HEART, "G1 양손 하트"),
    "xray":            (ACTION_XRAY,           "G1 엑스레이 (울트라맨 광선)"),
}
```

# 음성 인식

```python
COMMAND_MAP = [
(["뽀뽀", "키스"],                    ACTION_TWO_HAND_KISS,  "양손 뽀뽀"),
(["왼손 뽀뽀"],                       ACTION_LEFT_KISS,      "왼손 뽀뽀"),
(["오른손 뽀뽀"],                     ACTION_RIGHT_KISS,     "오른손 뽀뽀"),
(["만세", "양손 들어", "손 들어"],      ACTION_BOTH_HANDS_UP,  "양손 올리기"),
(["박수", "짝짝"],                    ACTION_CLAP,           "박수"),
(["하이파이브", "하이 파이브"],         ACTION_HIGH_FIVE,      "하이파이브"),
(["안아줘", "허그", "포옹"],            ACTION_HUG,            "허그"),
(["하트", "사랑해"],                   ACTION_TWO_HAND_HEART, "양손 하트"),
(["오른손 하트"],                     ACTIONq_RIGHT_HEART,    "오른손 하트"),
(["싫어", "거절", "안돼"],              ACTION_REJECT,         "거절"),
(["오른손 들어"],                     ACTION_RIGHT_HAND_UP,  "오른손 올리기"),
(["레이저", "울트라맨", "액션빔"],       ACTION_XRAY,           "엑스레이"),
(["얼굴 흔들어"],                     ACTION_FACE_WAVE,      "얼굴 앞 흔들기"),
(["흔들어", "안녕", "인사"],            ACTION_WAVE,           "손 흔들기"),
(["악수"],                           ACTION_SHAKE_HAND,     "악수"),
(["그만", "놓아", "릴리즈", "release"], ACTION_RELEASE,        "팔 제어권 반납"),
]
```
