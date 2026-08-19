#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""g1_audio_test.py — G1 스피커(TTS) · LED 단독 확인.

로봇을 '움직이지 않는다'. 관절 명령을 하나도 보내지 않으므로
행어 없이도, 앉아 있는 상태에서도 안전하게 실행할 수 있다.
그래서 실기체를 처음 만졌을 때 통신 확인용으로도 쓸 만하다.

확인 목적:
  ① 스피커에서 소리가 나는가
  ② 한국어 TTS 가 되는가  ← 이게 이 스크립트의 핵심 확인 항목
  ③ LED 색이 바뀌는가

사용:
  python3 g1_audio_test.py --iface enp2s0
  python3 g1_audio_test.py --iface enp2s0 --volume 70
  python3 g1_audio_test.py --iface enp2s0 --say "안녕하세요"   # 한 문장만
  python3 g1_audio_test.py --iface enp2s0 --led 255 0 0        # 색 하나만
"""
import argparse
import sys
import time

from g1_common import LED, G1Link, banner

# 언어별 확인 문장 — 어떤 언어가 되는지 귀로 판별한다.
PHRASES = [
    ("한국어", "안녕하세요. 유니트리 지원 로봇입니다."),
    ("English", "Hello. This is a Unitree G1 humanoid robot."),
    ("中文", "你好，我是宇树科技人形机器人。"),
]


def main():
    ap = argparse.ArgumentParser(description="G1 오디오·LED 단독 확인 (관절 명령 없음)")
    ap.add_argument("--iface", required=True, help="예: enp2s0")
    ap.add_argument("--domain", type=int, default=0)
    ap.add_argument("--volume", type=int, default=70, help="0~100")
    ap.add_argument("--speaker", type=int, default=0, help="speaker_id (기본 0)")
    ap.add_argument("--say", help="이 문장만 말하고 종료")
    ap.add_argument("--led", nargs=3, type=int, metavar=("R", "G", "B"),
                    help="이 색만 켜고 종료")
    ap.add_argument("--wait", type=float, default=6.0,
                    help="문장 사이 대기 [s] — TTS 는 완료 신호가 없다")
    args = ap.parse_args()

    banner("G1 오디오 · LED 확인 (로봇은 움직이지 않습니다)")

    link = G1Link(args.iface, args.domain, with_arm=False,
                  with_audio=True, volume=args.volume)
    if link.audio is None:
        sys.exit("오디오 클라이언트 초기화 실패 — 연결/서비스 상태를 확인하세요.")

    # 현재 볼륨 확인
    try:
        code, vol = link.audio.GetVolume()
        print(f"\n  볼륨 조회: code={code}, {vol}")
    except Exception as e:
        print(f"\n  볼륨 조회 실패: {e}")

    # ── 단발 모드 ──
    if args.led:
        link.led(tuple(args.led))
        print(f"  LED → RGB{tuple(args.led)}")
        return
    if args.say:
        link.say(args.say, args.speaker)
        print(f'  TTS → "{args.say}"')
        time.sleep(args.wait)
        return

    # ── 전체 확인 ──
    print("\n[1] 언어별 TTS — 어느 것이 제대로 들리는지 기록하세요")
    for name, text in PHRASES:
        print(f"\n  {name}: {text}")
        link.say(text, args.speaker)
        for r in range(int(args.wait), 0, -1):
            print(f"      … 재생 대기 {r}s   ", end="\r", flush=True)
            time.sleep(1)
        print(" " * 40, end="\r")
        ans = input(f"      {name} 정상적으로 들렸습니까? (y/n) > ").strip().lower()
        print(f"      → {name}: {'OK' if ans == 'y' else '실패/부정확'}")

    print("\n[2] LED 색 확인 — 각 2초")
    for state in ("damp", "standing", "balance", "arm", "walk"):
        rgb = LED[state]
        print(f"  {state:<9s} RGB{rgb}")
        link.led(state)
        time.sleep(2.0)
    link.led("off")
    print("  LED off")

    print("\n[3] 데모 진행 문구 리허설")
    demo = [
        ("damp",     "댐프 모드로 전환합니다."),
        ("standing", "기립합니다."),
        ("balance",  "균형 제어 상태입니다."),
        ("arm",      "인사하겠습니다."),
        ("walk",     "전진하겠습니다."),
    ]
    for state, text in demo:
        print(f"  [{state}] {text}")
        link.announce(text, state)
        time.sleep(args.wait * 0.7)
    link.led("off")

    print("\n  확인 완료 — 되는 언어와 적절한 대기 시간을 기록해 두세요.")


if __name__ == "__main__":
    main()
