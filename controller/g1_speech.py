#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""g1_speech.py — G1 스피커로 미리 만들어둔 wav 를 비동기로 재생한다.

g1_P_A_action.py 에서 액션을 쏠 때 같이 호출해서, 동작 + 음성이 함께
나가게 하는 용도다.

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
"""

import os
import threading
import time
import wave

APP_NAME = "g1_action"
CHUNK_BYTES = 32000      # 16kHz * 2byte = 1초치
BYTES_PER_SEC = 32000.0


class Speaker:
    """액션 ID → wav 파일 매핑을 갖고, 비동기로 재생한다.

    audio_client 가 None 이면(=dry-run) 로그만 찍고 아무것도 안 한다.
    """

    def __init__(self, audio_client, speech_map, wav_dir="speech", volume=85):
        self.client = audio_client
        self.speech_map = speech_map
        self.wav_dir = wav_dir
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
                self._pcm_cache[action_id] = self._load_pcm(path)
                secs = len(self._pcm_cache[action_id]) / BYTES_PER_SEC
                print(f"    [음성출력] {fname} 로드 ({secs:.1f}초)")
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

    def _play(self, pcm):
        try:
            with self._lock:
                sent = 0
                t0 = time.time()
                for off in range(0, len(pcm), CHUNK_BYTES):
                    chunk = pcm[off:off + CHUNK_BYTES]
                    self.client.PlayStream(APP_NAME, str(self._stream_id), chunk)
                    self._stream_id += 1
                    sent += len(chunk)

                    # 실시간보다 조금만 앞서가게 페이싱 (한꺼번에 밀면 잘린다)
                    lag = sent / BYTES_PER_SEC - (time.time() - t0)
                    if lag > 0.2:
                        time.sleep(lag - 0.2)

                remain = sent / BYTES_PER_SEC - (time.time() - t0)
                if remain > 0:
                    time.sleep(remain + 0.2)
                self.client.PlayStop(APP_NAME)
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
