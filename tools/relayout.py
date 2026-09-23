# -*- coding: utf-8 -*-
"""重排背景塔罗牌：两列完全错开 + 明确纵深分层 + 牌层铺满整页。

核心思路：
  · 横向 —— 近景列贴内容卡，远景列再向外让开「整整一个牌宽」(k=1)，
    两列 x 区间不相交，所以永远不会横向压在一起。
  · 纵向 —— 同一列内相邻两张相距 2 个槽位，节距 7.7%，牌高远小于 2×节距。
  · 尺寸 —— 牌宽同时受横向空间和纵向槽位约束，取较小值。这样任何视口比例
    下"牌高 < 2×节距"都成立，不会退化回堆叠。
  · 纵深 —— 近景大而实（s≈1.0 / opacity≈0.5），远景小而淡（s≈0.6 / 0.25），
    并且远景不投阴影（22 个阴影叠在一起是"糊"的主要来源）。
"""
import re
import io

PATH = 'E:/mygit/Yanyishe.github.io/index.html'
src = io.open(PATH, encoding='utf-8').read()
orig = src

# ============================================================
# 1) :root —— 牌宽改为"横向空间"与"纵向槽位"双约束
# ============================================================
old_root = """:root {
  /* 内容卡固定 920px 居中，所以两侧可用宽度 = (100vw - 920px) / 2。
     卡牌尺寸与列位全部由它推导 —— 宽屏自动变大、窄屏自动收住，
     不会像写死 px 那样在超宽屏显得小、在 1280 屏溢出到内容卡后面。 */
  --edge: max(0px, calc(50vw - 460px));
  --base: clamp(78px, calc((50vw - 460px) * 0.5), 200px);
}"""

new_root = """:root {
  /* 内容卡固定 920px 居中，所以两侧可用宽度 = (100vw - 920px) / 2。 */
  --edge: max(0px, calc(50vw - 460px));
  /* 牌层高度由 JS 实测正文总高后写入（兜底给 200vh）。
     写死 200vh 时页面实际有 ~250vh，底部那一截根本没有牌。 */
  --layer-h: 200vh;
  /* 牌宽 = min(横向约束, 纵向约束)，两个方向都必须满足：
       横向：两侧要放得下「近景列 + 一个牌宽的间隙 + 远景列」
       纵向：11 个槽位交错排布，同列相邻两张相距 2 个节距(2×7.7%)，
             牌高(1.5×宽)必须小于它，否则又叠回去 —— 所以不能写死 px。 */
  --base: min(
    clamp(72px, calc((50vw - 460px) * 0.5), 190px),
    calc(var(--layer-h) * 0.088)
  );
}"""
assert old_root in src, '找不到 :root 块'
src = src.replace(old_root, new_root, 1)

# ============================================================
# 2) 牌层高度改用 --layer-h
# ============================================================
old_layer = """.tarot-layer {
  position: absolute;
  top: 0; left: 0;
  width: 100%;
  height: 200vh;"""
new_layer = """.tarot-layer {
  position: absolute;
  top: 0; left: 0;
  width: 100%;
  height: var(--layer-h);"""
assert old_layer in src, '找不到 .tarot-layer'
src = src.replace(old_layer, new_layer, 1)

# ============================================================
# 3) 列位公式：--k 默认 0（近景列），远景列传 1
# ============================================================
old_lx = """  /* 两种列位，都以"右边缘贴住内容卡边缘再退让 10px"为基准，
     --k 让外列再向外让开约一个牌宽（内列不设 --k，直接用基准）。
     max() 兜底：视口收窄到放不下时贴住屏幕边，而不是被推出屏幕外 */
  --lx: max(0px, calc(var(--edge) - var(--w) - 10px - var(--base) * var(--k, 0)));
  --rx: max(0px, calc(var(--edge) - var(--w) - 10px - var(--base) * var(--k, 0)));"""
