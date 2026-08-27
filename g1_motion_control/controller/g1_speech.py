#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""g1_speech.py — G1 스피커로 미리 만들어둔 wav 를 비동기로 재생한다.

g1_interaction_controller.py 에서 액션을 쏠 때 같이 호출해서, 동작 + 음성이
함께 나가게 하는 용도다.

왜 별도 스레드인가:
    PlayStream 은 오디오 길이만큼 시간이 걸린다. try_trigger() 안에서
    그냥 재생하면 카메라 루프(메인 스레드)가 그 시간만큼 멈춰서 화면이
    얼어붙는다. 그래서 say() 는 스레드에 던지고 즉시 리턴한다.

왜 wav 인가:
    G1 내장 TtsMaker 는 중국어 전용이라 한국어를 못 낸다. 한국어를
    내려면 미리 만든 16kHz/mono/16bit wav 를 PlayStream 으로 밀어넣어야
    한다.

음성 파일 만들기 (노트북에서 미리, 로봇에 올려두기):
    pip install edge-tts
    edge-tts --voice ko-KR-SunHiNeural --text "안녕하세요!" --write-media t.mp3
    ffmpeg -i t.mp3 -ar 16000 -ac 1 -c:a pcm_s16le speech/hello.wav

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
말 잘림 문제를 이 파일 하나로 시험하는 법 (컨트롤러 없이)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    g1
    python3 g1_speech.py --wav speech/hello.wav                # 기본(한 번에 전송)
    python3 g1_speech.py --wav speech/hello.wav --chunk 32000  # 예전처럼 쪼개서
    python3 g1_speech.py --wav speech/hello.wav --no-stop      # PlayStop 안 부름
    python3 g1_speech.py --wav speech/hello.wav --raw          # 패딩·대기 전부 끄고 원본만

  기본(--chunk 0)으로 안 잘리면 원인은 청크 쪼개기였다 — 기기는 새 청크를
  받으면 재생 중이던 버퍼를 버리기 때문에, 잘리는 길이가 lead 와 같아진다.
  기본으로도 잘리는데 --no-stop 이면 멀쩡하다면 범인은 PlayStop 이다.
  --raw 로도 잘리면 원인은 코드가 아니라 wav 나 기기 쪽이다.
