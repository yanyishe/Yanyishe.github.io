# -*- coding: utf-8 -*-
"""
诊断：翻开后的牌是否真的"浮起来"了。

关掉过渡后直接读计算矩阵，检查三件事：
  1. 矩阵是 3D（matrix3d）而不是被压平的 2D matrix
  2. rotateY(180deg) 生效（首项 ≈ -cos(rot)）
  3. 含 Z 轴方向的推进（透视换算出的放大 > 1）
"""
import io
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, 'index.html')
OUT = os.path.join(ROOT, '_diag3.html')

src = io.open(SRC, encoding='utf-8').read()

NO_TRANSITION = '<style>.tarot-card { transition: none !important; }</style>'

PROBE = r"""
<script>
setTimeout(function () {
  var out = [];
  var wraps = document.querySelectorAll('.tarot-wrap');
  var flipped = null, plain = null, i;
  for (i = 0; i < wraps.length; i++) {
    var r = wraps[i].getBoundingClientRect();
    if (r.width < 4 || r.bottom < 20 || r.top > window.innerHeight - 20) continue;
    if (!flipped) flipped = wraps[i];
    else if (!plain) { plain = wraps[i]; break; }
  }

  function dump(w, tag) {
    if (!w) { out.push(tag + ': 无可见牌'); return; }
    var c = w.querySelector('.tarot-card');
    var r = c.getBoundingClientRect();
    var cs = getComputedStyle(c);
    out.push(tag + '  ' + w.className.replace('tarot-wrap ', ''));
    out.push('   transform   = ' + (cs.transform || 'none').slice(0, 96));
    out.push('   视觉宽高    = ' + r.width.toFixed(1) + ' x ' + r.height.toFixed(1));
    out.push('   perspective = ' + getComputedStyle(w).perspective);
    out.push('   card 透明   = ' + cs.opacity + '   z-index(wrap) = '
             + getComputedStyle(w).zIndex);
  }

  if (flipped) {
    var card = flipped.querySelector('.tarot-card');
    var before = card.getBoundingClientRect();
    flipped.dispatchEvent(new MouseEvent('click', { bubbles: true }));
    void document.body.offsetWidth;          // 强制样式重算
    var after = card.getBoundingClientRect();
    dump(flipped, '[翻开的牌]');
    out.push('   放大倍数 = ' + (after.width / before.width).toFixed(3)
             + '   上浮 = ' + (before.top - after.top).toFixed(1) + 'px');
    out.push('   中心是否仍对齐 = '
             + (Math.abs((after.left + after.width / 2) - (before.left + before.width / 2)) < 1.5
                ? '是 ✓（只上浮，没有横移）' : '否 ✗ 有横移'));
  }
  dump(plain, '[对照：未翻开的牌]');

  var box = document.createElement('div');
  box.style.cssText = 'position:fixed;z-index:99999;top:0;left:0;background:#000;'
    + 'color:#0ff;font:16px/1.5 monospace;padding:14px;white-space:pre;pointer-events:none';
  box.textContent = out.join('\n');
  document.body.appendChild(box);
}, 1400);
</script>
"""

html = src.replace('</head>', NO_TRANSITION + '</head>')
html = html.replace('</body>', PROBE + '</body>')
io.open(OUT, 'w', encoding='utf-8').write(html)
print('diag -> ' + OUT)
