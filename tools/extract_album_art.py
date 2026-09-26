# -*- coding: utf-8 -*-
"""把 mp3 里内嵌的专辑封面抽出来，存成 music/<同名>.webp。

用法（在项目根目录）：
    python tools/extract_album_art.py            # 抽所有还没封面的
    python tools/extract_album_art.py --force    # 连已有封面的也重抽

抽出来之后，它就是一 normal 的封面文件了 —— gen_music_manifest.py 按
「music/ 里同名图片」的规则自动认出来，不需要额外配置。

两个刻意的取舍：
  · **默认不覆盖**已有的同名封面。你自己配的图不会被 mp3 里的顶掉，
    即使那张图不是 .webp（会按其他扩展名识别为已有封面而跳过）。
  · 抽出来的图会**缩到 512px 并存成 WebP**。原始内嵌图常常是 1000px+jpeg，
    作为 104px 的缩略图用太浪费 —— 实测两张能省下约 300KB 的首屏流量。

需要 Pillow。装不上就看 README 里那段「pip 装不上包」的绕行方案。
"""

import io
import os
import re
import struct
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MUSIC_DIR = os.path.join(ROOT, "music")

MAX_EDGE = 512          # 存盘后的最长边 —— 播放器封面显示尺寸是 104px，留足余量
WEBP_QUALITY = 82
IMAGE_EXT = {".webp", ".jpg", ".jpeg", ".png", ".avif", ".gif"}

PIC_TYPES = {
    0x00: "其他", 0x01: "32x32 图标", 0x02: "其他图标", 0x03: "封面(正面)",
    0x04: "封面(背面)", 0x05: "折页", 0x06: "媒体", 0x07: "独唱艺术家",
    0x08: "表演者", 0x09: "指挥", 0x0A: "乐队", 0x0B: "作曲", 0x0C: "作词",
    0x0D: "唱片公司", 0x0E: "混音", 0x0F: "制作人", 0x10: "版权",
    0x12: "插图", 0x13: "乐队标志", 0x14: "出版者标志",
}


def syncsafe(b):
    return (b[0] << 21) | (b[1] << 14) | (b[2] << 7) | b[3]


def read_apic(path):
    """返回 [(图片类型, mime, 原始字节)]，按「正面封面优先、其次尺寸大的」排好。"""
    out = []
    with io.open(path, "rb") as f:
        head = f.read(10)
        if len(head) < 10 or head[:3] != b"ID3":
            return out
        major = head[3]
        flags = head[5]
        size = syncsafe(head[6:10])
        body = f.read(size)
        if flags & 0x40:                       # 跳过扩展头
            ext = syncsafe(body[:4])
            body = body[4 + ext:]

        pos = 0
        while pos + 10 <= len(body):
            fid = body[pos:pos + 4]
            if not fid.strip(b"\x00"):
                break
            if major == 2:
                fsize = (body[pos + 3] << 16) | (body[pos + 4] << 8) | body[pos + 5]
                hlen = 6
            else:
                fsize = (syncsafe(body[pos + 4:pos + 8]) if major == 4
                         else struct.unpack(">I", body[pos + 4:pos + 8])[0])
                hlen = 10
            if fid == b"APIC":
                d = body[pos + hlen:pos + hlen + fsize]
                if d:
                    enc = d[0]                 # 0=ISO-8859-1 1=UTF-16 2=UTF-16BE 3=UTF-8
                    rest = d[1:]
                    if major == 2:
                        mime = "image/" + rest[:3].decode("latin-1", "replace").lower()
                        rest = rest[3:]
                    else:
                        z = rest.find(b"\x00")
                        mime = rest[:z].decode("latin-1", "replace") if z >= 0 else ""
                        rest = rest[z + 1:]
                    ptype = rest[0] if rest else 0xFF
                    rest = rest[1:]
                    # 图片类型后面还有一段「描述」，同样以 0 结尾 ——
                    # 漏掉它就会把描述文字当成图片数据的开头，Pillow 认不出来。
                    # UTF-16 的结束符是两个字节。
                    z = rest.find(b"\x00\x00" if enc in (1, 2) else b"\x00")
                    if z >= 0:
                        rest = rest[z + (2 if enc in (1, 2) else 1):]
                    out.append((ptype, mime, rest))
            pos += hlen + fsize

    # 正面封面(3) 排最前，其余按体积从大到小
    out.sort(key=lambda x: (0 if x[0] == 0x03 else 1, -len(x[2])))
    return out


def pick_best(pics):
    """挑一张：优先「封面(正面)」，否则选体积最大的那张（大的一般是真正的封面，
    小的是 32x32 图标之类的垃圾帧）。"""
    for t, m, data in pics:
        if t == 0x03:
            return t, m, data
    return max(pics, key=lambda x: len(x[2]))


def existing_cover(stem, listing):
    for name in listing:
        if (os.path.splitext(name)[0].lower() == stem.lower()
                and os.path.splitext(name)[1].lower() in IMAGE_EXT):
            return name
    return None


def main():
    try:
        from PIL import Image
    except ImportError:
        sys.exit("需要 Pillow。装不上时见 README 里「pip 装不上包」那段绕行方案。")

    force = "--force" in sys.argv
    if not os.path.isdir(MUSIC_DIR):
        sys.exit("找不到目录：%s" % MUSIC_DIR)

    listing = os.listdir(MUSIC_DIR)
    mp3s = sorted(n for n in listing
                  if os.path.isfile(os.path.join(MUSIC_DIR, n))
                  and n.lower().endswith(".mp3"))

    print("扫描 %d 个 mp3   (最长边缩到 %dpx，存 WebP q%d)\n"
          % (len(mp3s), MAX_EDGE, WEBP_QUALITY))

    done = skipped = empty = 0
    for name in mp3s:
        stem = os.path.splitext(name)[0]
        side = existing_cover(stem, listing)
        if side and not force:
            print("  %-46s 跳过（已有封面 %s）" % (name[:46], side))
            skipped += 1
            continue

        try:
            pics = read_apic(os.path.join(MUSIC_DIR, name))
        except Exception as e:
            print("  %-46s 解析失败: %s" % (name[:46], e))
            continue
        if not pics:
            print("  %-46s 没有内嵌封面" % name[:46])
            empty += 1
            continue

        ptype, mime, raw = pick_best(pics)
        before = len(raw)
        try:
            im = Image.open(io.BytesIO(raw))
            im.load()
            w, h = im.size
            if max(w, h) > MAX_EDGE:
                sc = MAX_EDGE / float(max(w, h))
                im = im.resize((max(1, int(round(w * sc))), max(1, int(round(h * sc)))),
                               Image.LANCZOS)
            if im.mode not in ("RGB", "RGBA"):
                im = im.convert("RGB")
            out = os.path.join(MUSIC_DIR, stem + ".webp")
            im.save(out, format="WEBP", quality=WEBP_QUALITY, method=6)
        except Exception as e:
            print("  %-46s 解不出图（%s）：%s" % (name[:46], mime, e))
            continue

        after = os.path.getsize(out)
        print("  %-46s ✓ %-10s %dx%d  %dKB -> %dKB"
              % (name[:46], PIC_TYPES.get(ptype, "0x%02x" % ptype),
                 im.size[0], im.size[1], before // 1024, after // 1024))
        done += 1

    print()
    print("抽出 %d 首  跳过 %d 首  无封面 %d 首" % (done, skipped, empty))
    if done:
        print()
        print("下一步：跑一次 python tools/gen_music_manifest.py，清单里就有 cover 字段了。")


if __name__ == "__main__":
    main()
