# G1 실기체 데모 — 파일 구성

로봇 연결 전에 준비한 파일들. `~/g1_real/` 에 두고 사용한다.

## 파일

| 파일 | 단계 | 역할 |
|---|---|---|
| `g1_env.sh` | 전체 | 터미널 준비 (venv + CYCLONEDDS_HOME + 인터페이스 자동 탐지) |
| `g1_common.py` | 전체 | 공통 래퍼 — FSM 전이·보행·팔 반납, 반환코드 검사 |
| `g1_stand_test.py` | 1 | Damp → 기립 → 균형 제어 단독 검증 |
| `g1_walk_test.py` | 2 | 보행 단독 검증 (데드맨 방식) |
| `g1_real_sequence.py` | 2·3 | 주 실행 파일 — 전이 + 상체 + (검증 후) 보행 |
| `g1_imu_view.py` | 전체 | 내장 IMU 실시간 확인 (읽기 전용) |
| `g1_audio_test.py` | 전체 | 스피커(TTS)·LED 확인 — 관절 명령 없음 |
| `g1_real_monitor.py` | 전체 | 기존 모니터 (precheck / baseline / watch) |

## 터미널 구성

**터미널 A — 제어 (venv)**
```bash
source ~/g1_real/g1_env.sh
python3 ~/g1_real/g1_stand_test.py --iface $G1_IFACE
```

**터미널 B — 모니터 (venv)**
```bash
source ~/g1_real/g1_env.sh
python3 ~/g1_real/g1_real_monitor.py watch --iface $G1_IFACE
```

**터미널 C — ROS 2 (4단계 이후, venv 와 섞지 말 것)**
```bash
source /opt/ros/jazzy/setup.bash
```

## 진행 순서

```
1단계  g1_stand_test.py --dry-run          # 로봇 없이 계획 확인
       g1_stand_test.py --iface … --list-actions
       g1_stand_test.py --iface …          # 전이만
       g1_stand_test.py --iface … --with-arm
         ↓  관측 FSM 값을 TRANSITIONS 에 반영
2단계  g1_real_sequence.py --dry-run
       g1_real_sequence.py --iface … --operator 이름
         ↓
3단계  g1_walk_test.py --iface … --vx 0.2 --sec 3
       g1_walk_test.py --iface … --preset forward_stop_turn
         ↓
4단계  SEQUENCE 에 move/stop 행 추가
       g1_real_sequence.py --iface … --enable-walk
         ↓
5단계  g1_imu_view.py → LiDAR(RViz2) → 깊이 카메라(Jetson 경유)
```

## 원본에서 바꾼 것 (`g1_real_sequence.py`)

1. **전이가 실패해도 못 잡던 문제 수정.**
   `LocoClient.Damp()/Start()/Squat2StandUp()` 은 내부에서 `SetFsmId()` 를 부르지만
   **반환값이 없다(None).** 원본의 `check_code(self.loco.Damp(), ...)` 는 항상 통과했다.
   `TRANSITIONS` 를 메서드명 대신 FSM ID 로 바꾸고 `SetFsmId()` 를 직접 호출해
   반환 코드를 검사한다.

2. **`706` 토글 경고 명시.**
   `Squat2StandUp` 과 `StandUp2Squat` 은 **같은 ID(706)** 다. 이미 서 있는 상태에서
   다시 보내면 앉는다.

3. **팔 액션 뒤 `release arm`(ID 99) 자동 전송.** 보행 전·시퀀스 종료 전에도 호출.

4. **`move` / `stop` 행 지원** — 단, `--enable-walk` 없이는 거부된다.
   속도는 안전 상한(`vx 0.3 / vy 0.2 / vyaw 0.4`)으로 자동 clamp.

5. **`safe_damp` 에 `stop_move` + `release_arm` 선행.**

## 보행 데드맨 (중요)

`Move()` 를 쓰지 않는다.

- `Move(vx,vy,vyaw)` = `SetVelocity(..., duration=1)` → 1초만 걷고 멈춤
- `Move(..., continous_move=True)` = **duration 864000초(10일)** → 스크립트가 죽어도 계속 걸음

대신 `SetVelocity(vx, vy, vyaw, duration=0.5)` 를 **0.2초 주기로 재전송**한다.
프로세스가 죽거나 통신이 끊기면 0.5초 안에 로봇이 스스로 멈춘다.

## 실기체 확정값 (2026-08 실측)

| 항목 | 값 |
|---|---|
| 전이 사슬 | `0(전원) → 1 Damp → 4 Lock Stand → 200 레귤러 모드` |
| 레귤러 모드 | **FSM 200** — 조이스틱 R1+Y 와 같은 모드 |
| `Start()` (=500) | **통하지 않음** — FSM 이 4 에서 바뀌지 않는다 |
| `Squat2StandUp()` (=706) | Damp 직후 거부됨 — 기립 경로는 4 |
| Lock Stand(4) | SDK 에 래퍼 없음 — `SetFsmId(4)` 직접 호출 |
| TTS | 한국어 미지원, 영어도 부정확 → **로봇 내장 음성 사용** |

