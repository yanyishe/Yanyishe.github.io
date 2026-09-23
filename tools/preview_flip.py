# -*- coding: utf-8 -*-
"""
预览：真实点击若干张牌后的翻牌 + "浮起来"的结果。

无头 + virtual-time 环境不推进 CSS transition，所以这里临时关掉 .tarot-card 的
transform 过渡，让点击结果直接落到终点态，才拍得到翻开的正面。
真实浏览器里同样会走到这个状态，只是中间多了 0.8s 的翻转 + 抬起动画。

翻开的是偶数张，和未翻开的奇数张相邻排列，方便直接对比"浮起来"的差别。
"""
import io
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, 'index.html')
OUT = os.path.join(ROOT, '_flip.html')

src = io.open(SRC, encoding='utf-8').read()

NO_TRANSITION = (
    '<style>/* 预览专用：无头环境不推进 CSS transition，'
    '关掉才能拍到翻牌终点态 */\n'
    '.tarot-card { transition: none !important; }</style>'
)

PROBE = r"""
<script>
setTimeout(function () {
  var wraps = document.querySelectorAll('.tarot-wrap');
  var i;
  // 先翻开视口内偶数序号的牌，奇数序号留作对照
  var vis = [];
  for (i = 0; i < wraps.length; i++) {
    var r = wraps[i].getBoundingClientRect();
    if (r.width < 4) continue;
    if (r.bottom < 20 || r.top > window.innerHeight - 20) continue;
    vis.push(wraps[i]);
  }
  for (i = 0; i < vis.length; i++) {
    if (i % 2 === 0) vis[i].dispatchEvent(new MouseEvent('click', { bubbles: true }));
  }
}, 900);
</script>
"""

html = src.replace('</head>', NO_TRANSITION + '</head>')
html = html.replace('</body>', PROBE + '</body>')
# 无头 + 虚拟时钟下 async 解码偶发来不及，图会空白（环境噪声，不是页面问题）。
# 预览副本改成同步解码，让图上得齐。
html = html.replace('decoding="async"', 'decoding="sync"')
io.open(OUT, 'w', encoding='utf-8').write(html)
print('flip preview -> ' + OUT)
