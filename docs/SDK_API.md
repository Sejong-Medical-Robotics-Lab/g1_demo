# Unitree SDK2 Python — G1 API 정리

`unitree_sdk2py` 로 G1 을 제어할 때 쓰는 클라이언트와 명령 목록.
실기체(2026-08, mode_machine=5)에서 관측한 값을 함께 기록한다.

## 클라이언트 구성

| 클라이언트 | 담당 | 파일 |
|---|---|---|
| `LocoClient` | FSM 전이 + 보행 + 자세 + 간단한 팔(wave, shake) | `g1/loco/g1_loco_client.py` |
| `G1ArmActionClient` | 팔 동작 23종 | `g1/arm/g1_arm_action_client.py` |
| `AudioClient` | TTS · 볼륨 · RGB LED | `g1/audio/g1_audio_client.py` |

```python
from unitree_sdk2py.g1.loco.g1_loco_client import LocoClient
from unitree_sdk2py.g1.arm.g1_arm_action_client import G1ArmActionClient, action_map
from unitree_sdk2py.g1.audio.g1_audio_client import AudioClient
```

---

## 번호 체계는 세 가지 — 섞어 쓰지 말 것

같은 숫자라도 **어느 함수에 넣느냐**에 따라 뜻이 완전히 다르다.

| 함수 | 소속 | 성격 | 예 |
|---|---|---|---|
| `SetFsmId(n)` | LocoClient | **상태** 전환 — 계속 유지된다 | 1 = Damp |
| `SetTaskId(n)` | LocoClient | **일회성** 동작 | 1 = 몸 돌리며 손 흔들기 |
| `ExecuteAction(n)` | ArmActionClient | **일회성** 팔 동작 | 1 = turn_back_wave |

`1` 하나만 봐도 셋 다 다른 뜻이다. 각 체계 안에서는 번호가 유일하므로
실제 사용에는 문제가 없지만, **한 체계의 ID 를 다른 함수에 옮겨 쓰면 안 된다.**

> 실제로 겪은 사고: `action_map["release arm"] = 99` 를 보고
> `SetTaskId(99)` 도 release 겠거니 하고 넣었다가 원인 불명의 오동작을 겪었다.
> `SetTaskId` 쪽 99 는 검증된 값이 아니다.

---

## FSM — 상태 기계

`SetFsmId(n)` / `GetFsmId()`

정해진 경로로만 이동할 수 있다. 허용되지 않는 전이는 코드 0 을 반환하면서도
FSM 이 바뀌지 않는다 — **반환 코드만으로 성공을 판단하면 안 된다.**

### 확정 사슬

```
0 (전원 인가) → 1 Damp → 4 Lock Stand → 501 레귤러 모드
```

| FSM | 이름 | SDK 래퍼 | 가능한 것 |
|---|---|---|---|
| 0 | ZeroTorque | `ZeroTorque()` | 힘 완전 없음 — 서 있을 때 보내면 주저앉는다 |
| 1 | Damp | `Damp()` | 감쇠 — 알려진 안전 상태 |
| 2 | Squat | 없음 | 쭈그림 |
| 3 | Sit | `Sit()` | 앉기 |
| 4 | **Lock Stand** | **없음** | 관절 잠그고 기립(레디) |
| 200 | MainControl | 없음 | **보행만** — 팔 액션은 7404 거부 |
| 500 | Start | `Start()` | **이 기체에서는 전이 자체가 안 됨** |
| **501** | **레귤러** | **없음** | **보행 + 팔 액션 모두 가능** |
| 702 | Lie2StandUp | `Lie2StandUp()` | 누운 상태에서 기립 |
| 706 | Squat↔Stand | `Squat2StandUp()` / `StandUp2Squat()` | 같은 ID 토글. Damp 직후에는 거부됨 |

### 주의사항

- **4 와 501 은 SDK 에 래퍼가 없다.** `SetFsmId(4)`, `SetFsmId(501)` 로 직접 보낸다.
- **래퍼 함수들은 반환값이 없다(None).** `Damp()` 는 내부에서 `SetFsmId(1)` 을
  호출하지만 그 코드를 돌려주지 않으므로, 거부를 잡으려면 `SetFsmId` 를 직접 부른다.
