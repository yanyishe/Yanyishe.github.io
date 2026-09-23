# -*- coding: utf-8 -*-
"""
验证音效链路。

声音截不出来，所以这里换一种验证方式：把 window.AudioContext 换成 mock，
记录每一次发声到底创建了哪些节点、参数怎么走。
断言：悬停/翻牌各自触发正确的音色、静音开关真的拦得住、指数斜坡端点不为 0
（后者是真实浏览器会直接抛 InvalidStateError 的写法，mock 能提前抓住）。
"""
import io
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, 'index.html')
OUT = os.path.join(ROOT, '_probe_sfx.html')

src = io.open(SRC, encoding='utf-8').read()

PROBE = r"""
<script>
(function () {
  var LOG = [], BAD = [];

  // ---- mock：只实现页面真正用到的那几个接口 ----
  function P(v, label) { this.label = label; this.last = v; this.v = v; }
  P.prototype.setValueAtTime = function (v) { this.last = v; this.v = v; return this; };
  P.prototype.linearRampToValueAtTime = function (v) { this.last = v; this.v = v; return this; };
  P.prototype.setTargetAtTime = function (v) { this.last = v; return this; };
  P.prototype.cancelScheduledValues = function () { return this; };
  P.prototype.exponentialRampToValueAtTime = function (v) {
    // 真实 Web Audio 里，指数斜坡的起点或终点为 0 会抛 InvalidStateError
    if (!(this.last > 0) || !(v > 0)) {
      BAD.push(this.label + ' 指数斜坡端点含 0 (from ' + this.last + ' to ' + v + ')');
    }
    this.last = v; this.v = v; return this;
  };

  function N(kind) { this.kind = kind; this.out = []; }
  N.prototype.connect = function (d) { this.out.push(d && d.kind); return d; };
  N.prototype.disconnect = function () {};

  function MockAC() {
    LOG.push('AudioContext');
    this.state = 'running';
    this.sampleRate = 48000;
    this.currentTime = 0;
    this.destination = { kind: 'destination' };
  }
  MockAC.prototype.resume = function () { LOG.push('resume'); return { then: function () {} }; };
  MockAC.prototype.createBuffer = function (ch, len) {
    LOG.push('createBuffer(' + len + ')');
    return { length: len, getChannelData: function () { return new Float32Array(len); } };
  };
  MockAC.prototype.createBufferSource = function () {
    var n = new N('bufferSource');
    n.buffer = null;
    n.playbackRate = new P(1, 'bufferSource.playbackRate');
    n.start = function (t) { n.t0 = t; };
    n.stop = function (t) { n.t1 = t; };
    LOG.push('bufferSource'); return n;
  };
  MockAC.prototype.createOscillator = function () {
    var n = new N('oscillator');
    n.type = 'sine';
    n.frequency = new P(350, 'oscillator.frequency');
    n.start = function (t) { n.t0 = t; };
    n.stop = function (t) { n.t1 = t; };
    LOG.push('oscillator'); return n;
  };
  MockAC.prototype.createGain = function () {
    var n = new N('gain');
    n.gain = new P(1, 'gain.gain');
    LOG.push('gain'); return n;
  };
  MockAC.prototype.createBiquadFilter = function () {
    var n = new N('biquad');
    n.type = 'lowpass';
    n.Q = new P(1, 'biquad.Q');
    n.frequency = new P(350, 'biquad.frequency');
    LOG.push('biquad'); return n;
  };

  window.AudioContext = MockAC;
  window.webkitAudioContext = MockAC;

  // ---- 工具 ----
  var out = [];
  function count(k) {
    var c = 0;
    for (var i = 0; i < LOG.length; i++) if (LOG[i] === k) c++;
    return c;
  }
  function snap() {
    return { src: count('bufferSource'), osc: count('oscillator'),
             gain: count('gain'), bp: count('biquad') };
  }
  function diff(a, b) {
    return '噪源+' + (b.src - a.src) + ' 振荡器+' + (b.osc - a.osc)
         + ' 增益+' + (b.gain - a.gain) + ' 带通+' + (b.bp - a.bp);
  }
  function wait(ms) { return new Promise(function (r) { setTimeout(r, ms); }); }
  function vis() {
    var ws = document.querySelectorAll('.tarot-wrap'), r = [];
    for (var i = 0; i < ws.length; i++) {
      var b = ws[i].getBoundingClientRect();
      if (b.width > 1 && b.bottom > 0 && b.top < window.innerHeight) r.push(ws[i]);
    }
    return r;
  }

  setTimeout(function () {
    var vs = vis();
    out.push('可见牌 ' + vs.length + ' 张');

    // 1) 手势解锁
    window.dispatchEvent(new Event('pointerdown', { bubbles: true }));
    out.push('1 首次手势 -> AudioContext ' + (count('AudioContext') ? '已创建 OK' : '未创建 FAIL')
      + ' / 噪声源 ' + LOG.filter(function (s) { return s.indexOf('createBuffer') === 0; }).join(''));

    var s0 = snap();

    // 2) 悬停 -> tick
    vs[0].dispatchEvent(new MouseEvent('mouseenter'));
    var s1 = snap();
    out.push('2 悬停 tick: ' + diff(s0, s1)
      + (s1.src === s0.src + 1 && s1.bp === s0.bp + 1 && s1.gain === s0.gain + 1 ? '  OK' : '  FAIL'));

    // 3) 同一瞬间的第二张牌，应被 70ms 节流吃掉
    vs[1].dispatchEvent(new MouseEvent('mouseenter'));
    var s2 = snap();
    out.push('3 节流(70ms 内二次悬停): ' + (s2.src === s1.src ? '已抑制 OK' : '仍发声 FAIL'));

    return wait(140).then(function () {
      // 4) 点击 -> flip
      vs[0].dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));
      var s3 = snap();
      out.push('4 翻牌 flip: ' + diff(s2, s3)
        + (s3.src === s2.src + 1 && s3.osc === s2.osc + 1 ? '  OK' : '  FAIL'));
      out.push('   flipped class: ' + (vs[0].className.indexOf('flipped') >= 0 ? '已加上 OK' : '未变化 FAIL'));

      // 5) 静音
      var btn = document.getElementById('sfxToggle');
      out.push('5 开关存在: ' + (btn ? 'OK' : 'FAIL'));
      if (!btn) return wait(0);
      btn.dispatchEvent(new MouseEvent('click', { bubbles: true }));
      out.push('   点击后 aria-pressed=' + btn.getAttribute('aria-pressed')
        + ' localStorage=' + localStorage.getItem('yys-sfx')
        + ' label="' + btn.getAttribute('aria-label') + '"'
        + (btn.getAttribute('aria-pressed') === 'true' ? '  OK' : '  FAIL'));

      // 6) 静音后悬停必须完全无声
      var s4 = snap();
      vs[2].dispatchEvent(new MouseEvent('mouseenter'));
      vs[0].dispatchEvent(new MouseEvent('mouseenter'));
      var s5 = snap();
      out.push('6 静音后悬停: ' + diff(s4, s5) + (s5.src === s4.src ? '  已静默 OK' : '  仍发声 FAIL'));

      return wait(140);
    }).then(function () {
      // 7) 恢复
      var btn = document.getElementById('sfxToggle');
      var s6 = snap();
      btn.dispatchEvent(new MouseEvent('click', { bubbles: true }));
      var s7 = snap();
      out.push('7 重新开启: aria-pressed=' + btn.getAttribute('aria-pressed') + ' 确认音 '
        + diff(s6, s7) + (s7.src > s6.src ? '  OK' : '  FAIL'));

      // 8) 参数体检
      out.push('8 参数体检: ' + (BAD.length ? 'FAIL  ' + BAD.join(' | ') : '指数斜坡端点全部非 0  OK'));
      out.push('  日志共 ' + LOG.length + ' 条');

      var box = document.createElement('div');
      box.style.cssText = 'position:fixed;z-index:99999;top:0;left:0;right:0;background:rgba(8,6,16,.93);'
        + 'color:#7dfba0;font:15px/1.8 monospace;padding:14px 16px;white-space:pre-wrap;pointer-events:none';
      box.textContent = out.join('\n');
      document.body.appendChild(box);

      // 同时挂到 window 上，供 CDP 直接读回纯文本（截图里的字不好核对）
      window.__probeResult = out.join('\n');
    });
  }, 600);
})();
</script>
"""

io.open(OUT, 'w', encoding='utf-8').write(src.replace('</body>', PROBE + '</body>'))
print('probe -> ' + OUT)
