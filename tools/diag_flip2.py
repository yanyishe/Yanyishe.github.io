# -*- coding: utf-8 -*-
"""
决定性对照：临时关掉 transition，直接比较 flipped 前后的计算矩阵。

用来区分两种可能：
  (a) CSS 规则没生效        -> after 仍是 2D matrix
  (b) 规则生效、只是虚拟时钟不推进 CSS transition -> after 是 matrix3d(-1,...)
"""
import io
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, 'index.html')
OUT = os.path.join(ROOT, '_diag2.html')

src = io.open(SRC, encoding='utf-8').read()

PROBE = r"""
<script>
function render(lines) {
  var b = document.createElement('div');
  b.style.cssText = 'position:fixed;z-index:99999;top:0;left:0;background:#000;color:#0ff;'
    + 'font:15px/1.45 monospace;padding:14px;white-space:pre;pointer-events:none';
  b.textContent = lines.join('\n');
  document.body.appendChild(b);
}

setTimeout(function () {
  var out = [];
  var wraps = document.querySelectorAll('.tarot-wrap');
  var target = null;
  for (var i = 0; i < wraps.length; i++) {
    var r = wraps[i].getBoundingClientRect();
    if (r.width > 4 && r.top > 60 && r.bottom < window.innerHeight - 20) { target = wraps[i]; break; }
  }

  if (!target) { render(['没有合适的可见牌']); return; }

  var card = target.querySelector('.tarot-card');

  function show(label) {
    var cs = getComputedStyle(card);
    out.push(label);
    out.push('  klass     = ' + target.className.replace('tarot-wrap ', ''));
    out.push('  matches   = ' + card.matches('.tarot-wrap.flipped .tarot-card'));
    out.push('  --rot     = ' + cs.getPropertyValue('--rot').trim());
    out.push('  transform = ' + cs.transform);
  }

  // 关掉过渡，排除"虚拟时钟不推进 CSS transition"的干扰
  card.style.transition = 'none';

  target.classList.remove('flipped');
  void card.offsetWidth;
  show('[A] 未加 flipped（期望 2D matrix）');

  target.classList.add('flipped');
  void card.offsetWidth;
  show('[B] 已加 flipped（期望 matrix3d，首项 -1）');

  // 恢复过渡，再触发一次状态变化，看 1.3s 后停在哪
  card.style.transition = '';
  target.classList.remove('flipped');
  void card.offsetWidth;

  setTimeout(function () {
    out.push('[C] 恢复过渡、翻回 1.3s 后（期望回到 2D matrix）');
    out.push('  transform = ' + getComputedStyle(card).transform);
    out.push('  -> 若停在 matrix3d，说明本环境不推进 CSS transition');
    render(out);
  }, 1300);
}, 1400);
</script>
"""

io.open(OUT, 'w', encoding='utf-8').write(src.replace('</body>', PROBE + '</body>'))
print('diag2 -> ' + OUT)