- **706 은 토글이다.** 서 있는 상태에서 다시 보내면 앉는다.
- 조이스틱 R1+Y 로 들어가는 "레귤러 모드"가 FSM 501 이다.

---

## 보행

| 함수 | 설명 |
|---|---|
| `SetVelocity(vx, vy, vyaw, duration)` | **반환 코드 있음** — 권장 |
| `Move(vx, vy, vyaw)` | `SetVelocity(..., duration=1)` 과 같다 |
| `Move(vx, vy, vyaw, continous_move=True)` | duration=864000초(10일) — **위험** |
| `StopMove()` | 속도 0 |
| `SetSpeedMode(n)` | 속도 모드 |
| `SetSwingHeight(h)` | 발 드는 높이 |

`vx` 전후 / `vy` 좌우 / `vyaw` 회전 [rad/s].

**데드맨 패턴**: `duration` 을 짧게(0.5초) 주고 그보다 빠른 주기(0.2초)로 재전송한다.
프로세스가 죽거나 통신이 끊기면 로봇이 스스로 멈춘다. `continous_move=True` 는
그 반대로 동작하므로 쓰지 않는다.

## 자세

| 함수 | 설명 |
|---|---|
| `SetStandHeight(h)` | 서 있는 높이 |
| `HighStand()` / `LowStand()` | 위 함수의 최대/최소값 |
| `SetBalanceMode(n)` | 균형 모드 |

## 조회

`GetFsmId()`, `GetFsmMode()`, `GetBalanceMode()`, `GetStandHeight()`, `GetSwingHeight()`
— 모두 `(code, value)` 튜플을 반환한다.

## 건드리지 말 것

`SwitchToUserCtrl()` / `SwitchToInternalCtrl()` — Unitree 내부 제어를 끊는 스위치다.
저수준 제어(`rt/lowcmd`)로 갈 때 필요하지만, 잘못 쓰면 로봇이 힘을 잃는다.

---

## LocoClient 의 팔 동작 (SetTaskId 경로)

| 함수 | 내부 | 비고 |
|---|---|---|
| `WaveHand()` | `SetTaskId(0)` | 손 흔들기 |
| `WaveHand(True)` | `SetTaskId(1)` | 몸 돌리며 흔들기 |
| `ShakeHand(stage)` | `SetTaskId(2/3)` | 악수 — 단계별 호출 필요 |

**이 경로는 되도록 쓰지 않는 편이 낫다.** ArmActionClient 에 같은 동작이
더 많이 있고, 두 창구를 섞으면 제어권 문제를 의심하게 된다.
`WaveHand()` 는 ID 25(`wave_under_head`) 나 26(`wave_above_head`) 으로,
`WaveHand(True)` 는 ID 1(`turn_back_wave`) 로 대체할 수 있어 보인다.

---

## 팔 액션 (ExecuteAction 경로)

```python
arm = G1ArmActionClient()
arm.SetTimeout(10.0)
arm.Init()
arm.ExecuteAction(action_map["hands up"])   # = 15
arm.ExecuteAction(action_map["release arm"]) # = 99, 끝나면 반드시 반납
```

**FSM 501 에서만 동작한다.** 200 에서 호출하면 `code=7404` 로 거부된다.
`GetActionList()` 자체는 200 에서도 정상 응답(code=0)하므로,
7404 를 서비스 장애로 오해하지 말 것.

### SDK action_map 에 있는 것 (이름으로 호출)

| ID | SDK 이름 | 실기체 이름 |
|---|---|---|
| 11 | two-hand kiss | blow_kiss_with_both_hands |
| 12 | left kiss | blow_kiss_with_left_hand |
| 13 | right kiss | blow_kiss_with_right_hand |
| 15 | hands up | both_hands_up |
| 17 | clap | clamp |
| 18 | high five | high_five |
| 19 | hug | hug |
| 20 | heart | make_heart_with_both_hands |
| 21 | right heart | make_heart_with_right_hand |
| 22 | reject | refuse |
| 23 | right hand up | right_hand_up |
| 24 | x-ray | ultraman_ray |
| 25 | face wave | wave_under_head |
| 26 | high wave | wave_above_head |
| 27 | shake hand | shake_hand |
| 99 | release arm | release_arm |

