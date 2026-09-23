# -*- coding: utf-8 -*-
"""
验证"点击翻牌"链路：
  A. 命中测试 —— elementFromPoint 每张可见牌的中心点，看指针是否真的落在牌上
  B. 事件测试 —— 对命中的牌派发真实 click，检查 flipped class 与正面背景是否写入
结果画到页面上，靠截图读回来（无头模式拿不到 stdout）。
"""
import io
import re
import sys
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, 'index.html')
OUT = os.path.join(ROOT, '_probe.html')

src = io.open(SRC, encoding='utf-8').read()

PROBE = r"""
<script>
setTimeout(function () {
  var out = [];
  var wraps = document.querySelectorAll('.tarot-wrap');
  var visible = [];
  for (var i = 0; i < wraps.length; i++) {
    var r = wraps[i].getBoundingClientRect();
    if (r.width < 1) continue;
    if (r.bottom < 0 || r.top > window.innerHeight) continue;
    visible.push(wraps[i]);
  }

  // ---- A. 命中测试 ----
  var hit = 0, blocked = {};
  var hitList = [];
  for (var j = 0; j < visible.length; j++) {
    var rr = visible[j].getBoundingClientRect();
    var cx = rr.left + rr.width / 2, cy = rr.top + rr.height / 2;
    var el = document.elementFromPoint(cx, cy);
    if (el && (el === visible[j] || visible[j].contains(el))) {
      hit++; hitList.push(visible[j]);
    } else {
      var d = el ? (el.tagName.toLowerCase() + '.' + el.className) : 'null';
      blocked[d] = (blocked[d] || 0) + 1;
    }
  }
  out.push('A 命中: ' + hit + ' / ' + visible.length + ' 张可见牌');
  for (var k in blocked) out.push('    被挡: ' + k + ' x' + blocked[k]);

  // ---- B. 事件测试：点第一张命中的牌 ----
  if (hitList.length) {
    var t = hitList[0];
    var before = t.className;
    t.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));
    var after = t.className;
    var front = t.querySelector('.tarot-front');
    var bg = front ? getComputedStyle(front).backgroundImage : 'none';
    var card = t.querySelector('.tarot-card');
    out.push('B 点击: ' + t.className.replace('tarot-wrap ', ''));
    out.push('    flipped class: ' + (after.indexOf('flipped') >= 0 ? '已加上 OK' : '未变化 FAIL'));
    out.push('    正面背景图  : ' + (bg && bg !== 'none' ? '已写入 OK' : '仍为空 FAIL'));
    // 再点一次，确认能翻回
    t.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));
    out.push('    二次点击翻回: ' + (t.className.indexOf('flipped') < 0 ? 'OK' : 'FAIL'));
  } else {
    out.push('B 点击: 无牌可点');
  }

  // ---- C. 内容区可交互性：面板里的元素仍能命中 ----
  var mc = document.querySelector('.main-container');
  var mr = mc.getBoundingClientRect();
  var probeY = Math.min(mr.top + 60, window.innerHeight - 5);
  var el2 = document.elementFromPoint(mr.left + mr.width / 2, probeY);
  out.push('C 面板内命中: ' + (el2 && mc.contains(el2)
    ? 'OK (' + el2.tagName.toLowerCase() + ')' : 'FAIL 被穿透到 ' + (el2 ? el2.className : 'null')));

  var box = document.createElement('div');
  box.style.cssText = 'position:fixed;z-index:99999;top:0;left:0;background:rgba(0,0,0,.88);'
    + 'color:#0f0;font:16px/1.6 monospace;padding:12px;white-space:pre;pointer-events:none';
  box.textContent = out.join('\n');
  document.body.appendChild(box);
}, 900);
</script>
"""

io.open(OUT, 'w', encoding='utf-8').write(src.replace('</body>', PROBE + '</body>'))
print('probe -> ' + OUT)
