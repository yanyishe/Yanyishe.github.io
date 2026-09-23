# -*- coding: utf-8 -*-
"""
两种布局下的命中 / 翻牌验证（各取卡片与视口的交集中心作为采样点）。

为什么要取"交集中心"而不是卡片中心：卡片跨越首屏边界时，它自身的中心点落在
视口之外，elementFromPoint 直接返回 null —— 那是探针的取点问题，不是页面缺陷。
用户能点到的只有视口内那部分，所以采样点必须落在交集里。
"""
import io
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, 'index.html')
OUT = os.path.join(ROOT, '_probe3.html')

src = io.open(SRC, encoding='utf-8').read()

PROBE = r"""
<script>
function samplePoint(el) {
  var r = el.getBoundingClientRect();
  var x0 = Math.max(r.left, 0), x1 = Math.min(r.right, window.innerWidth);
  var y0 = Math.max(r.top, 0), y1 = Math.min(r.bottom, window.innerHeight);
  if (x1 - x0 < 6 || y1 - y0 < 6) return null;
  return { x: Math.round((x0 + x1) / 2), y: Math.round((y0 + y1) / 2) };
}

function audit(label) {
  var out = [label + '  (视口 ' + window.innerWidth + 'x' + window.innerHeight + ')'];
  var wraps = document.querySelectorAll('.tarot-wrap');
  var tested = 0, hit = 0, missed = [];
  for (var i = 0; i < wraps.length; i++) {
    var el = wraps[i];
    var p = samplePoint(el);
    if (!p) continue;
    tested++;
    var got = document.elementFromPoint(p.x, p.y);
    if (got && (got === el || el.contains(got))) hit++;
    else missed.push({
      name: el.className.replace('tarot-wrap ', ''),
      layer: el.getAttribute('data-layer'),
      at: p.x + ',' + p.y,
      by: got ? got.tagName.toLowerCase() + '.' + String(got.className).split(' ')[0] : 'null'
    });
  }
  out.push('  命中 ' + hit + ' / ' + tested + ' 张（采样点落在视口内的牌）');
  for (var m = 0; m < missed.length; m++) {
    out.push('    x ' + missed[m].name + ' [' + missed[m].layer + '] @' + missed[m].at
             + '  被 ' + missed[m].by + ' 挡住');
  }
  if (!missed.length) out.push('    全部可命中 OK');

  // 翻牌：对第一张命中的牌派发 click，检查状态与正面素材
  for (var j = 0; j < wraps.length; j++) {
    var e2 = wraps[j], p2 = samplePoint(e2);
    if (!p2) continue;
    var g2 = document.elementFromPoint(p2.x, p2.y);
    if (!(g2 && (g2 === e2 || e2.contains(g2)))) continue;
    e2.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));
    var front = e2.querySelector('.tarot-front');
    var bg = front ? getComputedStyle(front).backgroundImage : 'none';
    out.push('  翻牌: ' + e2.className.replace('tarot-wrap ', '')
             + '  class=' + (e2.className.indexOf('flipped') >= 0 ? 'OK' : 'FAIL')
             + '  正面图=' + (bg && bg !== 'none' ? 'OK' : 'FAIL'));
    e2.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));
    out.push('  翻回: ' + (e2.className.indexOf('flipped') < 0 ? 'OK' : 'FAIL'));
    break;
  }

  // 内容面板仍须可交互
  var mc = document.querySelector('.main-container');
  var mr = mc.getBoundingClientRect();
  var py = Math.min(Math.max(mr.top + 80, 10), window.innerHeight - 10);
  var el3 = document.elementFromPoint(Math.round(mr.left + mr.width / 2), Math.round(py));
  out.push('  面板内命中: ' + (el3 && mc.contains(el3)
    ? 'OK (' + el3.tagName.toLowerCase() + ')'
    : 'FAIL -> ' + (el3 ? el3.tagName.toLowerCase() + '.' + String(el3.className).split(' ')[0] : 'null')));
  return out.join('\n');
}

var lines = [];
setTimeout(function () {
  lines.push(audit('【布局 layout-top 滚动前】'));
  document.body.className = 'layout-scrolled';
  setTimeout(function () {
    lines.push('');
    lines.push(audit('【布局 layout-scrolled 滚动后】'));
    var b = document.createElement('div');
    b.style.cssText = 'position:fixed;z-index:99999;top:0;left:0;background:rgba(0,0,0,.9);'
      + 'color:#0ff;font:15px/1.5 monospace;padding:14px;white-space:pre;pointer-events:none';
    b.textContent = lines.join('\n');
    document.body.appendChild(b);
  }, 1700);
}, 800);
</script>
"""

io.open(OUT, 'w', encoding='utf-8').write(src.replace('</body>', PROBE + '</body>'))
print('probe3 -> ' + OUT)
