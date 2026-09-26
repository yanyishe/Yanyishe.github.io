# -*- coding: utf-8 -*-
"""生成几段占位氛围音，放进 music/ 让播放器先有东西可放。

用法（在项目根目录）：
    python tools/make_placeholder_audio.py
    python tools/gen_music_manifest.py      # 再跑一次清单脚本

这几段是正弦叠加出来的氛围铺底，不是真正的乐曲 —— 只是让你在还没准备好
自己的音乐之前，能先把播放器、切歌、淡入淡出这套东西体验一遍。
换上自己的音乐后，把这里生成的 .wav 删掉、再跑一次清单脚本即可。

文件名刻意带了三种易错形态（中文 / 带空格 / 前导编号），顺带能验证
URL 编码和标题解析这两处：
  · 01-夜色低语.wav        -> 标题「夜色低语」（编号被剥掉）
  · 02-moonlit drift.wav   -> URL 里的空格会被编码成 %20
"""
import math
import os
import struct
import sys
import wave

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

SR = 16000
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "music")

SPECS = [
    ("01-夜色低语.wav", [220.0, 330.0, 440.0, 550.0], 8.0),
    ("02-moonlit drift.wav", [261.6, 392.0, 523.3], 8.0),
    ("03-静谧之门.wav", [146.8, 220.0, 293.7], 8.0),
]


def render(freqs, dur):
    n = int(SR * dur)
    frames = bytearray()
    for i in range(n):
        t = i / SR
        env = 0.55 + 0.45 * math.sin(2 * math.pi * 0.11 * t)   # 缓慢起伏，像呼吸
        edge = min(1.0, t / 0.6, (dur - t) / 0.6)              # 首尾淡化，免爆音
        s = 0.0
        for k, f in enumerate(freqs):
            s += math.sin(2 * math.pi * f * t) / (k + 1.6)
        v = int(max(-1.0, min(1.0, s * 0.28 * env * edge)) * 32767)
        frames += struct.pack("<h", v)
    return bytes(frames)


def main():
    if not os.path.isdir(OUT):
        os.makedirs(OUT)
    for name, freqs, dur in SPECS:
        path = os.path.join(OUT, name)
        w = wave.open(path, "wb")
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(render(freqs, dur))
        w.close()
        print("生成 %-24s %6.1f KB" % (name, os.path.getsize(path) / 1024.0))


if __name__ == "__main__":
    main()