new_lx = """  /* 两种列位，右边缘都锚在内容卡边缘退让 12px 处。
     --k 是"再向外让开的牌宽倍数"：近景列 0，远景列 1。
     让开整整一个牌宽，才能保证近景列最左 < 远景列最右，两列 x 区间不相交。 */
  --lx: max(0px, calc(var(--edge) - var(--w) - 12px - var(--base) * var(--k, 0)));
  --rx: max(0px, calc(var(--edge) - var(--w) - 12px - var(--base) * var(--k, 0)));"""
assert old_lx in src, '找不到列位公式'
src = src.replace(old_lx, new_lx, 1)

# 删掉旧的 --k 分组规则（新布局逐张显式给 --k）
old_k = """.tw-0,.tw-1,.tw-2,.tw-3,.tw-4,.tw-5,.tw-6,.tw-7,.tw-8,.tw-9 { --k: 0.76; }
"""
assert old_k in src, '找不到 --k 分组规则'
src = src.replace(old_k, '', 1)

# ============================================================
# 4) 远景牌去掉投影
# ============================================================
old_face = """.tarot-wrap[data-layer="back"]  { opacity: 0.32; --s: 0.60; }
.tarot-wrap[data-layer="mid"]   { opacity: 0.6;  --s: 0.78; }
.tarot-wrap[data-layer="front"] { opacity: 0.82; --s: 1; }"""
new_face = """.tarot-wrap[data-layer="back"]  { opacity: 0.30; --s: 0.60; --k: 1; }
.tarot-wrap[data-layer="mid"]   { opacity: 0.55; --s: 0.78; --k: 0; }
.tarot-wrap[data-layer="front"] { opacity: 0.55; --s: 1;    --k: 0; }

/* 远景牌不投阴影：22 张牌的阴影叠在一起，是"糊成一团"的主要来源之一。
   纵深靠「尺寸 + 透明度」表达，不用 filter:blur()——那会让每帧重新光栅化，
   正是当初吃掉几个 G 显存的东西。 */
.tarot-wrap[data-layer="back"] .tarot-face {
  box-shadow: 0 3px 8px -3px rgba(40,30,80,0.16);
}"""
assert old_face in src, '找不到 data-layer 分组规则'
src = src.replace(old_face, new_face, 1)

# ============================================================
# 5) 生成新的两套布局
# ============================================================
SLOTS_TOP = [16.0, 23.7, 31.4, 39.1, 46.8, 54.5, 62.2, 69.9, 77.6, 85.3, 93.0]
SHIFT = -4.0          # 滚动后整体上移 4%（≈半个节距），形成视差迟滞
SLOTS_SCR = [round(v + SHIFT, 1) for v in SLOTS_TOP]

# (卡号, 槽位, 缩放, 透明度)。槽位奇数 = 近景列，偶数 = 远景列，纵向交错。
LEFT = [
    (10, 0, 0.60, 0.30), (4, 1, 0.98, 0.56), (12, 2, 0.62, 0.28), (0, 3, 1.00, 0.54),
    (14, 4, 0.58, 0.26), (6, 5, 0.96, 0.52), (16, 6, 0.63, 0.27), (2, 7, 1.02, 0.50),
    (18, 8, 0.59, 0.25), (8, 9, 0.94, 0.48), (20, 10, 0.61, 0.24),
]
RIGHT = [
    (11, 0, 0.61, 0.29), (5, 1, 0.99, 0.55), (13, 2, 0.59, 0.27), (1, 3, 0.97, 0.53),
    (15, 4, 0.62, 0.26), (7, 5, 1.01, 0.51), (17, 6, 0.58, 0.25), (3, 7, 0.95, 0.49),
    (19, 8, 0.60, 0.24), (9, 9, 0.98, 0.47), (21, 10, 0.57, 0.23),
]


def rows(items, slots):
    out = []
    for idx, slot, s, op in items:
        out.append((idx, slots[slot], s, op, 1 if slot % 2 == 0 else 0))
    return sorted(out)


