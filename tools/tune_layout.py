# -*- coding: utf-8 -*-
"""按几何断言的结论收紧参数（在 relayout.py 之后运行）。

断言发现两个肉眼看不出的问题：
  ① 近景列最大缩放 1.02 > --k 的让位量 1.0，两列在 0~3.5px 上贴死；
  ② 宽屏下纵向上限 0.088×层高 偏大，最后一张牌溢出牌层底部（101%）。
"""
import io
import re

PATH = 'E:/mygit/Yanyishe.github.io/index.html'
src = io.open(PATH, encoding='utf-8').read()
n0 = len(src)

# ---------- ① 纵向上限 0.088 -> 0.084（留出底部余量） ----------
a = 'calc(var(--layer-h) * 0.088)'
assert a in src
src = src.replace(a, 'calc(var(--layer-h) * 0.084)')

# ---------- ② 远景列让位量 1 -> 1.12（大于近景最大缩放 1.02，留 10% 净间隙） ----------
src = src.replace('.tarot-wrap[data-layer="back"]  { opacity: 0.30; --s: 0.60; --k: 1; }',
                  '.tarot-wrap[data-layer="back"]  { opacity: 0.30; --s: 0.60; --k: 1.12; }')
src = src.replace('--k: 1; opacity:', '--k: 1.12; opacity:')

# ---------- ③ 槽位网格 16%~93% -> 16%~90%（节距 7.7% -> 7.4%） ----------
OLD_TOP = [16.0, 23.7, 31.4, 39.1, 46.8, 54.5, 62.2, 69.9, 77.6, 85.3, 93.0]
OLD_SCR = [12.0, 19.7, 27.4, 35.1, 42.8, 50.5, 58.2, 65.9, 73.6, 81.3, 89.0]
NEW_TOP = [round(16.0 + k * 7.4, 1) for k in range(11)]
NEW_SCR = [round(v - 4.0, 1) for v in NEW_TOP]

remap = {}
for o, n in zip(OLD_TOP, NEW_TOP):
    remap[o] = n
for o, n in zip(OLD_SCR, NEW_SCR):
    remap[o] = n


def fix_t(m):
    t = float(m.group(1))
    return '--t: %4.1f%%' % remap.get(t, t)


start = src.index('/* ========== 布局 1（滚动前）')
end = src.index('/* ========== 内容区 ========== */')
block = src[start:end]
new_block = re.sub(r'--t:\s*([\d.]+)%', fix_t, block)
src = src[:start] + new_block + src[end:]

# ---------- ④ 远景列的显示门槛 1200 -> 1320（低于此宽度两列会贴到屏幕边） ----------
src = src.replace('/* 视口收窄到两侧放不下两列时，收起内列小牌，只保留外列 */\n@media (max-width: 1200px) {',
                  '/* 视口收窄到两侧塞不下「近景列 + 间隔 + 远景列」时，收起远景列。\n'
                  '   1320px 是算出来的临界点：再窄远景列就会贴到屏幕边缘。 */\n@media (max-width: 1320px) {')

# 注释同步
src = src.replace('节距 7.7%', '节距 7.4%')
src = src.replace('相距 2 个节距(2×7.7%)', '相距 2 个节距(2×7.4%)')

io.open(PATH, 'w', encoding='utf-8').write(src)
print('参数收紧完成 %d -> %d' % (n0, len(src)))
print('新槽位 top :', NEW_TOP)
print('新槽位 scr :', NEW_SCR)
