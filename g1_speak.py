#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""g1_speak.py — 오프라인 TTS로 만든 음성을 G1 스피커로 재생 (로봇 TTS 우회)

로봇 내장 TTS(`AudioClient.TtsMaker`)는 중국어는 되지만 **한국어·영어는
소리 자체가 안 난다**(발음이 나쁜 게 아니라 무음). 그래서 텍스트를
로봇에 보내 합성시키는 대신, **PC 에서 직접 음성을 만들어 그 파형을
로봇 스피커로 흘려보낸다.**

    텍스트 → (PC, 오프라인) espeak-ng 로 음성 생성 → 16kHz/모노/16비트로 변환
           → AudioClient.PlayStream() 으로 로봇에 스트리밍

이 방식은 SDK 가 공식 예제로 제공하는 `PlayStream()` API 를 쓴다
(example/g1/audio/g1_audio_client_play_wav.py 참고). TtsMaker 를 아예
쓰지 않으므로 로봇 TTS 의 언어 지원과 무관하다.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
왜 espeak-ng 인가 — 완전 오프라인
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
설치 한 번(apt, 로봇 제어 PC 가 인터넷 될 때 미리)만 하면, **그 뒤로는
텍스트를 아무리 바꿔도 인터넷이 전혀 필요 없다.** gTTS(구글 서버 필요)
와 달리 로봇 현장에서 완전히 끊긴 상태로도 새 문장을 바로 만들 수 있다.

음질은 또박또박하지만 억양은 기계적이다("로봇 목소리" 느낌). 발표
안내 문구 정도의 짧은 문장에는 충분히 알아듣기 좋다.

**더 자연스러운 음성이 필요하면**: Piper TTS(신경망 기반, 훨씬 자연스러움)
로 바꿀 수 있다. 다만 음성 모델 파일(수십MB)을 huggingface.co 에서
**한 번은** 받아야 한다 — 그 이후엔 역시 완전 오프라인이다.

    pip install piper-tts
    python3 -m piper.download_voices ko_KR-hana-medium --download-dir ~/piper_voices
    # 인터넷 되는 곳에서 한 번만. 그 뒤 --engine piper 로 이 스크립트에 쓴다.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
준비
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    sudo apt install -y espeak-ng ffmpeg
    # (선택) pip install piper-tts   ← 더 자연스러운 음성을 원하면

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
사용
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    python3 g1_speak.py --iface $G1_IFACE --text "안녕하세요"
    python3 g1_speak.py --iface $G1_IFACE --text "Hello" --lang en
    python3 g1_speak.py --iface $G1_IFACE --wav ~/greeting.wav   # 이미 있는 wav 파일

    # 로봇 연결 없이 음성만 만들어서 PC 스피커로 미리 들어보기
    python3 g1_speak.py --text "안녕하세요" --preview-only

    # Piper 로 더 자연스러운 음성 (모델을 미리 받아뒀다면)
    python3 g1_speak.py --iface $G1_IFACE --text "안녕하세요" \\
        --engine piper --piper-model ~/piper_voices/ko_KR-hana-medium.onnx
