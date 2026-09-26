# -*- coding: utf-8 -*-
"""从牌背原图里裁出面具，生成站点 favicon。

用法（在项目根目录）：
    python tools/make_favicon.py

为什么需要这个脚本：
    favicon 必须是**一个真实存在的图片文件** —— 浏览器要拿它的 URL。
    播放器封面可以靠 CSS 的 background-position 从牌背上裁出来，favicon 不行，
    所以只能把裁好的结果固化下来。

构图上的两个约束（都是实测出来的）：
  1. 面具要尽量占满画布。16px 是标签页的实际显示尺寸，留白多了就只剩一团。
  2. **白色那半边必须有个边界**。面具是左白右黑，纯裁切的话白半边在浅色标签栏上
     直接糊进背景 —— 所以最终版给它加了一圈暖金描边，白半边黑半边都和它对得上。
"""

import os
import sys

from PIL import Image, ImageDraw, ImageFont

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "images", "tarot-back.webp")
OUT_ICON = os.path.join(ROOT, "images", "favicon.png")
OUT_APPLE = os.path.join(ROOT, "images", "favicon-180.png")
OUT_SHEET = os.path.join(ROOT, "preview", "favicon-check.png")

# 牌背是 320×451。面具（日月双面那个）正好落在牌面正中，直径约占牌宽的 69%。
# 这两个数是量出来的；换了素材得重新量。
CENTER = (162, 227)
MASK_D = 220

ICON_SIZE = 64          # 标签页够用（显示 16/32，高 DPI 屏也覆盖得到）
APPLE_SIZE = 180        # iOS 加到主屏用

# 最终采用的构图：紧裁 + 暖金描边
CHOSEN_PAD = 1.00
RING = (201, 162, 74)   # #c9a24a，和播放器主按钮、站内金色强调同一个色
RING_W = 0.09           # 描边宽度占画布的比例


def rounded_alpha(size, radius_ratio):
    """圆角矩形的 alpha 通道。4 倍超采样再缩，免得圆角一圈锯齿。"""
    ss = 4
    big = Image.new("L", (size * ss, size * ss), 0)
    ImageDraw.Draw(big).rounded_rectangle(
        [0, 0, size * ss - 1, size * ss - 1],
        radius=int(size * ss * radius_ratio), fill=255)
    return big.resize((size, size), Image.LANCZOS)


def circle_alpha(size):
    ss = 4
    big = Image.new("L", (size * ss, size * ss), 0)
    ImageDraw.Draw(big).ellipse([0, 0, size * ss - 1, size * ss - 1], fill=255)
    return big.resize((size, size), Image.LANCZOS)


def crop_mask(im, pad):
    """按面具的实测中心与直径裁一个正方形，pad 控制留白。"""
    side = int(round(MASK_D * pad))
    cx, cy = CENTER
    left = max(0, min(int(round(cx - side / 2)), im.width - side))
    top = max(0, min(int(round(cy - side / 2)), im.height - side))
    return im.crop((left, top, left + side, top + side))


# ---- 三种构图，用来横向对比 ----
def v_plain(src, size):
    return crop_mask(src, 1.06).resize((size, size), Image.LANCZOS).convert("RGBA")


def v_tight(src, size):
    return crop_mask(src, 1.00).resize((size, size), Image.LANCZOS).convert("RGBA")


