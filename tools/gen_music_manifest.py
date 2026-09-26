# -*- coding: utf-8 -*-
"""扫描 music/ 目录，生成 music/manifest.js。

用法（在项目根目录）：
    python tools/gen_music_manifest.py

加歌就两步：把音频文件丢进 music/，跑一下这个脚本。

## 封面

**给某首歌配封面，就在 music/ 里放一张同名的图片**，脚本会自动认出来：

    music/01-全世界的灵魂之诗.mp3
    music/01-全世界的灵魂之诗.jpg     <- 封面，扩展名随意（见 IMAGE_EXT）

认不出封面时清单里写 `cover: null`，播放器退回牌背的面具那张图。
（内置封面可以从 mp3 里抽出来，用 tools/extract_album_art.py。）

## 为什么不生成 manifest.json

json 要用 fetch 取，而 fetch 在 file:// 协议下会被 CORS 拦掉 ——
本地双击打开 index.html 时音乐就没了。<script src> 没有这个限制，
本地和线上行为一致。

## 标题怎么来的

文件名去掉扩展名，去掉常见的前导编号（01- / 02. / 03_ ），下划线换空格。
例：`01-夜深了.mp3` -> title 为「夜深了」。
"""

import io
import os
import re
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MUSIC_DIR = os.path.join(ROOT, "music")
OUT_FILE = os.path.join(MUSIC_DIR, "manifest.js")

AUDIO_EXT = {".mp3", ".ogg", ".oga", ".opus", ".m4a", ".aac",
             ".wav", ".flac", ".webm"}
IMAGE_EXT = {".webp", ".jpg", ".jpeg", ".png", ".avif", ".gif"}
# 同一首歌有多张封面图时按这个顺序取第一张 —— webp 体积最小，优先
IMAGE_PREF = [".webp", ".avif", ".jpg", ".jpeg", ".png", ".gif"]

# 这些字符会把 CSS 的 url("...") 拆坏，遇到就报警告。
# 注意：单引号**不**在其中 —— 播放器用的是 url("...")（双引号），
# 撇号（When The Moon's Reaching Out Stars 这种歌名里就有）是安全的。
BAD_CHARS = set('"()\\\n\r')

# 前导编号：01- / 02. / 03_ / 04 空格 —— 曲目名里通常不需要它
LEADING_NUM = re.compile(r"^\d{1,3}\s*[-_.、\s]+\s*")


def natural_key(name):
    """让 2 排在 10 前面，而不是按字典序排到后面。"""
    return [int(p) if p.isdigit() else p.lower()
            for p in re.split(r"(\d+)", name)]


def title_of(filename):
    stem = os.path.splitext(filename)[0]
    stem = LEADING_NUM.sub("", stem)
    stem = stem.replace("_", " ").strip()
    return stem or os.path.splitext(filename)[0]


def find_cover(stem, listing):
    """找同名的封面图。listing 是 music/ 里的文件名集合（小写比较）。"""
    for ext in IMAGE_PREF:
        cand = stem + ext
        for name in listing:
            if name.lower() == cand.lower():
                return name
    return None


def has_embedded_art(path):
    """粗略判断 mp3 里有没有内嵌专辑封面。
    只用来打印提示，不做精确解析 —— 真正的抽取在 tools/extract_album_art.py。"""
    try:
        with io.open(path, "rb") as f:
            head = f.read(10)
            if len(head) < 10 or head[:3] != b"ID3":
                return False
            size = ((head[6] & 0x7F) << 21) | ((head[7] & 0x7F) << 14) | \
                   ((head[8] & 0x7F) << 7) | (head[9] & 0x7F)
            return b"APIC" in f.read(size)
    except Exception:
        return False


def main():
    if not os.path.isdir(MUSIC_DIR):
        os.makedirs(MUSIC_DIR)

    listing = os.listdir(MUSIC_DIR)
    audio, covers = [], {}
    for name in listing:
        full = os.path.join(MUSIC_DIR, name)
        if not os.path.isfile(full):
            continue
        ext = os.path.splitext(name)[1].lower()
        if ext in AUDIO_EXT:
            audio.append(name)
            c = find_cover(os.path.splitext(name)[0], listing)
            if c:
                covers[name] = c

    audio.sort(key=natural_key)

    lines = [
        "// 曲目清单 —— 由 tools/gen_music_manifest.py 扫描 music/ 目录生成，请勿手改。",
        "//",
        "// 加歌：把音频丢进 music/，再跑一次这个脚本。",
        "// 配封面：在 music/ 里放一张同名的图片，例如",
        "//         01-夜色低语.mp3  +  01-夜色低语.jpg",
        "//         cover 为 null 时，播放器退回牌背的面具那张图。",
        "//",
        "// 这里用 .js 而不是 .json：json 要靠 fetch 取，而 fetch 在 file:// 下会被",
        "// CORS 拦掉 —— 本地双击打开 index.html 时音乐就消失了。<script src> 没这个问题。",
        "window.YYS_TRACKS = [",
    ]

    for name in audio:
        title = title_of(name)
        cover = covers.get(name)
        safe_file = name.replace("\\", "\\\\").replace('"', '\\"')
        safe_title = title.replace("\\", "\\\\").replace('"', '\\"')
        if cover:
            safe_cover = cover.replace("\\", "\\\\").replace('"', '\\"')
            cover_js = '"./music/%s"' % safe_cover
        else:
            cover_js = "null"
        lines.append('  { file: "%s", title: "%s", cover: %s },'
                     % (safe_file, safe_title, cover_js))

    lines.append("];")
    lines.append("")

    io.open(OUT_FILE, "w", encoding="utf-8", newline="\n").write("\n".join(lines))

    print("扫描目录 : %s" % MUSIC_DIR)
    print("写入清单 : %s" % OUT_FILE)
    print("曲目数量 : %d" % len(audio))
    for i, name in enumerate(audio):
        size = os.path.getsize(os.path.join(MUSIC_DIR, name))
        has = "封面 ✓" if name in covers else "封面 ——（播放器退回面具）"
        print("  %2d. %-32s %s  %6.2f MB"
              % (i + 1, title_of(name), has, size / 1048576.0))

    # 有内嵌封面但还没抽出来的，提示一句
    pending = []
    for name in audio:
        if name in covers:
            continue
        if has_embedded_art(os.path.join(MUSIC_DIR, name)):
            pending.append(name)
    if pending:
        print()
        print("提示：下面 %d 首的 mp3 里自带封面，但还没抽出来 ——" % len(pending))
        for n in pending:
            print("        %s" % n)
        print("      跑一下：python tools/extract_album_art.py")

    # 文件名里会破坏 CSS url() 的字符
    bad = [c for c in covers.values() if BAD_CHARS & set(c)]
    if bad:
        print()
        print("!! 这些封面文件名里有引号或括号，会拆坏 CSS 的 url()，请改名：")
        for b in bad:
            print("        %s" % b)

    total = sum(os.path.getsize(os.path.join(MUSIC_DIR, n)) for n in audio)
    covered = len(covers)
    if audio:
        print()
        print("封面覆盖   : %d / %d 首" % (covered, len(audio)))
        print("音频总体积 : %.2f MB" % (total / 1048576.0))
        csize = sum(os.path.getsize(os.path.join(MUSIC_DIR, c)) for c in covers.values())
        if csize:
            print("封面总体积 : %.2f MB" % (csize / 1048576.0))
        print("提醒：音频和封面都是「按需加载」—— 不点播放就不会下载，首屏体积不受影响。")


if __name__ == "__main__":
    main()
