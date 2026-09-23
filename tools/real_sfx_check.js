// 在真实 Web Audio（非 mock）下验证音效链路：派发真实手势 + 悬停 + 双击翻牌，
// 捕获 window.error 与 unhandledrejection，确认没有异常漏出来。
// 用法: node tools/cdp_probe.mjs index.html 1500 "$(cat tools/real_sfx_check.js)"
new Promise(function (resolve) {
  var log = [];
  window.addEventListener('error', function (e) { log.push('ERROR ' + e.message); });
  window.addEventListener('unhandledrejection', function (e) {
    log.push('REJECT ' + ((e.reason && e.reason.message) || e.reason));
  });

  var Native = window.AudioContext || window.webkitAudioContext;
  if (!Native) { resolve('本环境没有 AudioContext'); return; }

  var made = 0, states = [];
  function Wrapped() {
    made++;
    var ctx = new Native();
    states.push(ctx.state);
    return ctx;
  }
  Wrapped.prototype = Native.prototype;
  window.AudioContext = Wrapped;
  window.webkitAudioContext = Wrapped;

  var p = document.querySelector('.tarot-wrap');

  window.dispatchEvent(new Event('pointerdown', { bubbles: true }));

  setTimeout(function () {
    p.dispatchEvent(new MouseEvent('mouseenter'));
    p.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));

    setTimeout(function () {
      p.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));

      setTimeout(function () {
        log.push('AudioContext 实例数=' + made + ' 创建时 state=' + JSON.stringify(states));
        log.push('翻回后 flipped=' + p.classList.contains('flipped'));
        resolve(log.length ? log.join('  |  ') : '真实 Web Audio 下无异常 OK');
      }, 300);
    }, 200);
  }, 150);
})