def render(state, slots, title, note):
    lines = ['/* ========== %s ========== */' % title]
    lines += ['/* %s */' % n for n in note]
    lines.append('')
    for idx, t, s, op, k in rows(LEFT + RIGHT, slots):
        lines.append('body.%s .tw-%-2d { --t: %4.1f%%; %s; --s: %s; --k: %d; opacity: %s; }'
                     % (state, idx, t,
                        '--l: var(--lx)' if idx % 2 == 0 else '--r: var(--rx)',
                        '%.2f' % s, k, '%.2f' % op))
    return '\n'.join(lines)


block = render(
    'layout-top', SLOTS_TOP,
    '布局 1（滚动前）｜近景列在内、远景列在外，纵向半节距交错',
    ['两侧各 11 张：近景列 5 张（--k:0，贴内容卡，大而实），',
     '远景列 6 张（--k:1，再向外让开一个牌宽，小而淡）。',
     '两列 x 区间不相交 + 同列相距 2 个槽位 ⇒ 任何视口下都不会互相压住。',
     '最上一张落在 16%，正好避开 38vh 的顶部横幅。']
) + '\n\n' + render(
    'layout-scrolled', SLOTS_SCR,
    '布局 2（滚动后）｜整体上移 4%，形成视差迟滞',
    ['相对布局 1 只是统一上移，相对位置不变 —— 所以同样不会叠。',
     '横幅滚出后，最上面几张正好接上原本被横幅挡住的区域。']
)

m = re.search(r'/\* ========== 布局 1（滚动前） ========== \*/.*?(?=/\* ========== 内容区 ========== \*/)',
              src, re.S)
assert m, '找不到布局区块'
src = src[:m.start()] + block + '\n\n' + src[m.end():]

# ============================================================
# 6) 收窄角度：原来 ±20° 的散角是"乱"的一半原因
# ============================================================
ROT_MAP = {'-14': '7', '13': '7', '8': '4', '-10': '-5', '6': '3', '-7': '-4',
           '-6': '-3', '7': '4', '-5': '-3', '5': '3', '9': '5', '-9': '-5',
           '-4': '-2', '4': '2', '-20': '-10', '15': '8', '-11': '-6',
           '19': '10', '-17': '-9'}


def fix_rot(mm):
    v = mm.group(1)
    return 'data-rotate="%s"' % ROT_MAP.get(v, v)


src = re.sub(r'data-rotate="(-?\d+)"', fix_rot, src)

# ============================================================
# 7) JS：把牌层高度对准正文真实高度
# ============================================================
anchor = """  window.addEventListener('resize', updateLayout, { passive: true });
  updateLayout();
"""
assert anchor in src, '找不到 updateLayout 收尾'
js_add = anchor + """
  // ---- 牌层高度 = 正文真实高度 ----
  // 层高写死 200vh，而页面实际约 250vh，底部那一截一张牌都没有，
  // 是"背景空"的一半原因。这里直接量 banner + 内容区的总高写进 --layer-h，
  // 槽位百分比就永远铺满整页；层是绝对定位、不参与布局，所以不会回调递归。
  function syncLayerHeight() {
    var cwEl = document.querySelector('.content-wrap');
    var h = 0;
    if (banner) h = Math.max(h, banner.offsetTop + banner.offsetHeight);
    if (cwEl)   h = Math.max(h, cwEl.offsetTop + cwEl.offsetHeight);
    h = Math.max(h, window.innerHeight);
    document.documentElement.style.setProperty('--layer-h', h + 'px');
  }
  syncLayerHeight();
  window.addEventListener('load', syncLayerHeight, { passive: true });
  window.addEventListener('resize', syncLayerHeight, { passive: true });
  if ('ResizeObserver' in window) {
    new ResizeObserver(syncLayerHeight).observe(
      document.querySelector('.content-wrap') || document.body);
  }
"""
src = src.replace(anchor, js_add, 1)

io.open(PATH, 'w', encoding='utf-8').write(src)
print('改动完成：%d -> %d 字符' % (len(orig), len(src)))
print()
print(render('layout-top', SLOTS_TOP, '布局 1', ['预览']))
