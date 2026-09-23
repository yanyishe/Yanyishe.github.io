# -*- coding: utf-8 -*-
"""诊断翻牌到底停在哪一层：内联 transform / 计算 transform / 透视 / 帧率。"""
import io
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, 'index.html')
OUT = os.path.join(ROOT, '_diag.html')

src = io.open(SRC, encoding='utf-8').read()

PROBE = r"""
<script>
var rafCount = 0;
(function tick() { rafCount++; requestAnimationFrame(tick); })();

setTimeout(function () {
  var out = [];
  var wraps = document.querySelectorAll('.tarot-wrap');

  // 选一张视口内可见的牌
  var target = null;
  for (var i = 0; i < wraps.length; i++) {
    var r = wraps[i].getBoundingClientRect();
    if (r.width > 4 && r.top > 60 && r.bottom < window.innerHeight - 20) { target = wraps[i]; break; }
  }
  if (!target) { out.push('没有合适的可见牌'); }

  if (target) {
    target.dispatchEvent(new MouseEvent('click', { bubbles: true }));
  }

  // 等 0.75s 的翻牌过渡走完再读数（虚拟时钟下同样会快进）
  setTimeout(function () {
  if (target) {
    var card = target.querySelector('.tarot-card');
    var front = target.querySelector('.tarot-front');

    out.push('class       : ' + target.className.replace('tarot-wrap ', ''));
    out.push('rAF frames  : ' + rafCount + '  (全程)');
    out.push('wrap persp  : ' + getComputedStyle(target).perspective);
    out.push('card compute: ' + getComputedStyle(card).transform);
    out.push('card style  : ' + getComputedStyle(card).transformStyle);
    out.push('front bg    : ' + (getComputedStyle(front).backgroundImage || 'none').slice(0, 46));
    out.push('front transf: ' + getComputedStyle(front).transform);
  }

  var box = document.createElement('div');
  box.style.cssText = 'position:fixed;z-index:99999;top:0;left:0;background:#000;color:#0ff;'
    + 'font:17px/1.55 monospace;padding:14px;white-space:pre;pointer-events:none';
  box.textContent = out.join('\n');
  document.body.appendChild(box);
  }, 1300);
}, 1600);
</script>
"""

io.open(OUT, 'w', encoding='utf-8').write(src.replace('</body>', PROBE + '</body>'))
print('diag -> ' + OUT)
