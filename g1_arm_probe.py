#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""g1_arm_probe.py — 팔 액션 하나씩 실행해 7404 원인을 좁히는 도구.

배경:
  G1 의 팔 동작에는 **서로 다른 두 창구**가 있다.

    ① LocoClient.WaveHand()/ShakeHand()  → SetTaskId (loco 서비스)
    ② G1ArmActionClient.ExecuteAction()  → action_map (arm 서비스)

  실기체에서 ①(wave)을 실행한 뒤 ②(hands up)를 부르면 code=7404 로 거부됐다.
  ①이 팔 제어권을 쥔 채 놓지 않기 때문으로 보인다.
  이 스크립트로 그 가설을 확인한다.

사용:
  python3 g1_arm_probe.py --iface wlo1 --list              # 목록 + 서비스 응답 확인
  python3 g1_arm_probe.py --iface wlo1 --action "hands up" # 이것 하나만 (wave 없이)
  python3 g1_arm_probe.py --iface wlo1 --sequence          # wave → 해제 → hands up
  python3 g1_arm_probe.py --iface wlo1 --release           # 팔 제어권 해제만

전제: 로봇이 레귤러 모드(FSM 200)로 서 있어야 한다.
      실패해도 Damp 로 내리지 않는다 — 자세를 유지한 채 끝난다.
"""
import argparse
import time

from g1_common import FSM, G1Link, banner, gate

RELEASE_TASK_ID = 99      # loco 쪽 팔 태스크 해제


def release_all(link, note=True):
    """두 창구 모두 팔 제어권을 놓게 한다."""
    if note:
        print("  팔 제어권 해제 —", end=" ")
    try:
        link.loco.SetTaskId(RELEASE_TASK_ID)    # loco 창구
        print("loco SetTaskId(99)", end=" ")
    except Exception as e:
        print(f"loco 실패({e})", end=" ")
    try:
        link.release_arm()                      # arm 창구 (action 99)
        print("/ arm release")
    except Exception as e:
        print(f"/ arm 실패({e})")
    time.sleep(1.0)


def run_action(link, name, wait):
    aid = link.action_map.get(name)
    if aid is None:
        print(f"  [실패] action_map 에 없음: '{name}'")
        return False
    print(f"\n  → ExecuteAction({name} = {aid})")
    code = link.arm.ExecuteAction(aid)
    if code == 0:
        print(f"      code=0 — 접수됨. {wait:.0f}초 관찰")
        time.sleep(wait)
        return True
    if code == 7404:
        print("      code=7404 — arm 서비스 거부. "
              "팔 제어권이 loco 쪽에 잡혀 있거나 현재 상태에서 불가.")
    else:
        print(f"      code={code} — 실패")
    return False


def main():
    ap = argparse.ArgumentParser(description="팔 액션 진단 (Damp 로 내리지 않음)")
    ap.add_argument("--iface")
    ap.add_argument("--domain", type=int, default=0)
    ap.add_argument("--action", help="실행할 액션 이름 (예: 'hands up')")
    ap.add_argument("--list", action="store_true", help="목록 + GetActionList 응답")
    ap.add_argument("--sequence", action="store_true",
                    help="wave → 해제 → hands up 순으로 가설 검증")
    ap.add_argument("--release", action="store_true", help="팔 제어권 해제만")
    ap.add_argument("--wait", type=float, default=8.0, help="동작 관찰 시간")
    args = ap.parse_args()

    banner("팔 액션 진단 — 두 창구(loco / arm) 충돌 확인")
    link = G1Link(args.iface, args.domain, with_arm=True)

    f = link.fsm()
    print(f"\n  현재 FSM: {link.fsm_text()}")
    if f is not None and f != FSM.MAIN_CONTROL:
        print(f"  [경고] 레귤러 모드(FSM {FSM.MAIN_CONTROL})가 아닙니다 — "
              "팔 액션이 거부될 수 있습니다.")

    if args.list:
        print("\n  SDK action_map:")
        for k, v in sorted(link.action_map.items(), key=lambda kv: kv[1]):
            print(f"    {v:>3d}  {k}")
        print("\n  실기체 GetActionList 응답:")
        try:
            code, data = link.arm.GetActionList()
            print(f"    code={code}")
            print(f"    {data}")
            if code != 0:
                print("    → 목록 조회조차 실패. arm 서비스 자체가 응답하지 않는 상태.")
        except Exception as e:
            print(f"    예외: {e}")
        return

    if args.release:
        release_all(link)
        return

    if args.sequence:
        gate("로봇이 레귤러 모드로 서 있고, 팔이 움직여도 안전합니까?")

        print("\n[1] 먼저 팔 제어권을 깨끗이 비운다")
        release_all(link)

        print("\n[2] arm 창구 단독 — wave 없이 'hands up'")
        ok_alone = run_action(link, "hands up", args.wait)
        release_all(link)

        print("\n[3] loco 창구 — WaveHand()")
        link.wave()
        print(f"      {args.wait:.0f}초 관찰")
        time.sleep(args.wait)

        print("\n[4] 해제 없이 곧바로 arm 창구 — 'hands up'")
        ok_no_release = run_action(link, "hands up", args.wait)

        print("\n[5] 해제 후 다시 arm 창구 — 'hands up'")
        release_all(link)
        ok_after_release = run_action(link, "hands up", args.wait)
        release_all(link)

        banner("진단 결과")
        print(f"  wave 없이 단독 실행      : {'성공' if ok_alone else '실패'}")
        print(f"  wave 직후 (해제 안 함)   : {'성공' if ok_no_release else '실패'}")
        print(f"  wave 후 해제하고 실행    : {'성공' if ok_after_release else '실패'}")
        print()
        if ok_alone and not ok_no_release and ok_after_release:
            print("  → 두 창구 충돌 확정. wave 와 arm 액션 사이에 해제를 넣으면 된다.")
        elif not ok_alone:
            print("  → wave 와 무관하게 arm 서비스가 거부. FSM 상태·서비스 자체를 의심.")
        else:
            print("  → 위 조합을 기록하고 판단할 것.")
        return

    if args.action:
        gate(f"'{args.action}' 을 실행합니다. 팔이 움직여도 안전합니까?")
        release_all(link)
        run_action(link, args.action, args.wait)
        release_all(link)
        return

    ap.print_help()


if __name__ == "__main__":
    main()
