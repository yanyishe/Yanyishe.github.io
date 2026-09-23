# -*- coding: utf-8 -*-
"""几何断言：证明任意两张牌都不重叠，且牌层铺满整页。

复刻 index.html 里 :root 与 .tarot-wrap 的 calc 公式，把每张牌的矩形算出来，
两两求交。比肉眼看图可靠 —— 而且换视口比例后能立刻发现退化。
"""
import io
import re
import itertools

PATH = 'E:/mygit/Yanyishe.github.io/index.html'
src = io.open(PATH, encoding='utf-8').read()

# ---------- 解析：:root 的 --base 公式 ----------
root = re.search(r':root\s*\{(.*?)\}', src, re.S).group(1)
assert '--layer-h' in root, ':root 里没有 --layer-h，说明改回写死高度了'

# ---------- 解析：每张牌的层级 ----------
layer = {}
for m in re.finditer(r'class="tarot-wrap (tw-\d+)"[^>]*?data-layer="(\w+)"', src):
    layer[m.group(1)] = m.group(2)


def parse(state):
    out = {}
    for m in re.finditer(r'body\.layout-' + state + r'\s+\.(tw-\d+)\s*\{([^}]*)\}', src):
        name, body = m.group(1), m.group(2)
        if name not in layer:
            continue
        g = lambda k: re.search(r'--' + k + r':\s*(-?[\d.]+)', body)
        t, s, k = g('t'), g('s'), g('k')
        op = re.search(r'opacity:\s*([\d.]+)', body)
        out[name] = dict(
            t=float(t.group(1)) if t else None,
            s=float(s.group(1)) if s else 1.0,
            k=float(k.group(1)) if k else 0.0,
            op=float(op.group(1)) if op else None,
            side='r' if '--r:' in body else 'l',
            layer=layer[name])
    return out


def geom(VW, LAYER_H, name, c, flip=False):
    """复刻 CSS：--edge / --base / --w / --lx|--rx / --t

    flip=True 时按"翻开"的终点态算：牌会朝观察者推进，透视把它换算成放大，
    并上浮若干 px。数值必须和 index.html 里 .tarot-wrap.flipped .tarot-card
    的 translate3d 与 .tarot-wrap 的 perspective 保持一致。
    """
    PERSPECTIVE = 1000.0     # .tarot-wrap { perspective }
    LIFT_Z = 40.0            # translate3d 的 z
    LIFT_Y = 22.0            # translate3d 的 y
    edge = max(0.0, VW / 2 - 460)
    base = min(max(72.0, min((VW / 2 - 460) * 0.48, 190.0)), LAYER_H * 0.084)
    w = base * c['s']
    h = w * 1.5
    if flip:
        k = PERSPECTIVE / (PERSPECTIVE - LIFT_Z)      # 透视放大倍数
        w, h = w * k, h * k
    off = max(0.0, edge - w - base * 0.15 - base * c['k'])
    x = off if c['side'] == 'l' else VW - off - w
    y = c['t'] / 100.0 * LAYER_H - (LIFT_Y if flip else 0.0)
    return x, y, w, h


def overlap(a, b):
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    ox = min(ax + aw, bx + bw) - max(ax, bx)
    oy = min(ay + ah, by + bh) - max(ay, by)
    return (ox, oy) if ox > 0 and oy > 0 else None


# 参考系：1440 视口宽、页面总高 1883（由 758 视口实测得出）
CASES = [
    ('1440x900 常见桌面', 1410, 1883),
    ('1280x800', 1250, 1896),
    ('1920x1080', 1880, 2002),
    ('2560x1440', 2510, 2139),
    ('1680x1050', 1650, 1988),
]

print('=' * 78)
print('横向布局（1440 参考）')
edge = 1410 / 2 - 460
base = min(max(72.0, min((1410 / 2 - 460) * 0.48, 190.0)), 1883 * 0.084)
near_w, far_w = base * 1.0, base * 0.6
near_l = edge - near_w - base * 0.15
far_l = edge - far_w - base * 0.15 - base * 1.25
print('  两侧可用 %.0fpx   牌基准 %.1fpx   近景列宽 %.1f   远景列宽 %.1f'
      % (edge, base, near_w, far_w))