보행·팔 액션은 FSM 200 에서만 동작한다.

## 음성 · LED (`--audio`)

`AudioClient` 로 TTS 와 RGB LED 를 제어한다. **오디오는 실패해도 제어 흐름을
막지 않는다** — 초기화나 호출이 실패하면 경고만 찍고 조용히 넘어간다.

```bash
python3 g1_audio_test.py --iface $G1_IFACE          # 먼저 단독 확인
python3 g1_stand_test.py --iface $G1_IFACE --audio
python3 g1_real_sequence.py --iface $G1_IFACE --operator 이름 --audio
```

LED 색 규약:

| 색 | 상태 |
|---|---|
| 빨강 | Damp / 이상·중단 |
| 주황 | 기립 전이 중 |
| 초록 | 균형 제어(정상) |
| 파랑 | 상체 동작 중 |
| 보라 | 보행 중 |

**우리 TTS 는 기본으로 꺼져 있다.** 실기체에서 한국어는 재생되지 않고 영어도
발음이 부정확했다. 모드 전환 안내는 **로봇 자체 내장 음성**(레디/레귤러 등)에
맡기고, 스크립트는 LED 색만 바꾼다.

굳이 우리 문구를 읽히려면 `--tts` 를 준다(중국어는 정상 동작).
`g1_audio_test.py` 로 언어별 재생을 다시 확인할 수 있다.

**SDK 버그 우회:** `AudioClient.TtsMaker()` 안의 `tts_index += tts_index` 는
0 에서 시작해 영원히 0 이다(증가하지 않음). `tts_index = 1` 로 초기화해 두었다.

## CYCLONEDDS_URI 우회 (Ubuntu 24.04 필수)

`ChannelFactoryInitialize(domain, iface)` 처럼 **인터페이스 이름을 인자로 넘기면
C 레벨에서 죽는다** — `*** buffer overflow detected ***`.

원인: SDK 가 인터페이스 이름을 받았을 때 만드는 설정 XML
(`unitree_sdk2py/core/channel_config.py` 의 `ChannelConfigHasInterface`)에만
`<Tracing><OutputFile>/tmp/cdds.LOG</OutputFile></Tracing>` 블록이 있다.
인터페이스 없이 호출하는 `ChannelConfigAutoDetermine` 에는 이 블록이 없어서
정상 동작한다.

그래서 이 저장소의 스크립트는 **`CYCLONEDDS_URI` 가 설정되어 있으면 인터페이스
인자를 넘기지 않는다.** `g1_env.sh` 가 `G1_IFACE` 를 찾아 자동으로 export 한다.

```bash
g1                      # CYCLONEDDS_URI : 설정됨 (interface=...) 이 뜨면 정상
python3 g1_imu_view.py  # --iface 생략 가능
```

수동으로 지정하려면:

```bash
export CYCLONEDDS_URI='<CycloneDDS><Domain id="any"><General><Interfaces><NetworkInterface name="wlo1" priority="default" multicast="default"/></Interfaces></General></Domain></CycloneDDS>'
```

### ROS 2 와 같은 터미널을 쓰지 말 것

ROS 2 Jazzy 는 cyclonedds 0.10.4, Unitree SDK 는 0.10.2 를 쓴다. ROS 를 source 한
셸에서는 라이브러리가 섞여 같은 크래시가 난다. `~/.bashrc` 에서 ROS 워크스페이스
`setup.bash` 들을 모두 주석 처리하고, ROS 가 필요한 터미널에서만 직접 source 한다.
(워크스페이스 `setup.bash` 는 내부에서 기반 ROS 환경까지 불러오므로
`/opt/ros/jazzy` 줄만 막는 것으로는 부족하다.)

```bash
echo "[$ROS_DISTRO]"    # 제어 터미널에서는 [] 여야 한다
```

## 로봇 연결 후 확정해야 할 값

- [ ] 기립 완료 시 실제 FSM 관측값 (`4` 인지 `706` 인지)
- [ ] 균형 제어 진입 시 실제 FSM 관측값 (`500` 인지 `200` 인지)
- [ ] `GetActionList` 실기체 응답 ↔ SDK `action_map` 대조
- [ ] 관절 수 (`g1_real_monitor.py --joints`, 기본 29)
- [ ] LiDAR IP (`ip neigh`), Jetson(`192.168.123.164`) OS·ROS 배포판
- [ ] TTS 지원 언어(한국어 되는지)와 문장별 재생 소요 시간
