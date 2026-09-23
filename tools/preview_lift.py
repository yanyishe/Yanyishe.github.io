# -*- coding: utf-8 -*-
"""
生成两张变体，用于「同一张牌翻开前后」的同框对比：
  _lift_off.html  不翻开（tw-4 保持面具牌背）
  _lift_on.html   翻开 tw-4（露出大阿尔卡那正面）

两个变体都在同一个窗口尺寸下截图，再按同一个坐标框裁剪、并排拼成一张，
于是"上浮 / 放大 / 换金边"三件事可以直接量出来。

无头环境限制的绕法同 preview_flip.py：关过渡（不推进 transition）、
改同步解码（async 偶发来不及）。
"""
import io
import os

from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, 'index.html')

STYLE = ('<style>.tarot-card { transition: none !important; }</style>')
CLICK = r"""
<script>
setTimeout(function () {
  ['tw-4', 'tw-5'].forEach(function (cls) {
    var el = document.querySelector('.tarot-wrap.' + cls);
    if (el) el.dispatchEvent(new MouseEvent('click', { bubbles: true }));
  });
}, 700);
</script>
"""

src = io.open(SRC, encoding='utf-8').read().replace('decoding="async"', 'decoding="sync"')

for name, probe in (('_lift_off.html', ''), ('_lift_on.html', CLICK)):
    html = src.replace('</head>', STYLE + '</head>').replace('</body>', probe + '</body>')
    io.open(os.path.join(ROOT, name), 'w', encoding='utf-8').write(html)
    print('variant -> ' + name)

# 裁剪框（CSS 像素）：把 tw-4 翻开前后的最高点和最低点都框进来
BOX = (86, 398, 252, 646)
SCALE = 2


def stitch(off_png, on_png, out_png):
    x0, y0, x1, y1 = [v * SCALE for v in BOX]
    a = Image.open(off_png).crop((x0, y0, x1, y1))
    b = Image.open(on_png).crop((x0, y0, x1, y1))

    pad, top = 14, 40
    W = a.width + b.width + pad * 3
    H = a.height + top + pad
    out = Image.new('RGB', (W, H), (24, 22, 32))
    out.paste(a, (pad, top))
    out.paste(b, (pad * 2 + a.width, top))
    d = ImageDraw.Draw(out)
    d.text((pad, 14), 'BEFORE  tw-4  (not flipped)', fill=(190, 205, 225))
    d.text((pad * 2 + a.width, 14), 'AFTER  tw-4  (flipped)', fill=(255, 214, 130))
    out.save(out_png)
    print('stitched -> %s  (%dx%d)' % (out_png, out.width, out.height))


if __name__ == '__main__':
    import sys
    if len(sys.argv) == 4:
        stitch(sys.argv[1], sys.argv[2], sys.argv[3])