"""

import argparse
import os
import sys
import threading
import time
import wave

APP_NAME = "g1_action"
BYTES_PER_SEC = 32000.0  # 16kHz * 2byte

# ── 기본값 ────────────────────────────────────────────────────────────
# 이 네 개가 "말이 잘리는" 현상의 조절 손잡이 전부다. 기기마다 버퍼
# 사정이 달라서 정답이 하나가 아니다 — 위 자체 시험 모드로 찾아라.
CHUNK_BYTES = 0          # 0 = 쪼개지 않고 한 번에 전송(기본). 아주 긴 wav 를
                         #     쓸 때만 32000(1초치) 같은 값으로 켠다
LEAD_S = 0.2             # 쪼개서 보낼 때만 쓰는 값. 실시간보다 이만큼 앞서 보낸다
TAIL_PAD_S = 0.3         # 파형 뒤에 붙일 무음. 잘리는 게 음절이 아니라 무음이 되게
STOP_GUARD_S = 0.5       # 전송이 끝나도 이만큼 더 기다렸다가 PlayStop


class Speaker:
    """액션 ID → wav 파일 매핑을 갖고, 비동기로 재생한다.

    audio_client 가 None 이면(=dry-run) 로그만 찍고 아무것도 안 한다.
    """

    def __init__(self, audio_client, speech_map, wav_dir="speech", volume=85,
                 tail_pad_s=TAIL_PAD_S, stop_guard_s=STOP_GUARD_S,
                 lead_s=LEAD_S, chunk_bytes=CHUNK_BYTES,
                 call_stop=True, debug=False):
        self.client = audio_client
        self.speech_map = speech_map
        self.wav_dir = wav_dir
        self.tail_pad_s = tail_pad_s
        self.stop_guard_s = stop_guard_s
        self.lead_s = lead_s
        self.chunk_bytes = int(chunk_bytes)   # 0 이하면 쪼개지 않는다
        self.call_stop = call_stop
        self.debug = debug
        self._lock = threading.Lock()
        self._speaking = threading.Event()
        self._stream_id = 0
        self._pcm_cache = {}

        if self.client is not None and volume is not None:
            try:
                self.client.SetVolume(volume)
            except Exception as e:
                print(f"    [음성출력] 볼륨 설정 실패: {e}")

        self._preload()

    # ── 준비 ────────────────────────────────────────────────────────────
    def _preload(self):
        """시작할 때 wav 를 전부 읽어 검증한다 — 데모 중에 파일 문제로
        놀라는 것보다 시작할 때 알고 가는 게 낫다."""
        for action_id, fname in self.speech_map.items():
            path = os.path.join(self.wav_dir, fname)
            try:
                pcm = self._load_pcm(path)
                secs = len(pcm) / BYTES_PER_SEC
                self._pcm_cache[action_id] = self._pad_tail(pcm)
                padded = len(self._pcm_cache[action_id]) / BYTES_PER_SEC
                print(f"    [음성출력] {fname} 로드 ({secs:.1f}초 → 패딩 후 {padded:.1f}초)")
            except Exception as e:
                print(f"    [음성출력] {path} 로드 실패 — 이 액션은 무음: {e}")

    @staticmethod
    def _load_pcm(path):
        with wave.open(path, "rb") as w:
            fmt = (w.getframerate(), w.getnchannels(), w.getsampwidth())
            pcm = w.readframes(w.getnframes())
        if fmt != (16000, 1, 2):
            raise ValueError(
                f"16kHz/mono/16bit 이어야 함 (현재 {fmt[0]}Hz/{fmt[1]}ch/{fmt[2]*8}bit). "
                "ffmpeg -ar 16000 -ac 1 -c:a pcm_s16le 로 변환하세요.")
        return pcm

    def _pad_tail(self, pcm):
        """파형 뒤에 무음을 붙이고 청크 크기의 배수로 맞춘다.

        무음 패딩: PlayStop 이 잘라먹는 꼬리가 '진짜 음절'이 아니라
                   '무음'이 되게 한다.
        배수 정렬: 마지막 조각이 chunk 보다 짧으면 기기가 아예 안 실어
                   보내는 경우가 있어 0 으로 채워 꽉 채운다.
        tail_pad_s 가 0 이면 둘 다 안 한다(원본 그대로).
        """
        if self.tail_pad_s <= 0:
            return pcm

        pad = int(BYTES_PER_SEC * self.tail_pad_s)
        pad -= pad % 2                      # 16bit 샘플 경계 유지
        pcm = pcm + b"\x00" * pad

        rem = len(pcm) % self.chunk_bytes if self.chunk_bytes > 0 else 0
        if rem:
            pcm += b"\x00" * (self.chunk_bytes - rem)
        return pcm

    # ── 재생 ────────────────────────────────────────────────────────────
    def is_speaking(self):
        return self._speaking.is_set()

    def say(self, action_id):
        """액션 ID에 매핑된 음성을 비동기로 재생한다. 즉시 리턴."""
        pcm = self._pcm_cache.get(action_id)
        if pcm is None:
            return False
        if self.client is None:
            print(f"    [음성출력][dry-run] {self.speech_map[action_id]} 재생했다 치기")
            return True
        if self._speaking.is_set():
            # 이미 말하는 중이면 겹치지 않게 버린다. PlayStream 을 동시에
            # 두 개 밀어넣으면 소리가 섞여서 알아들을 수 없게 된다.
            print("    [음성출력] 이미 재생 중 — 이번 건 건너뜀")
            return False

        self._speaking.set()
        threading.Thread(target=self._play, args=(pcm,), daemon=True).start()
        return True

    def play_pcm_blocking(self, pcm):
        """자체 시험용. 재생이 끝날 때까지 기다린다."""
        self._speaking.set()
        self._play(pcm)

    def _play(self, pcm):
        try:
            with self._lock:
                # ── stream_id 는 발화 하나당 하나 ──────────────────────
                # 예전엔 청크마다 새 id 를 붙였는데, 기기는 새 id 를 받으면
                # "새 스트림"으로 보고 재생 중이던 버퍼를 버린다. 그래서
                # 다음 청크를 보내는 순간 직전 청크의 아직 안 나간 부분
                # (= 딱 lead_s 만큼)이 사라졌다. 잘리는 길이가 lead_s 와
                # 같았던 이유가 이것이다. 마지막 청크에서 이게 일어나면
                # 그 사라지는 부분이 곧 마지막 음절이다.
                self._stream_id += 1
                stream_id = str(self._stream_id)

                t0 = time.time()
                total_s = len(pcm) / BYTES_PER_SEC

                if self.chunk_bytes <= 0 or len(pcm) <= self.chunk_bytes:
                    # 기본 경로: 통째로 한 번에 보낸다. 인사말 정도 길이면
                    # 100KB 도 안 되니 쪼갤 이유가 없고, 쪼개지 않으면
                    # 위 문제가 일어날 여지 자체가 없다.
                    self.client.PlayStream(APP_NAME, stream_id, pcm)
                    if self.debug:
                        print(f"      [전송] {len(pcm)}B ({total_s:.2f}초) 한 번에, "
                              f"stream_id={stream_id}")
                else:
                    sent = 0
                    for off in range(0, len(pcm), self.chunk_bytes):
                        chunk = pcm[off:off + self.chunk_bytes]
                        self.client.PlayStream(APP_NAME, stream_id, chunk)
                        sent += len(chunk)

                        if self.debug:
                            print(f"      [chunk] {sent/BYTES_PER_SEC:5.2f}s 분량 전송, "
                                  f"경과 {time.time()-t0:5.2f}s, "
                                  f"앞선 정도 {sent/BYTES_PER_SEC-(time.time()-t0):+.2f}s")

                        if self.lead_s is not None:
                            wait = (sent / BYTES_PER_SEC - self.lead_s) - (time.time() - t0)
                            if wait > 0:
                                time.sleep(wait)

                # 다 보냈다 ≠ 다 나왔다. 남은 재생 시간만큼 기다린다.
                remain = total_s - (time.time() - t0)
                if remain > 0:
                    time.sleep(remain)
                if self.stop_guard_s > 0:
                    time.sleep(self.stop_guard_s)

                if self.call_stop:
                    self.client.PlayStop(APP_NAME)
                if self.debug:
                    print(f"      [끝] 총 {time.time()-t0:.2f}s "
                          f"(PlayStop {'호출' if self.call_stop else '생략'})")
        except Exception as e:
            print(f"    [음성출력] 재생 실패: {e}")
        finally:
            self._speaking.clear()

    def close(self):
        if self.client is not None:
            try:
                self.client.PlayStop(APP_NAME)
            except Exception:
                pass


# ══════════════════════════════════════════════════════════════════════
# 자체 시험 모드 — 컨트롤러 없이 이 파일만 돌려서 잘림 원인을 좁힌다
# ══════════════════════════════════════════════════════════════════════

def _self_test():
    ap = argparse.ArgumentParser(description="G1 스피커 재생 시험")
    ap.add_argument("--wav", required=True, help="16kHz/mono/16bit wav 경로")
    ap.add_argument("--iface", help="예: enx... (CYCLONEDDS_URI 설정 시 생략 가능)")
    ap.add_argument("--domain", type=int, default=0)
    ap.add_argument("--volume", type=int, default=85)
    ap.add_argument("--chunk", type=int, default=CHUNK_BYTES,
                    help="0 이면 쪼개지 않고 한 번에 전송(기본)")
    ap.add_argument("--lead", type=float, default=LEAD_S)
    ap.add_argument("--pad", type=float, default=TAIL_PAD_S)
    ap.add_argument("--guard", type=float, default=STOP_GUARD_S)
    ap.add_argument("--no-stop", action="store_true", help="PlayStop 을 아예 안 부른다")
    ap.add_argument("--raw", action="store_true",
                    help="패딩·페이싱 전부 끄고 원본을 그대로 밀어넣는다")
    ap.add_argument("--repeat", type=int, default=1)
    args = ap.parse_args()

    if args.raw:
        args.pad, args.guard = 0.0, 0.0
        lead = None
    else:
        lead = args.lead

    from unitree_sdk2py.core.channel import ChannelFactoryInitialize
    from unitree_sdk2py.g1.audio.g1_audio_client import AudioClient

    if os.environ.get("CYCLONEDDS_URI"):
        ChannelFactoryInitialize(args.domain)
    else:
        if not args.iface:
            sys.exit("--iface 가 필요합니다 (또는 g1 으로 CYCLONEDDS_URI 설정).")
        ChannelFactoryInitialize(args.domain, args.iface)

    client = AudioClient()
    client.SetTimeout(10.0)
    client.Init()

    sp = Speaker(client, {}, volume=args.volume,
                 tail_pad_s=args.pad, stop_guard_s=args.guard,
                 lead_s=lead, chunk_bytes=args.chunk,
                 call_stop=not args.no_stop, debug=True)

    pcm = sp._load_pcm(args.wav)
    print(f"\n  원본 {len(pcm)/BYTES_PER_SEC:.2f}초")
    pcm = sp._pad_tail(pcm)
    print(f"  전송 {len(pcm)/BYTES_PER_SEC:.2f}초 "
          f"(chunk={args.chunk}B, lead={lead}, pad={args.pad}s, "
          f"guard={args.guard}s, PlayStop={'생략' if args.no_stop else '호출'})\n")

    for i in range(args.repeat):
        if args.repeat > 1:
            print(f"  --- {i+1}/{args.repeat} ---")
        sp.play_pcm_blocking(pcm)
        time.sleep(0.5)

    print("\n  끝. 마지막 음절이 들렸는지 귀로 확인하세요.\n")


if __name__ == "__main__":
    _self_test()
