# -*- coding: utf-8 -*-
"""
音效验证：把 AudioContext 换成计数桩，让"到底有没有真的合成声音"
变成可以截图看见的数字。

为什么不用真音频验证：无头环境没有声卡，AudioContext 大概率是 suspended，
"有没有出声"根本无法从外部观测。所以验证的是**合成管线有没有被驱动** ——
只要 createBufferSource / createOscillator 被调用，真实浏览器里就一定出声。

产出三个变体：
  _sfx_verify.html  完整验证浮层，结束时停在静音态
  _sfx_open.html    只解锁不静音，按钮停在"开"
  _sfx_shut.html    点过开关，按钮停在"关"
"""
import io
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, 'index.html')

# ---- 计数桩：完整实现页面用到的那一小撮 Web Audio API ----
STUB = r"""
<script>
(function () {
  var C = { ctx: 0, noise: 0, burst: 0, tone: 0 };
  window.__sfxC = C;
  function param(v) {
    return {
      value: v || 0,
      setValueAtTime: function () { return this; },
      exponentialRampToValueAtTime: function () { return this; },
      linearRampToValueAtTime: function () { return this; }
    };
  }
  function node() {
    return {
      connect: function () { return this; },
      start: function () {}, stop: function () {},
      frequency: param(), gain: param(), Q: param(),
      playbackRate: param(), type: '', buffer: null, loop: false
    };
  }
  function AC() {
    C.ctx++;
    var self = this;
    this.state = 'running';
    this.sampleRate = 48000;
    this.currentTime = 0;
    this.destination = {};
    this.createBuffer = function (ch, len) {
      C.noise++;
      return { getChannelData: function () { return new Float32Array(len || 1); } };
    };
    this.createBufferSource = function () { C.burst++; return node(); };
    this.createOscillator = function () { C.tone++; return node(); };
    this.createBiquadFilter = function () { return node(); };
    this.createGain = function () { return node(); };
    this.resume = function () { self.state = 'running'; return { 'catch': function () {} }; };
    this.suspend = function () { self.state = 'suspended'; return { 'catch': function () {} }; };
  }
  window.AudioContext = AC;
  window.webkitAudioContext = AC;
})();
</script>
"""

VERIFY = r"""
<script>
function __vis(sel) {
  var el = document.querySelector(sel);
  if (!el) return '不存在';
  return String(getComputedStyle(el).display !== 'none');
}
setTimeout(function () {
  var C = window.__sfxC, out = [];
  var btn = document.getElementById('sfxToggle');

  out.push('[1] 页面加载完成，还没有任何手势');
  out.push('    AudioContext 创建次数 = ' + C.ctx + '    0 = 没有提前建，符合预期');
  out.push('    aria-pressed=' + btn.getAttribute('aria-pressed')
           + '   label="' + btn.getAttribute('aria-label') + '"');
  out.push('    ico-on 显示=' + __vis('.sfx-toggle .ico-on')
           + '   ico-off 显示=' + __vis('.sfx-toggle .ico-off'));

  window.dispatchEvent(new PointerEvent('pointerdown', { bubbles: true }));
  out.push('');
  out.push('[2] 首次按下任意位置（解锁时机）');
  out.push('    AudioContext 创建次数 = ' + C.ctx + '    1 = 在手势内建好');
  out.push('    噪声缓冲生成次数 = ' + C.noise + '    1 = 只生成一次，之后复用');

  var card = document.querySelector('.tarot-wrap.tw-4');
  var b = C.burst;
  card.dispatchEvent(new MouseEvent('mouseenter'));
  out.push('');
  out.push('[3] 悬停一张牌');
  out.push('    噪声源节点 +' + (C.burst - b) + '    1 = tick 响了');

  var b0 = C.burst, t0 = C.tone;
  card.dispatchEvent(new MouseEvent('click', { bubbles: true }));
  card.dispatchEvent(new MouseEvent('click', { bubbles: true }));
  card.dispatchEvent(new MouseEvent('click', { bubbles: true }));
  out.push('');
  out.push('[4] 连点同一张牌 3 次');
  out.push('    噪声源 +' + (C.burst - b0) + '   振荡器 +' + (C.tone - t0)
           + '    3+3 = 每次翻牌 1 扫频噪声 + 1 低频正弦');
  out.push('    牌已翻转 = ' + card.classList.contains('flipped'));

  var b1 = C.burst;
  for (var k = 0; k < 6; k++) card.dispatchEvent(new MouseEvent('mouseenter'));
  out.push('');
  out.push('[5] 同一瞬间连发 6 次 mouseenter');
  out.push('    噪声源 +' + (C.burst - b1) + '    <=1 = 70ms 节流生效，没连成一片');

  btn.click();
  out.push('');
  out.push('[6] 点击开关 → 静音');
  out.push('    aria-pressed=' + btn.getAttribute('aria-pressed')
           + '   label="' + btn.getAttribute('aria-label') + '"');
  out.push('    ico-on 显示=' + __vis('.sfx-toggle .ico-on')
           + '   ico-off 显示=' + __vis('.sfx-toggle .ico-off'));
  var b2 = C.burst, t2 = C.tone;
  card.dispatchEvent(new MouseEvent('click', { bubbles: true }));
  card.dispatchEvent(new MouseEvent('mouseenter'));
  out.push('    静音后再翻牌 + 悬停：噪声 +' + (C.burst - b2)
           + '   振荡器 +' + (C.tone - t2) + '    0/0 = 真的没出声');
  try {
    out.push('    localStorage[yys-sfx] = ' + localStorage.getItem('yys-sfx'));
  } catch (e) {
    out.push('    localStorage 不可用（file:// 下被限制）');
  }

  var box = document.createElement('div');
  box.style.cssText = 'position:fixed;left:14px;top:14px;z-index:99999;'
    + 'background:rgba(8,8,14,0.94);color:#7ff0d8;padding:16px 20px;'
    + 'font:13px/1.62 Consolas,monospace;white-space:pre;border-radius:10px;'
    + 'border:1px solid rgba(127,240,216,0.28);pointer-events:none';
  box.textContent = out.join('\n');
  document.body.appendChild(box);
}, 1200);
</script>
"""

# 只做"解锁 + 可选静音"，用来观察按钮的两种图标状态
TOUCH = r"""
<script>
setTimeout(function () {
  var btn = document.getElementById('sfxToggle');
  window.dispatchEvent(new PointerEvent('pointerdown', { bubbles: true }));
  if (%s) { btn.click(); }
}, 900);
</script>
"""

src = io.open(SRC, encoding='utf-8').read()
# 无头环境里 async 解码偶发来不及，统一改同步
src = src.replace('decoding="async"', 'decoding="sync"')


def emit(name, extra):
    html = src.replace('</head>', STUB + '</head>')
    html = html.replace('</body>', extra + '</body>')
    path = os.path.join(ROOT, name)
    io.open(path, 'w', encoding='utf-8').write(html)
    print('variant -> ' + name)


emit('_sfx_verify.html', VERIFY)
emit('_sfx_open.html', TOUCH % 'false')
emit('_sfx_shut.html', TOUCH % 'true')