print('  近景列 x = [%.1f, %.1f]   远景列 x = [%.1f, %.1f]   净间隙 %.1fpx  %s'
      % (near_l, near_l + near_w, far_l, far_l + far_w, near_l - (far_l + far_w),
         '不重叠 OK' if near_l >= far_l + far_w else '有重叠 X'))

print()
print('=' * 78)
worst = None
for label, VW, LH in CASES:
    for state in ('top', 'scrolled'):
        cards = parse(state)
        rects = []
        for name, c in sorted(cards.items(), key=lambda kv: int(kv[0][3:])):
            if c['t'] is None:
                continue
            rects.append((name, geom(VW, LH, name, c)))
        bad = []
        for (n1, r1), (n2, r2) in itertools.combinations(rects, 2):
            ov = overlap(r1, r2)
            if ov:
                bad.append((n1, n2, ov))
        # 最小区分度：同侧、相邻 y 之间的净空隙
        gaps = []
        for side in ('l', 'r'):
            col = sorted([r for n, r in rects if r[0] < VW / 2] if side == 'l'
                         else [r for n, r in rects if r[0] >= VW / 2], key=lambda r: r[1])
            for a, b in zip(col, col[1:]):
                if a[0] < b[0] + b[2] and b[0] < a[0] + a[2]:     # 同列
                    gaps.append(b[1] - (a[1] + a[3]))
        # 覆盖：最上/最下的牌是否落在牌层内
        top = min(r[1] for n, r in rects)
        bot = max(r[1] + r[3] for n, r in rects)
        cover = (top, bot, LH)
        status = '重叠 %d 对' % len(bad) if bad else '无重叠'
        print('%-16s %-9s 牌数%3d   %s   纵向 %d~%d / 层高 %d  %.0f%%'
              % (label, state, len(rects), status, top, bot, LH, bot / LH * 100))
        if bad:
            worst = bad[:5]
        if state == 'top' and gaps:
            print('%-16s   └ 同列最小净间隙 %.1fpx' % ('', min(gaps)))

if worst:
    print()
    print('重叠明细：')
    for n1, n2, ov in worst:
        print('  %s × %s  ->  x %.1fpx / y %.1fpx' % (n1, n2, ov[0], ov[1]))
else:
    print()
    print('结论：所有视口、两种布局下，22 张牌（未翻开态）两两无重叠。')

# ---------------------------------------------------------------------------
# 最坏情况：全部翻开。牌会放大并上浮，这是唯一可能重新压到邻牌的态。
# 注意：这里按"未旋转的矩形"算，是保守近似；倾角带来的外接框扩展
# 由浏览器实测脚本 tools/probe_flip_overlap.py 兜底。
# ---------------------------------------------------------------------------
print()
print('=' * 78)
print('最坏情况：22 张全部翻开（含透视放大 + 上浮）')
for label, VW, LH in CASES:
    for state in ('top', 'scrolled'):
        cards = parse(state)
        rects = []
        for name, c in sorted(cards.items(), key=lambda kv: int(kv[0][3:])):
            if c['t'] is None:
                continue
            rects.append((name, geom(VW, LH, name, c, flip=True)))
        bad = []
        for (n1, r1), (n2, r2) in itertools.combinations(rects, 2):
            ov = overlap(r1, r2)
            if ov:
                bad.append((n1, n2, ov))
        # 翻开后是否侵入内容卡（内容卡恒 920 居中）
        cl = VW / 2 - 460
        intrude = [(n, r) for n, r in rects
                   if r[0] < cl < r[0] + r[2] and r[1] < LH]
        gap = min((cl - (r[0] + r[2]) for n, r in rects
                   if r[0] + r[2] <= cl and r[0] + r[2] > cl - 200), default=999)
        print('%-16s %-9s 重叠 %d 对   离内容卡最近净空 %.1fpx   %s'
              % (label, state, len(bad), gap,
                 '侵入内容卡 %d 张 X' % len(intrude) if intrude else '未侵入 OK'))
