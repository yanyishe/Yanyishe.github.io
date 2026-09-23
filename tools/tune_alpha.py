# -*- coding: utf-8 -*-
"""拉开远近景的"实 / 虚"对比，强化纵深。

近景牌 +0.13、远景牌 +0.05：尺寸差（1.0 vs 0.6）之外再叠一层透明度差，
两者合起来才读得出"前后距离"，而单纯缩小只会显得小、不会显得远。
"""
import io
import re

P = 'E:/mygit/Yanyishe.github.io/index.html'
s = io.open(P, encoding='utf-8').read()

ROW = re.compile(r'(body\.layout-(?:top|scrolled)\s+\.tw-\d+\s*\{)([^}]*)(\})')
K = re.compile(r'--k:\s*([\d.]+)')
OP = re.compile(r'opacity:\s*([\d.]+)')


def bump(m):
    body = m.group(2)
    gk, gop = K.search(body), OP.search(body)
    if not (gk and gop):
        return m.group(0)
    delta = 0.13 if abs(float(gk.group(1))) < 0.01 else 0.05
    val = min(0.95, float(gop.group(1)) + delta)
    return m.group(1) + body[:gop.start(1)] + ('%.2f' % val) + body[gop.end(1):] + m.group(3)


s2, n = ROW.subn(bump, s)
assert n == 44, '预期改 44 条布局规则，实际 %d' % n

s2 = s2.replace('.tarot-wrap[data-layer="back"]  { opacity: 0.30;',
                '.tarot-wrap[data-layer="back"]  { opacity: 0.35;')
s2 = s2.replace('.tarot-wrap[data-layer="mid"]   { opacity: 0.55;',
                '.tarot-wrap[data-layer="mid"]   { opacity: 0.66;')
s2 = s2.replace('.tarot-wrap[data-layer="front"] { opacity: 0.55;',
                '.tarot-wrap[data-layer="front"] { opacity: 0.68;')

io.open(P, 'w', encoding='utf-8').write(s2)

near = [float(x) for x in re.findall(r'--k: 0; opacity: ([\d.]+)', s2)]
far = [float(x) for x in re.findall(r'--k: 1\.12; opacity: ([\d.]+)', s2)]
print('近景 %d 张 opacity %.2f~%.2f' % (len(near), min(near), max(near)))
print('远景 %d 张 opacity %.2f~%.2f' % (len(far), min(far), max(far)))
