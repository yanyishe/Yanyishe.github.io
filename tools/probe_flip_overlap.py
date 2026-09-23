# -*- coding: utf-8 -*-
"""
实测断言：把所有可见的牌都翻开（最坏情况），量它们之间是否重叠。

不复刻 CSS 公式，而是直接读浏览器算出来的最终矩形 ——
因为这轮改动加的是「透视 + 3D 位移」，投影后的实际尺寸没法靠手算保证。

顺带量两件事：
  · 翻开的牌和内容卡之间的净间隙（不能被推进内容卡里）
  · 翻开的牌相对未翻开时的放大 / 上浮量

用法：python probe_flip_overlap.py  →  生成 _overlap.html
      两种布局各生成一份，分别截图读数。
"""
import io
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, 'index.html')

# 无头环境不推进 CSS transition：位置过渡和翻牌过渡都关掉，
# 这样"切换布局"和"点击翻牌"都立刻落到终点态，量到的才是最终几何。
NO_TRANSITION = (
    '<style>'
    '.tarot-wrap, .tarot-card { transition: none !important; }'
    '</style>'
)

PROBE = r"""
<script>
setTimeout(function () {
  var LAYOUT = '__LAYOUT__';
  if (LAYOUT === 'scrolled') document.body.className = 'layout-scrolled';

  var wraps = document.querySelectorAll('.tarot-wrap');
  var cards = [], i;
  for (i = 0; i < wraps.length; i++) {
    var w = wraps[i];
    if (w.getBoundingClientRect().width < 4) continue;   // 该布局下被隐藏的牌
    w.dispatchEvent(new MouseEvent('click', { bubbles: true }));  // 全部翻开
  }
  void document.body.offsetWidth;

  function rectOf(w) {
    var c = w.querySelector('.tarot-card');
    var r = c.getBoundingClientRect();
    return { n: w.className.replace('tarot-wrap ', '').trim(),
             x: r.left, y: r.top, w: r.width, h: r.height,
             cx: r.left + r.width / 2, cy: r.top + r.height / 2 };
  }
  for (i = 0; i < wraps.length; i++) {
    if (wraps[i].getBoundingClientRect().width < 4) continue;
    cards.push(rectOf(wraps[i]));
  }

  // ---- 两两求交 ----
  var bad = [];
  for (i = 0; i < cards.length; i++) {
    for (var j = i + 1; j < cards.length; j++) {
      var a = cards[i], b = cards[j];
      var ox = Math.min(a.x + a.w, b.x + b.w) - Math.max(a.x, b.x);
      var oy = Math.min(a.y + a.h, b.y + b.h) - Math.max(a.y, b.y);
      if (ox > 0.5 && oy > 0.5) bad.push(a.n + '×' + b.n
        + ' (' + ox.toFixed(1) + '×' + oy.toFixed(1) + ')');
    }
  }

  // ---- 翻开的牌 vs 内容卡：最近的那张留多少净空 ----
  var mc = document.querySelector('.main-container').getBoundingClientRect();
  var minGap = 1e9, gapWho = '';
  for (i = 0; i < cards.length; i++) {
    var c = cards[i];
    var gap = c.x < mc.left ? (mc.left - (c.x + c.w)) : (c.x - mc.right);
    if (gap < minGap) { minGap = gap; gapWho = c.n; }
  }

  // ---- 放大 / 上浮：同一张牌翻开前后对比 ----
  var probe = wraps[0], k;
  for (k = 0; k < wraps.length; k++) {
    if (wraps[k].getBoundingClientRect().width < 4) continue;
    probe = wraps[k]; break;
  }
  probe.classList.remove('flipped');
  void document.body.offsetWidth;
  var before = probe.querySelector('.tarot-card').getBoundingClientRect();
  probe.classList.add('flipped');
  void document.body.offsetWidth;
  var after = probe.querySelector('.tarot-card').getBoundingClientRect();

  var out = [];
  out.push('布局 = ' + LAYOUT + '    视口 ' + window.innerWidth + 'x' + window.innerHeight);
  out.push('可见牌 ' + cards.length + ' 张，全部翻开');
  out.push('两两重叠 = ' + (bad.length ? bad.length + ' 对  ' + bad.slice(0, 4).join(', ') : '0 对 ✓'));
  out.push('翻开后离内容卡最近净空 = ' + minGap.toFixed(1) + 'px  (' + gapWho + ')');
  out.push('单卡放大 = ' + (after.width / before.width).toFixed(3)
           + '    上浮 = ' + (before.top - after.top).toFixed(1) + 'px');

  var box = document.createElement('div');
  box.style.cssText = 'position:fixed;z-index:99999;top:0;left:0;background:#000;'
    + 'color:#0f0;font:19px/1.55 monospace;padding:14px;white-space:pre;pointer-events:none';
  box.textContent = out.join('\n');
  document.body.appendChild(box);
}, 900);
</script>
"""

src = io.open(SRC, encoding='utf-8').read()
# async 解码在虚拟时钟下偶发来不及，图会空白（环境噪声）
src = src.replace('decoding="async"', 'decoding="sync"')

for layout in ('top', 'scrolled'):
    html = src.replace('</head>', NO_TRANSITION + '</head>')
    html = html.replace('</body>', PROBE.replace('__LAYOUT__', layout) + '</body>')
    out = os.path.join(ROOT, '_overlap_%s.html' % layout)
    io.open(out, 'w', encoding='utf-8').write(html)
    print('overlap probe -> ' + out)