"""
import argparse
import os
import subprocess
import struct
import sys
import tempfile
import time


def read_wav(filename):
    """16kHz/모노/16비트 PCM wav 만 읽는다. (SDK 예제의 wav.py 와 동일 로직)"""
    with open(filename, "rb") as f:
        def read(fmt):
            return struct.unpack(fmt, f.read(struct.calcsize(fmt)))

        chunk_id, = read("<I")
        if chunk_id != 0x46464952:
            sys.exit(f"[오류] RIFF 헤더가 아닙니다: {filename}")
        f.read(4)
        format_tag, = read("<I")
        if format_tag != 0x45564157:
            sys.exit(f"[오류] WAVE 형식이 아닙니다: {filename}")

        subchunk1_id, subchunk1_size = read("<II")
        if subchunk1_id == 0x4B4E554A:  # JUNK
            f.seek(subchunk1_size, 1)
            subchunk1_id, subchunk1_size = read("<II")
        if subchunk1_id != 0x20746D66:
            sys.exit("[오류] fmt 청크를 찾을 수 없습니다.")

        audio_format, = read("<H")
        num_channels, = read("<H")
        sample_rate, = read("<I")
        f.read(6)  # byte_rate, block_align
        bits_per_sample, = read("<H")
        if subchunk1_size == 18:
            f.read(2)

        if bits_per_sample != 16:
            sys.exit(f"[오류] 16비트가 아닙니다: {bits_per_sample}bit")

        while True:
            subchunk2_id, subchunk2_size = read("<II")
            if subchunk2_id == 0x61746164:
                break
            f.seek(subchunk2_size, 1)

        raw_pcm = f.read(subchunk2_size)
        return list(raw_pcm), sample_rate, num_channels


def synth_espeak(text, lang, out_wav):
    """espeak-ng 로 직접 wav 생성 후 ffmpeg 로 16kHz/모노/16비트 변환.
    완전 오프라인 — 인터넷 필요 없음."""
    raw_wav = tempfile.mktemp(suffix="_raw.wav")
    r = subprocess.run(["espeak-ng", "-v", lang, text, "-w", raw_wav],
                       capture_output=True, text=True)
    if r.returncode != 0 or not os.path.exists(raw_wav):
        sys.exit(f"\n  espeak-ng 실패:\n{r.stderr}\n"
                 "  설치 확인:  sudo apt install espeak-ng\n"
                 f"  지원 언어 목록:  espeak-ng --voices\n")

    r = subprocess.run(
        ["ffmpeg", "-y", "-i", raw_wav,
         "-ar", "16000", "-ac", "1", "-sample_fmt", "s16", out_wav],
        capture_output=True, text=True)
    os.unlink(raw_wav)
    if r.returncode != 0:
        sys.exit(f"\n  ffmpeg 변환 실패:\n{r.stderr[-500:]}\n")


def synth_piper(text, model_path, out_wav):
    """Piper(신경망 TTS)로 생성. 모델 파일은 사전에 huggingface 에서
    한 번 받아둬야 한다(인터넷 필요한 건 그 다운로드 순간뿐)."""
    if not os.path.exists(model_path):
        sys.exit(f"\n  Piper 모델이 없습니다: {model_path}\n"
                 "  인터넷 되는 곳에서 한 번만 받으세요:\n"
                 "    pip install piper-tts\n"
                 "    python3 -m piper.download_voices ko_KR-hana-medium "
                 "--download-dir ~/piper_voices\n")
    raw_wav = tempfile.mktemp(suffix="_raw.wav")
    r = subprocess.run(
        ["piper", "-m", model_path, "-f", raw_wav],
        input=text, capture_output=True, text=True)
    if r.returncode != 0 or not os.path.exists(raw_wav):
        sys.exit(f"\n  Piper 실패:\n{r.stderr}\n")

    r = subprocess.run(
        ["ffmpeg", "-y", "-i", raw_wav,
         "-ar", "16000", "-ac", "1", "-sample_fmt", "s16", out_wav],
        capture_output=True, text=True)
    os.unlink(raw_wav)
    if r.returncode != 0:
        sys.exit(f"\n  ffmpeg 변환 실패:\n{r.stderr[-500:]}\n")


def play_pcm_stream(client, pcm_list, stream_name="g1_speak",
                    chunk_size=96000, sleep_time=1.0):
    """SDK 예제(play_pcm_stream)와 동일한 방식으로 청크 전송."""
    pcm_data = bytes(pcm_list)
    stream_id = str(int(time.time() * 1000))
    offset, total = 0, len(pcm_data)
    n_chunks = (total + chunk_size - 1) // chunk_size
    print(f"  전송: {total:,} bytes, {n_chunks}개 청크")

    idx = 0
    while offset < total:
        chunk = pcm_data[offset:offset + chunk_size]
        code, _ = client.PlayStream(stream_name, stream_id, chunk)
        if code != 0:
            print(f"  [경고] 청크 {idx} 전송 실패 (code={code})")
        else:
            print(f"    청크 {idx+1}/{n_chunks} 전송 완료")
        offset += chunk_size
        idx += 1
        time.sleep(sleep_time)


def main():
    ap = argparse.ArgumentParser(
        description="오프라인 TTS로 만든 음성을 G1 스피커로 재생 (로봇 TTS 우회)")
    ap.add_argument("--iface", help="예: enp2s0 (--preview-only 아니면 필수)")
    ap.add_argument("--domain", type=int, default=0)
    ap.add_argument("--text", help="이 문장을 합성해서 재생")
    ap.add_argument("--lang", default="ko",
                    help="espeak-ng 언어 코드. ko=한국어 en=영어 (기본 ko). "
                         "전체 목록: espeak-ng --voices")
    ap.add_argument("--engine", choices=["espeak", "piper"], default="espeak",
                    help="espeak(기본, 설치만 하면 바로 됨) 또는 "
                         "piper(더 자연스러움, 모델 사전 다운로드 필요)")
    ap.add_argument("--piper-model", help="--engine piper 일 때 .onnx 모델 경로")
    ap.add_argument("--wav", help="합성 대신 이미 있는 wav 파일을 재생")
    ap.add_argument("--speaker", default="g1_speak", help="app_name(스트림 이름)")
    ap.add_argument("--chunk-sleep", type=float, default=1.0,
                    help="청크 사이 대기[s]. 재생이 끊기면 늘려본다 (기본 1.0)")
    ap.add_argument("--preview-only", action="store_true",
                    help="로봇 없이 wav 만 만들어 PC 스피커로 들어본다")
    ap.add_argument("--keep-wav", help="생성된 wav 를 이 경로에 저장(디버깅용)")
    args = ap.parse_args()

    if not args.text and not args.wav:
        sys.exit("--text 또는 --wav 중 하나는 필요합니다.")
    if not args.preview_only and not args.iface:
        sys.exit("--iface 가 필요합니다 (또는 --preview-only 로 로봇 없이 확인).")
    if args.engine == "piper" and not args.piper_model:
        sys.exit("--engine piper 는 --piper-model 경로가 필요합니다.")

    # ── wav 준비 ──────────────────────────────────────────────────────
    if args.wav:
        wav_path = args.wav
        print(f"  기존 wav 사용: {wav_path}")
    else:
        wav_path = args.keep_wav or tempfile.mktemp(suffix="_16k.wav")
        print(f"  {args.engine} 로 오프라인 합성 중... (인터넷 불필요)")
        if args.engine == "piper":
            synth_piper(args.text, args.piper_model, wav_path)
        else:
            synth_espeak(args.text, args.lang, wav_path)
        print(f"  생성됨: {wav_path}")

    pcm, sr, ch = read_wav(wav_path)
    print(f"  wav 확인: {sr}Hz, {ch}채널, {len(pcm):,} bytes"
          f" (재생 길이 약 {len(pcm)/2/sr:.1f}초)")
    if sr != 16000 or ch != 1:
        sys.exit(f"\n  [오류] 16kHz/모노가 아닙니다(sr={sr}, ch={ch}).\n"
                 "  --wav 로 직접 넣은 파일이라면 먼저 변환하세요:\n"
                 f"    ffmpeg -i input.wav -ar 16000 -ac 1 -sample_fmt s16 {wav_path}\n")

    if args.preview_only:
        print("\n  --preview-only : PC 스피커로 재생합니다 (로봇에는 안 보냄)")
        subprocess.run(["ffplay", "-nodisp", "-autoexit", wav_path],
                       capture_output=True)
        if not args.keep_wav:
            os.unlink(wav_path)
        return

    # ── 로봇 연결 및 전송 ────────────────────────────────────────────
    from unitree_sdk2py.core.channel import ChannelFactoryInitialize
    from unitree_sdk2py.g1.audio.g1_audio_client import AudioClient

    ChannelFactoryInitialize(args.domain, args.iface)
    client = AudioClient()
    client.SetTimeout(10.0)
    client.Init()

    print(f"\n  G1 스피커로 재생 시작...")
    play_pcm_stream(client, pcm, args.speaker, sleep_time=args.chunk_sleep)
    client.PlayStop(args.speaker)
    print("  완료")

    if not args.wav and not args.keep_wav:
        os.unlink(wav_path)


if __name__ == "__main__":
    main()