### 실기체에만 있는 것 (ID 로만 호출)

`GetActionList()` 는 SDK `action_map` 보다 많은 액션을 보고한다.

| ID | 이름 | 조건 |
|---|---|---|
| 1 | turn_back_wave | `fsm: [500, 501]` |
| 28 | box_left_hand_win | `mode_machine: [5, 6]` |
| 29 | box_right_hand_win | `mode_machine: [5, 6]` |
| 30 | box_both_hand_win | `mode_machine: [5, 6]` |
| 33 | right_hand_on_heart | |
| 34 | both_hands_up_deviate_right | |
| 36 | forward_push | `mode_machine: [5, 6]` |

`mode_machine` 은 기체 구성 조건이다. 우리 기체는 5 이므로 모두 통과한다
(`g1_real_monitor.py precheck` 의 `mode_machine=5` 로 확인).

### 댄스 모션 (별도 배열, ID 없음)

`GetActionList()` 응답의 두 번째 배열에 이름과 재생 시간만 들어 있다.

| 이름 | 길이 |
|---|---|
| Waist_Drum_Dance | 9.5s |
| Scratch_head | 8.1s |
| Spin_discs | 6.9s |
| Throw_money | 8.1s |
| 2026-07-14_13:50:30 | 7.4s |

마지막 것은 날짜 이름인 것으로 보아 누군가 직접 만들어 저장한 모션으로 보인다.
ID 가 없어 `ExecuteAction` 으로는 호출할 수 없을 가능성이 크다 — 호출 방법 미확인.

---

## AudioClient

| 함수 | 설명 |
|---|---|
| `TtsMaker(text, speaker_id)` | 음성 합성 |
| `SetVolume(n)` / `GetVolume()` | 0~100 |
| `LedControl(r, g, b)` | RGB LED |

**TTS 는 한국어를 지원하지 않고 영어도 발음이 부정확하다.** 모드 전환 안내는
로봇 자체 내장 음성에 맡기고, 스크립트는 LED 색만 바꾸는 편이 낫다.

**SDK 버그**: `TtsMaker` 안의 `self.tts_index += self.tts_index` 는 0 에서
시작하면 영원히 0 이다. `client.tts_index = 1` 로 초기화하면 1,2,4,8… 로 증가한다.

---

## 에러 코드

### RPC (`unitree_sdk2py/rpc/internal.py`)

| 코드 | 뜻 |
|---|---|
| 3102 | 전송 실패 |
| 3103 | API 미등록 |
| **3104** | **응답 시간 초과 — 통신 문제** (전이 거부가 아니다) |
| 3105 | API 불일치 |
| 3106 | 데이터 오류 |
| 3107 | lease 무효 |

3104 는 "명령이 안 갔다"가 아니라 "답을 못 받았다"는 뜻이다. 명령 자체는
도착했을 수 있으므로, 상태를 다시 읽어 확인한 뒤 재시도한다.

### arm 서비스 (SDK 에 정의 없음 — 실기체 관측)

| 코드 | 뜻 |
|---|---|
| **7404** | 현재 FSM 에서 해당 액션이 허용되지 않음 (FSM 200 에서 팔 액션 호출 시) |

---

## 요약 — 실무 규칙

1. FSM 전이는 `SetFsmId` 를 직접 호출한다. 래퍼는 반환값이 없다.
2. 반환 코드 0 이 전이 성공을 뜻하지 않는다. `GetFsmId` 로 확인하되,
   그것도 실패할 수 있으므로 **최종 판정은 육안 확인**이다.
3. 팔 액션은 FSM 501 에서만 된다.
4. 팔 동작은 ArmActionClient 로 통일한다. LocoClient 의 wave/shake 와 섞지 않는다.
5. 액션 실행 후에는 `release arm`(99) 으로 제어권을 반납한다.
6. 보행은 `SetVelocity` + 짧은 duration 재전송(데드맨)으로만 한다.
