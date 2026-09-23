# -*- coding: utf-8 -*-
"""诊断未被 elementFromPoint 命中的牌：是坐标在视口外，还是真被遮挡。"""
import io
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, 'index.html')
OUT = os.path.join(ROOT, '_probe2.html')

src = io.open(SRC, encoding='utf-8').read()

PROBE = r"""
<script>
setTimeout(function () {
  var out = [], wraps = document.querySelectorAll('.tarot-wrap');
  var n = 0;
  for (var i = 0; i < wraps.length; i++) {
    var el = wraps[i];
    var r = el.getBoundingClientRect();
    if (r.width < 1) continue;
    var cx = Math.round(r.left + r.width / 2);
    var cy = Math.round(r.top + r.height / 2);
    var inVp = (cx >= 0 && cx < window.innerWidth && cy >= 0 && cy < window.innerHeight);
    var hit = inVp ? document.elementFromPoint(cx, cy) : null;
    var ok = hit && (hit === el || el.contains(hit));
    if (ok) continue;
    n++;
    var name = el.className.replace('tarot-wrap ', '');
    var layer = el.getAttribute('data-layer');
    out.push('[' + name + ' ' + layer + ']');
    out.push('   rect x ' + Math.round(r.left) + '~' + Math.round(r.right)
             + '  y ' + Math.round(r.top) + '~' + Math.round(r.bottom)
             + '  (视口 ' + window.innerWidth + 'x' + window.innerHeight + ')');
    out.push('   中心 (' + cx + ',' + cy + ')  在视口内: ' + inVp);
    if (!inVp) {
      out.push('   -> 原因: 中心点在视口外，属探针边界情况，非页面缺陷');
    } else {
      out.push('   -> 命中元素: ' + (hit ? hit.tagName.toLowerCase() + '.' + hit.className : 'null'));
    }
  }
  if (!n) out.push('全部可见牌均可命中');
  var b = document.createElement('div');
  b.style.cssText = 'position:fixed;z-index:99999;top:0;left:0;background:rgba(0,0,0,.88);'
    + 'color:#0ff;font:14px/1.55 monospace;padding:12px;white-space:pre;pointer-events:none';
  b.textContent = out.join('\n');
  document.body.appendChild(b);
}, 900);
</script>
"""

io.open(OUT, 'w', encoding='utf-8').write(src.replace('</body>', PROBE + '</body>'))
print('probe2 -> ' + OUT)