def v_ring(src, size, ring=RING, w=RING_W, pad=CHOSEN_PAD):
    inner = max(1, int(round(size * (1 - 2 * w))))
    art = crop_mask(src, pad).resize((inner, inner), Image.LANCZOS).convert("RGBA")
    canvas = Image.new("RGBA", (size, size), ring + (255,))
    canvas.paste(art, ((size - inner) // 2, (size - inner) // 2), art)
    canvas.putalpha(rounded_alpha(size, 0.22))
    return canvas


def v_disc(src, size, bg):
    inner = max(1, int(round(size * 0.84)))
    art = crop_mask(src, 0.98).resize((inner, inner), Image.LANCZOS).convert("RGBA")
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    base = Image.new("RGBA", (size, size), bg + (255,))
    canvas.paste(base, (0, 0), rounded_alpha(size, 0.22))
    canvas.paste(art, ((size - inner) // 2, (size - inner) // 2), circle_alpha(inner))
    return canvas


VARIANTS = [
    ("A 原始裁切 1.06", lambda s, n: v_plain(s, n)),
    ("B 紧裁 1.00", lambda s, n: v_tight(s, n)),
    ("C 紧裁 + 金环 ← 采用", lambda s, n: v_ring(s, n)),
    ("D 金底 + 圆章", lambda s, n: v_disc(s, n, RING)),
    ("E 藏青底 + 圆章", lambda s, n: v_disc(s, n, (28, 28, 51))),
]


def save_icon(src, path, size, colors):
    """缩到目标尺寸再存。用调色板量化 —— favicon 是几十像素的东西，
    真彩 PNG 省下的那点色深在眼睛上换不回体积。"""
    out = v_ring(src, size).convert("RGB")
    out.quantize(colors=colors, method=Image.MEDIANCUT,
                 dither=Image.FLOYDSTEINBERG).save(path, format="PNG", optimize=True)
    return os.path.getsize(path)


def load_font(size):
    """对照表要写中文标签，而 PIL 自带的位图字体没有汉字 —— 不换字体的话
    标签会全渲染成方框，图表反而看不懂。"""
    for p in (r"C:\Windows\Fonts\msyh.ttc",
              r"C:\Windows\Fonts\simhei.ttf",
              "/System/Library/Fonts/PingFang.ttc",
              "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"):
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                pass
    return ImageFont.load_default()


def sheet(src, path, sizes=(16, 24, 32, 48, 64)):
    """把几个候选摆成一张对照表：白底一行、深底一行。
    16px 的图标在整页截图里根本看不见，必须这样并排放大才判断得了。"""
    font = load_font(14)

    cell, label_w = 78, 210
    w = label_w + cell * len(sizes) + 20
    h = 40 + (cell * 2 + 16) * len(VARIANTS)
    canvas = Image.new("RGB", (w, h), (245, 242, 236))
    d = ImageDraw.Draw(canvas)

    d.text((label_w, 14), "  ".join("%dpx" % s for s in sizes) +
           "                   白底 / 深底（模拟标签栏）", fill=(70, 58, 34), font=font)

    y = 40
    for label, fn in VARIANTS:
        for row, bg in enumerate([(255, 255, 255), (26, 26, 46)]):
            strip = Image.new("RGB", (cell * len(sizes), cell), bg)
            for i, s in enumerate(sizes):
                t = fn(src, s)
                strip.paste(t, (i * cell + (cell - s) // 2, (cell - s) // 2), t)
            canvas.paste(strip, (label_w, y + row * cell))
        d.text((14, y + cell - 18), label, fill=(60, 50, 30), font=font)
        y += cell * 2 + 16

    os.makedirs(os.path.dirname(path), exist_ok=True)
    canvas.save(path, format="PNG", optimize=True)
    return path


def main():
    if not os.path.exists(SRC):
        raise SystemExit("找不到素材：%s" % SRC)

    src = Image.open(SRC).convert("RGB")
    print("素材      : %s  %dx%d" % (os.path.relpath(SRC, ROOT), src.width, src.height))
    print("牌面边长  : %d  (面具实测直径 %d @ 中心 %s)" % (MASK_D, MASK_D, CENTER))
    print("采用构图  : 紧裁 %.2f + 暖金 #%02x%02x%02x 描边 %.0f%%"
          % (CHOSEN_PAD, RING[0], RING[1], RING[2], RING_W * 100))
    print()

    s1 = save_icon(src, OUT_ICON, ICON_SIZE, 128)
    print("写入      : %s  %dx%d  %.1f KB"
          % (os.path.relpath(OUT_ICON, ROOT), ICON_SIZE, ICON_SIZE, s1 / 1024))

    s2 = save_icon(src, OUT_APPLE, APPLE_SIZE, 256)
    print("写入      : %s  %dx%d  %.1f KB"
          % (os.path.relpath(OUT_APPLE, ROOT), APPLE_SIZE, APPLE_SIZE, s2 / 1024))

    print("对照表    : %s" % os.path.relpath(sheet(src, OUT_SHEET), ROOT))
    print()
    print("合计新增  : %.1f KB" % ((s1 + s2) / 1024))
    print("提醒：换素材（images/tarot-back.webp）后要重跑本脚本，并核对对照表 ——")
    print("      重点看 16px 那一列在白底上还认不认得出面具。")


if __name__ == "__main__":
    main()
