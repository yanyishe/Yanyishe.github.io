'use strict';
/**
 * 用 CDP 驱动无头 Edge，把「背景音乐有没有按预期响起来」变成可断言的数据。
 *
 * 无头环境没有声卡，声音本身听不到也测不到 —— 所以这里测的是**播放状态机**：
 * 清单有没有读进来、被自动播放策略拦下后手势能不能解锁、进度有没有真的在走、
 * 切歌换没换源。这些都是 DOM 上看得见的结果。
 *
 * 用法：
 *   node tools/probe_bgm.js <url> [输出png] [allow|deny] [特写选择器]
 *   deny（默认）—— 保持浏览器默认的自动播放策略，验证「被拦 → 等手势 → 解锁」
 *   allow —— 加 --autoplay-policy=no-user-gesture-required，验证「能播就直接播」
 *
 * 和 tools/cdp_probe.mjs 的分工：
 *   cdp_probe.mjs 是通用的一次性取值工具（跑一个表达式把结果打回来）；
 *   这个是专用的状态机验证器 —— 多步交互 + 断言 + 分状态截图。
 *   关键差别在于它用了 Input 域发**真实**鼠标事件：element.click() 产生的是
 *   合成事件（isTrusted=false），拿不到「用户激活」，解锁不了音频，一测就假通过。
 */

const { spawn } = require('child_process');
const fs = require('fs');
const http = require('http');
const os = require('os');
const path = require('path');

const EDGE = 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe';
const PORT = 9411;

const TARGET_URL = process.argv[2];
const OUT_PNG = process.argv[3] || '';
const ALLOW_AUTOPLAY = process.argv[4] === 'allow';
// 给了选择器就额外拍一张该元素的放大特写（控制条只有 40px 高，整页图上看不清）
const CLIP_SELECTOR = process.argv[5] || '';
// 置 1 表示这一轮期望「清单为空」，断言方向相反：控制条不该出现
const EXPECT_EMPTY = process.env.BGM_EXPECT_EMPTY === '1';
// button-first —— 复现「用户的第一个动作就是点播放键」这条路径。
// 默认流程是先点页面空白处解锁，那恰好绕过了这里要查的竞态，必须先单独跑一轮。
const SCENARIO = process.env.BGM_SCENARIO || '';

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

function getJSON(url) {
  return new Promise((resolve, reject) => {
    const req = http.get(url, (res) => {
      let b = '';
      res.on('data', (c) => (b += c));
      res.on('end', () => {
        try { resolve(JSON.parse(b)); } catch (e) { reject(e); }
      });
    });
    req.on('error', reject);
    req.setTimeout(3000, () => req.destroy(new Error('timeout')));
  });
}

/* 页面上的可观测状态。音乐引擎把状态都挂在 DOM 上（is-ready / data-playing /
   进度条的 transform），所以这里不需要任何调试后门就能读到。 */
const READ_STATE = `(function(){
  var bar = document.getElementById('bgmBar');
  if (!bar) return { missing: true };
  var play  = document.getElementById('bgmPlay');
  var fill  = document.getElementById('bgmFill');
  var title = document.getElementById('bgmTitle');
  var m = /scaleX\\(([-\\d.]+)\\)/.exec(fill ? fill.style.transform : '');
  // 只列 <audio> 自己发出的请求。上面第 0 节用 fetch 发的 HEAD 也会落进
  // resource timing（initiatorType 为 fetch），混在一起会看不出到底谁在下载音频。
  var res = performance.getEntriesByType('resource')
    .filter(function(e){ return e.name.indexOf('/music/') !== -1 && e.initiatorType !== 'fetch'; })
    .map(function(e){ return e.name.split('/').pop() + ' [' + (e.responseStatus || '?') + ' ' + Math.round(e.transferSize/1024) + 'KB]'; });
  // 播放器的真实状况。光看 data-playing 是查不出问题的：它只说明「状态机想播」，
  // 文件 404 时它照样是 "true"，曲名和进度条也照样画得出来 —— 界面全绿，一声不吭。
  // 元素又不在 DOM 里（页面用的是 new Audio()），querySelector('audio') 取不到，
  // 所以要从导航前埋下的构造器钩子 window.__audioTap 里捞。
  var tap = window.__audioTap || [];
  var a = tap.length ? tap[tap.length - 1] : null;
  var el = null;
  if (a) {
    el = {
      src: decodeURIComponent((a.currentSrc || a.src || '').split('/').pop() || ''),
      ready: a.readyState,        // 0 无 / 1 元数据 / 2 当前帧 / 3 可播 / 4 足够播
      dur: Math.round(a.duration || 0),
      time: +(a.currentTime || 0).toFixed(2),
      err: a.error ? a.error.code : 0,   // 1 中止 / 2 网络 / 3 解码 / 4 不支持
      paused: a.paused,
      vol: +(a.volume || 0).toFixed(3)
    };
  }
  var vf = document.getElementById('bgmVolFill');
  var vm = /scaleX\\(([-\\d.]+)\\)/.exec(vf ? vf.style.transform : '');
  var muteBtn = document.getElementById('bgmMute');
  // 封面：有专属图时 JS 会给它加 .is-art 并写行内 backgroundImage，
  // 否则退回 CSS 里那张面具牌背（行内是空的）
  var cov = document.getElementById('bgmCover');
  var mini = document.getElementById('bgmMini');
  // 收起态的封面/旋转都在中央那枚标贴上，不在按钮本身上
  var miniLbl = document.getElementById('bgmMiniLabel');
  var mr = mini ? mini.getBoundingClientRect() : null;
  return {
    missing: false,
    ready: bar.classList.contains('is-ready'),
    // 收起态：显隐完全由 <body> 上的 .bgm-min 决定，所以几个量一起读
    collapsed: document.body.classList.contains('bgm-min'),
    barVisible: getComputedStyle(bar).display !== 'none',
    miniVisible: mini ? getComputedStyle(mini).display !== 'none' : null,
    miniArt: miniLbl ? miniLbl.classList.contains('is-art') : null,
    miniUrl: miniLbl ? decodeURIComponent((miniLbl.style.backgroundImage || '')).slice(0, 90) : null,
    miniPlaying: mini ? mini.getAttribute('data-playing') : null,
    miniSpin: miniLbl ? getComputedStyle(miniLbl).animationPlayState : null,
    miniAnim: miniLbl ? getComputedStyle(miniLbl).animationName : null,
    miniSize: mr ? Math.round(mr.width) + 'x' + Math.round(mr.height) : null,
    miniRadius: mini ? getComputedStyle(mini).borderRadius : null,
    miniLabelSize: (function () {
      if (!miniLbl) return null;
      var r = miniLbl.getBoundingClientRect();
      return Math.round(r.width) + 'x' + Math.round(r.height);
    })(),
    miniLabelRadius: miniLbl ? getComputedStyle(miniLbl).borderRadius : null,
    miniLabelArt: miniLbl ? getComputedStyle(miniLbl).backgroundSize : null,
    miniLabelImg: miniLbl ? getComputedStyle(miniLbl).backgroundImage.slice(0, 40) : null,
    miniLabel: mini ? mini.getAttribute('aria-label') : null,
    title: title ? title.textContent : null,
    count: (function () { var c = document.getElementById('bgmCount'); return c ? c.textContent : null; })(),
    time: (function () { var t = document.getElementById('bgmTime'); return t ? t.textContent : null; })(),
    playing: play ? play.getAttribute('data-playing') : null,
    muted: muteBtn ? muteBtn.getAttribute('data-muted') : null,
    progress: m ? parseFloat(m[1]) : 0,
    volFill: vm ? parseFloat(vm[1]) : 0,
    coverArt: cov ? cov.classList.contains('is-art') : null,
    coverUrl: cov ? decodeURIComponent((cov.style.backgroundImage || '')).slice(0, 90) : null,
    width: Math.round(bar.getBoundingClientRect().width),
    height: Math.round(bar.getBoundingClientRect().height),
    el: el,
    audio: res
  };
})()`;

(async () => {
  const profile = path.join(os.tmpdir(), 'yys-cdp-' + Date.now());
  const args = [
    '--headless=new', '--disable-gpu', '--no-sandbox', '--no-first-run',
    '--hide-scrollbars', '--mute-audio',
    '--remote-debugging-port=' + PORT,
    '--remote-allow-origins=*',
    '--user-data-dir=' + profile,
    '--window-size=1440,900',
  ];
  if (ALLOW_AUTOPLAY) args.push('--autoplay-policy=no-user-gesture-required');
  // 先开空白页，再用 CDP 导航 —— 只有在导航之前注册的钩子才能拦到页面的
  // new Audio()（直接拿 URL 当参数启动的话，页面脚本在我们连上之前就跑完了）
  args.push('about:blank');

  const edge = spawn(EDGE, args, { stdio: 'ignore' });

  const cleanup = () => {
    try { spawn('taskkill', ['/F', '/T', '/PID', String(edge.pid)], { stdio: 'ignore' }); } catch (e) {}
    try { fs.rmSync(profile, { recursive: true, force: true }); } catch (e) {}
  };
  process.on('exit', cleanup);

  // ---- 等 CDP 端点起来 ----
  let wsUrl = null;
  for (let i = 0; i < 48 && !wsUrl; i++) {
    try {
      const list = await getJSON(`http://127.0.0.1:${PORT}/json`);
      const page = list.find((t) => t.type === 'page' && t.webSocketDebuggerUrl);
      if (page) wsUrl = page.webSocketDebuggerUrl;
    } catch (e) { /* 还没起来 */ }
    if (!wsUrl) await sleep(250);
  }
  if (!wsUrl) throw new Error('CDP 端点没起来');

  const ws = new WebSocket(wsUrl);
  await new Promise((res, rej) => {
    ws.addEventListener('open', res, { once: true });
    ws.addEventListener('error', () => rej(new Error('WebSocket 连接失败')), { once: true });
  });

  let msgId = 0;
  const pending = new Map();
  ws.addEventListener('message', (ev) => {
    let m;
    try { m = JSON.parse(ev.data); } catch (e) { return; }
    if (m.id && pending.has(m.id)) {
      const { resolve, reject } = pending.get(m.id);
      pending.delete(m.id);
      if (m.error) reject(new Error(m.error.message));
      else resolve(m.result);
    }
  });
  const send = (method, params) => new Promise((resolve, reject) => {
    const id = ++msgId;
    pending.set(id, { resolve, reject });
    ws.send(JSON.stringify({ id, method, params: params || {} }));
  });

  await send('Runtime.enable');
  await send('Page.enable');

  // 把 Audio 构造器包一层，把实例捞进 window.__audioTap。
  // 返回的是真正的 HTMLAudioElement（构造器返回对象会顶替 this），
  // 且 Tap.prototype 指向原原型，页面侧的 instanceof / 特性检测都不受影响。
  await send('Page.addScriptToEvaluateOnNewDocument', {
    source: `(function(){
      if (typeof window.Audio !== 'function') return;
      var Orig = window.Audio;
      window.__audioTap = [];
      function Tap(src) {
        var a = new Orig(src);
        try { window.__audioTap.push(a); } catch (e) {}
        return a;
      }
      Tap.prototype = Orig.prototype;
      window.Audio = Tap;
    })();`,
  });
  await send('Page.navigate', { url: TARGET_URL });

  async function evaluate(expression) {
    const r = await send('Runtime.evaluate', {
      expression, returnByValue: true, awaitPromise: true,
    });
    if (r.exceptionDetails) {
      throw new Error(r.exceptionDetails.exception
        ? r.exceptionDetails.exception.description
        : r.exceptionDetails.text);
    }
    return r.result.value;
  }

  // 真实鼠标点击 —— 必须走 Input 域：element.click() 产生的是合成事件，
  // isTrusted 为 false，拿不到「用户激活」，解锁不了音频。
  async function clickAt(x, y) {
    const base = { x: Math.round(x), y: Math.round(y) };
    await send('Input.dispatchMouseEvent', Object.assign({ type: 'mouseMoved', button: 'none' }, base));
    await sleep(60);
    await send('Input.dispatchMouseEvent', Object.assign({ type: 'mousePressed', button: 'left', clickCount: 1 }, base));
    await sleep(40);
    await send('Input.dispatchMouseEvent', Object.assign({ type: 'mouseReleased', button: 'left', clickCount: 1 }, base));
  }

  async function centerOf(selector) {
    return evaluate(`(function(){
      var el = document.querySelector(${JSON.stringify(selector)});
      if (!el) return null;
      var r = el.getBoundingClientRect();
      return { x: r.left + r.width / 2, y: r.top + r.height / 2 };
    })()`);
  }

  // 控制条只有 40px 高，在整页图上就是个点 —— 每到一个关键状态就单独拍一张特写。
  // sel 可省略，默认拍 CLIP_SELECTOR 指定的那个元素。
  async function shootClip(tag, sel) {
    const target = sel || CLIP_SELECTOR;
    if (!OUT_PNG || !target) return;
    const box = await evaluate(`(function(){
      var el = document.querySelector(${JSON.stringify(target)});
      if (!el) return null;
      var b = el.getBoundingClientRect();
      return { x: b.left, y: b.top, width: b.width, height: b.height };
    })()`);
    if (!box || !box.width) return;
    const pad = 16;
    const clip = {
      x: Math.max(0, box.x - pad),
      y: Math.max(0, box.y - pad),
      width: box.width + pad * 2,
      height: box.height + pad * 2,
      scale: 3,
    };
    const shot = await send('Page.captureScreenshot', { format: 'png', clip });
    const p = OUT_PNG.replace(/\.png$/i, '') + '-' + tag + '.png';
    fs.mkdirSync(path.dirname(p), { recursive: true });
    fs.writeFileSync(p, Buffer.from(shot.data, 'base64'));
    console.log('  特写: ' + path.basename(p));
  }

  const pass = [];
  const fail = [];
  const check = (label, ok, detail) => {
    (ok ? pass : fail).push(label + (detail ? '  → ' + detail : ''));
    console.log(`  ${ok ? '✅' : '❌'} ${label}${detail ? '  → ' + detail : ''}`);
  };

  // ---- 等页面就绪 ----
  for (let i = 0; i < 60; i++) {
    const ok = await evaluate('document.readyState === "complete" && !!document.getElementById("bgmBar")')
      .catch(() => false);
    if (ok) break;
    await sleep(250);
  }
  await sleep(1200);   // 给清单解析 + 首次 play() 尝试留出时间

  // ---- 专治「歌丢进去了但页面没反应」----
  // 最常见的原因是忘了重跑 tools/gen_music_manifest.py：清单里还写着旧文件名
  // （或已经被删掉的占位音），于是音频全部 404。此时控制条在、曲名在、
  // data-playing 也是 true，界面一片正常，光看截图根本查不出来。
  if (!EXPECT_EMPTY) {
    console.log('\n===== 0. 清单指向的文件是否真在服务器上 =====');
    // file:// 下 fetch 用不了（本地文件没有 HTTP 状态码），但音频元素本身能读相对路径 ——
    // 所以双击打开时这条路照样通，只是没法在这里做存在性断言。
    const isFile = await evaluate('location.protocol === "file:"');
    if (isFile) {
      console.log('  （file:// 打开，fetch 用不了，跳过存在性逐一检查；改由第 3 节的解码断言兜底）');
    } else {
      const manifest = await evaluate(`(async function(){
        var t = window.YYS_TRACKS || [];
        var out = [];
        for (var i = 0; i < t.length; i++) {
          var st;
          try {
            var r = await fetch(encodeURI('./music/' + t[i].file), { method: 'HEAD', cache: 'no-store' });
            st = r.status;
          } catch (e) { st = 'ERR ' + (e && e.name); }
          out.push({ file: t[i].file, status: st });
        }
        return { tracks: out, defined: typeof window.YYS_TRACKS !== 'undefined' };
      })()`);
      const missingFiles = manifest.tracks.filter((m) => m.status !== 200);
      check('manifest.js 加载成功且清单非空', manifest.defined && manifest.tracks.length > 0,
            manifest.tracks.length + ' 首');
      check('清单里的文件在服务器上全部存在', missingFiles.length === 0,
            missingFiles.length
              ? '取不到 ' + missingFiles.map((m) => m.file + ' → ' + m.status).join(' / ')
              : '全部 200');
    }
  }

  console.log('\n===== 1. 清单与初始状态 =====');
  const s0 = await evaluate(READ_STATE);
  console.log('  状态:', JSON.stringify(s0));

  // ---- 空清单：这里就该到此为止，控制条不该出现，也不该白花一个音频请求 ----
  if (EXPECT_EMPTY) {
    check('空清单时不出现控制条（不留一个点不动的空壳）', s0.ready === false, 'is-ready=' + s0.ready);
    const audioReqs = s0.audio.filter((a) => !a.startsWith('manifest'));
    check('也没有白发出音频请求', audioReqs.length === 0, JSON.stringify(audioReqs));
    console.log(`\n===== 汇总: ${pass.length} 通过 / ${fail.length} 失败 =====`);
    if (fail.length) fail.forEach((f) => console.log('  · ' + f));
    ws.close();
    cleanup();
    process.exit(fail.length ? 1 : 0);
  }

  check('控制条出现（清单已读到曲目）', s0.ready === true);
  check('曲名解析正确（前导编号已剥掉）', !!s0.title && !/^\d/.test(s0.title), s0.title);

  console.log('\n===== 2. 自动播放策略 =====');
  if (ALLOW_AUTOPLAY) {
    check('策略放行时直接就播（无需交互）', s0.playing === 'true', 'data-playing=' + s0.playing);
  } else {
    check('策略拦下时不擅自出声（等手势）', s0.playing === 'false', 'data-playing=' + s0.playing);
  }
  await shootClip('1-initial');

  // ---- 场景：用户的第一个动作就是点播放键 ----
  // 默认流程这一步之前会先点一下页面空白处，那一下会把「等手势」的监听解掉，
  // 于是按钮的竞态被完全掩盖。这里必须什么都不先点，直接上按钮。
  if (SCENARIO === 'button-first') {
    console.log('\n===== S. 第一个交互就是点播放键（用户实际路径）=====');
    const pb = await centerOf('#bgmPlay');

    await clickAt(pb.x, pb.y);
    await sleep(1800);
    const b1 = await evaluate(READ_STATE);
    console.log('  第一次点击后:', JSON.stringify({
      playing: b1.playing, paused: b1.el && b1.el.paused, t: b1.el && b1.el.time,
    }));
    check('首个交互直接点播放键 → 就该开始播',
          b1.playing === 'true' && !!b1.el && b1.el.paused === false,
          'data-playing=' + b1.playing + '  el.paused=' + (b1.el && b1.el.paused));
    const tb = b1.el ? b1.el.time : 0;
    await sleep(1400);
    const b2 = await evaluate(READ_STATE);
    check('起播后播放头在走', (b2.el ? b2.el.time : 0) > tb,
          tb + 's → ' + (b2.el ? b2.el.time : 0) + 's');
    await shootClip('s1-playing');

    await clickAt(pb.x, pb.y);
    await sleep(1000);
    const b3 = await evaluate(READ_STATE);
    console.log('  第二次点击后:', JSON.stringify({
      playing: b3.playing, paused: b3.el && b3.el.paused, t: b3.el && b3.el.time,
    }));
    check('再点一次 → 暂停', b3.playing === 'false' && !!b3.el && b3.el.paused === true,
          'data-playing=' + b3.playing + '  el.paused=' + (b3.el && b3.el.paused));
    const t3 = b3.el ? b3.el.time : 0;
    await sleep(1300);
    const b4 = await evaluate(READ_STATE);
    check('暂停后播放头真的停住', (b4.el ? b4.el.time : 0) === t3,
          t3 + 's → ' + (b4.el ? b4.el.time : 0) + 's');
    await shootClip('s2-paused');

    await clickAt(pb.x, pb.y);
    await sleep(1500);
    const b5 = await evaluate(READ_STATE);
    check('第三次点击 → 恢复播放', b5.playing === 'true' && !!b5.el && b5.el.paused === false,
          'data-playing=' + b5.playing);
    const t5 = b5.el ? b5.el.time : 0;
    await sleep(1300);
    const b6 = await evaluate(READ_STATE);
    check('恢复后播放头继续走', (b6.el ? b6.el.time : 0) > t5,
          t5 + 's → ' + (b6.el ? b6.el.time : 0) + 's');
    await shootClip('s3-resumed');

    await finish();
    ws.close();
    cleanup();
    process.exit(fail.length ? 1 : 0);
  }

  if (SCENARIO === 'cover-fallback') {
    console.log('\n===== S. 没配封面时退回面具牌背 =====');
    // 用一份把 cover 全改成 null 的清单跑，验证兜底分支。
    // 现在 8 首都有封面了，正常清单测不到这条路径。
    const c0 = await evaluate(READ_STATE);
    console.log('  状态:', JSON.stringify({ title: c0.title, art: c0.coverArt, bg: c0.coverUrl }));
    check('清单里 cover 为 null 时不加 is-art（回落 CSS 那张面具）',
          c0.coverArt === false, 'is-art=' + c0.coverArt);
    check('行内没有残留的 backgroundImage',
          !c0.coverUrl, JSON.stringify(c0.coverUrl));
    check('兜底时控制条照常出现', c0.ready === true, 'is-ready=' + c0.ready);
    await shootClip('s-fallback');
    await finish();
    ws.close();
    cleanup();
    process.exit(fail.length ? 1 : 0);
  }

  console.log('\n===== 3. 手势解锁 =====');
  // 点横幅区域：那里是 <img>，点什么都不会翻牌，但 pointerdown 照样经过 window
  // 的捕获阶段 —— 正好验证「点页面任何地方都能解锁」，而不只是点播放按钮。
  await clickAt(720, 100);
  await sleep(1600);   // 等 1.4s 淡入走完
  const s1 = await evaluate(READ_STATE);
  console.log('  状态:', JSON.stringify(s1));
  check('页面任意位置一次点击即起播', s1.playing === 'true', 'data-playing=' + s1.playing);
  // 「想播」不等于「播得出来」。文件 404 / 编码不支持时，data-playing 照样是 true。
  check('音频文件真的解码成功（不是 404 也不是解码失败）',
        !!(s1.el && s1.el.err === 0 && s1.el.ready >= 2 && s1.el.dur > 0),
        s1.el
          ? ('「' + s1.el.src + '」readyState=' + s1.el.ready +
             '  时长=' + s1.el.dur + 's  error=' + s1.el.err + (s1.el.err ? '（1中止/2网络/3解码/4不支持）' : ''))
          : '没抓到 audio 实例（构造器钩子没生效？）');
  await shootClip('2-playing');

  console.log('\n===== 4. 播放推进 =====');
  await sleep(2600);
  const s2 = await evaluate(READ_STATE);
  // 阈值不能写死。曲目长度从几秒的占位音到几分钟的正式曲目差两个数量级，
  // 固定阈值会把「真的在播、只是走得慢」误判成失败。改为断言两次读数之间的增量。
  const t1 = s1.el ? s1.el.time : 0;
  const t2 = s2.el ? s2.el.time : 0;
  console.log('  进度条:', s1.progress, '->', s2.progress, '   播放头:', t1 + 's ->', t2 + 's');
  check('播放头真的在走（不是空转的进度条）', t2 > t1,
        t1.toFixed(2) + 's → ' + t2.toFixed(2) + 's');
  check('进度条在推进（音频真的在走）', s2.progress > s1.progress,
        'scaleX=' + s1.progress.toFixed(5) + ' → ' + s2.progress.toFixed(5));

  console.log('\n===== 5. 切换曲目 =====');
  const before = s2.title;
  const btn = await centerOf('#bgmNext');
  await clickAt(btn.x, btn.y);
  await sleep(1800);
  const s3 = await evaluate(READ_STATE);
  console.log('  状态:', JSON.stringify(s3));
  check('点「下一首」换到了另一首', s3.title !== before, `${before} → ${s3.title}`);
  check('切歌后继续播放', s3.playing === 'true');
  check('切换后进度重置', s3.progress < 0.5, 'scaleX=' + s3.progress.toFixed(4));
  // 曲目文件名里带空格、撇号、全角字符、行尾空格 —— 这些都要能正确编码并取到
  check('切歌后音频源真的换了，且新文件也加载成功',
        !!(s3.el && s2.el && s3.el.src !== s2.el.src && s3.el.err === 0 && s3.el.dur > 0),
        s3.el ? ('「' + s3.el.src + '」时长=' + s3.el.dur + 's error=' + s3.el.err) : '没抓到 audio 实例');
  check('切歌时控制条宽度不跳（曲名长短影响不到它）',
    s2.width === s3.width, s2.width + 'px → ' + s3.width + 'px');
  await shootClip('3-switched');

  console.log('\n===== 6. 音频资源 =====');
  console.log('  已加载:', JSON.stringify(s3.audio));
  // file:// 下浏览器不产出 resource timing（没有 HTTP 请求这回事），列表必然为空；
  // 那里改由第 3、5 节直接读 <audio> 的解码状态来判定，不要在这里误报失败。
  const onFile = await evaluate('location.protocol === "file:"');
  check('音频文件真的被请求了' + (onFile ? '（file:// 下不适用，改用解码状态判定）' : ''),
        onFile ? true : s3.audio.length > 0, s3.audio.join(', ') || '（file:// 无 resource timing）');

  console.log('\n===== 7. 再切回上一首 =====');
  const prevBtn = await centerOf('#bgmPrev');
  await clickAt(prevBtn.x, prevBtn.y);
  await sleep(1500);
  const s4 = await evaluate(READ_STATE);
  check('点「上一首」回到原来那首', s4.title === before, `${s3.title} → ${s4.title}`);

  console.log('\n===== 8. 悬停：整条亮起来（对照静置态） =====');
  const barCenter = await centerOf('#bgmBar');
  await send('Input.dispatchMouseEvent', {
    type: 'mouseMoved',
    x: Math.round(barCenter.x), y: Math.round(barCenter.y),
    button: 'none',
  });
  await sleep(700);
  const hoverColor = await evaluate(
    'getComputedStyle(document.getElementById("bgmBar")).color');
  console.log('  悬停时前景色:', hoverColor);
  check('悬停后前景色变亮（静置是压暗的同一系色）',
    hoverColor === 'rgb(246, 235, 210)', hoverColor);
  await shootClip('5-hover');

  console.log('\n===== 8b. 音量条与静音 =====');
  // 点音量条 25% 处。用真实鼠标事件（Input 域），不是 element.click()。
  const volBox = await evaluate(`(function(){
    var el = document.getElementById('bgmVol');
    if (!el) return null;
    var r = el.getBoundingClientRect();
    return { x: r.left + r.width * 0.25, y: r.top + r.height / 2 };
  })()`);
  await clickAt(volBox.x, volBox.y);
  await sleep(300);
  const v1 = await evaluate(READ_STATE);
  console.log('  点音量条 25% →', JSON.stringify({ vol: v1.el && v1.el.vol, fill: v1.volFill }));
  check('点音量条能改音量（约 0.25）', !!v1.el && Math.abs(v1.el.vol - 0.25) < 0.06,
        'el.volume=' + (v1.el && v1.el.vol));
  check('音量条填充跟着走', Math.abs(v1.volFill - 0.25) < 0.06, 'scaleX=' + v1.volFill);

  // 静音：音量淡到 0，但暂停态不能被改
  const muteBtn = await centerOf('#bgmMute');
  await clickAt(muteBtn.x, muteBtn.y);
  await sleep(700);
  const v2 = await evaluate(READ_STATE);
  console.log('  静音后 →', JSON.stringify({ muted: v2.muted, vol: v2.el && v2.el.vol, playing: v2.playing }));
  check('点喇叭进入静音（音量淡到 0）', v2.muted === 'true' && !!v2.el && v2.el.vol < 0.02,
        'data-muted=' + v2.muted + '  el.volume=' + (v2.el && v2.el.vol));
  check('静音只关声音，不暂停播放', v2.playing === 'true', 'data-playing=' + v2.playing);

  await clickAt(muteBtn.x, muteBtn.y);
  await sleep(700);
  const v3 = await evaluate(READ_STATE);
  console.log('  取消静音 →', JSON.stringify({ muted: v3.muted, vol: v3.el && v3.el.vol }));
  check('取消静音后音量回到原值（记住的是基准值，不是 0）',
        v3.muted === 'false' && !!v3.el && Math.abs(v3.el.vol - 0.25) < 0.06,
        'el.volume=' + (v3.el && v3.el.vol));
  await shootClip('6-volume');

  console.log('\n===== 8c. 进度条拖动跳转 =====');
  // 先把几何量和「页面自己算出来的比例」都记下来：真出问题时，
  // 光看 currentTime 分不清是坐标点错了、还是比例算错了。
  const seekDiag = await evaluate(`(function(){
    var el = document.getElementById('bgmSeek');
    if (!el) return null;
    var r = el.getBoundingClientRect();
    window.__seekDiag = null;
    el.addEventListener('pointerdown', function(ev){
      window.__seekDiag = {
        clientX: Math.round(ev.clientX),
        left: Math.round(r.left),
        width: Math.round(r.width),
        ratio: +((ev.clientX - r.left) / r.width).toFixed(4)
      };
    }, true);
    return { left: Math.round(r.left), width: Math.round(r.width),
             height: Math.round(r.height), x60: Math.round(r.left + r.width * 0.6) };
  })()`);
  console.log('  进度条几何:', JSON.stringify(seekDiag));
  await clickAt(seekDiag.x60, (await centerOf('#bgmSeek')).y);
  await sleep(600);
  const diag = await evaluate('window.__seekDiag');
  console.log('  元素自算的比例:', JSON.stringify(diag));
  const s1b = await evaluate(READ_STATE);
  const ratio = s1b.el && s1b.el.dur ? s1b.el.time / s1b.el.dur : 0;
  console.log('  点进度条 60% →', JSON.stringify({ time: s1b.el && s1b.el.time, dur: s1b.el && s1b.el.dur, ratio: +ratio.toFixed(3) }));
  check('点进度条能跳到该位置（±4%）', Math.abs(ratio - 0.6) < 0.04, '实际落在 ' + (ratio * 100).toFixed(1) + '%');
  check('跳转后进度条同步', Math.abs(s1b.progress - ratio) < 0.05,
        'scaleX=' + s1b.progress + '  vs 播放头 ' + ratio.toFixed(4));
  check('时间读数跟着跳', !!s1b.time && /^\d+:\d\d \/ \d+:\d\d$/.test(s1b.time), s1b.time);
  await shootClip('7-seek');

  console.log('\n===== 8d. 键盘也能调进度 =====');
  // 进度条是 role=slider + tabindex=0，键盘必须可用，不然用键盘的人拖不动它。
  // 走 CDP 的 Input 域发真实按键，同样不能用合成事件。
  // 先挂一个全局按键记录器：万一按键根本没送到页面，这条能立刻把原因分开 ——
  // 是「事件没到」还是「到了但处理器没认」。
  await evaluate(`(function(){
    window.__keys = [];
    window.addEventListener('keydown', function(e){ window.__keys.push(e.key); }, true);
  })()`);

  async function pressKey(key, code, vk) {
    const base = { key, code, windowsVirtualKeyCode: vk, nativeVirtualKeyCode: vk };
    await send('Input.dispatchKeyEvent', Object.assign({ type: 'rawKeyDown' }, base));
    await send('Input.dispatchKeyEvent', Object.assign({ type: 'keyUp' }, base));
  }

  await evaluate('document.getElementById("bgmSeek").focus()');
  await sleep(200);
  const focused = await evaluate('document.activeElement && document.activeElement.id');
  check('进度条能拿到键盘焦点', focused === 'bgmSeek', 'focused=' + focused);

  const kBefore = await evaluate(READ_STATE);
  console.log('  起始:', JSON.stringify({ title: kBefore.title, dur: kBefore.el && kBefore.el.dur, time: kBefore.el && kBefore.el.time }));

  // 先回到开头，从一个确定的位置开始
  await pressKey('Home', 'Home', 36);
  await sleep(400);
  const kHome = await evaluate(READ_STATE);
  check('按 Home 回到开头', kHome.el && kHome.el.time < 0.6, 'time=' + (kHome.el && kHome.el.time));

  // 两次 → ：每次 2%，合计约 4%
  await pressKey('ArrowRight', 'ArrowRight', 39);
  await pressKey('ArrowRight', 'ArrowRight', 39);
  await sleep(400);
  const kR = await evaluate(READ_STATE);
  const rR = kR.el && kR.el.dur ? kR.el.time / kR.el.dur : 0;
  console.log('  按两次 → →', JSON.stringify({ time: kR.el && kR.el.time, ratio: +rR.toFixed(4) }));
  check('按 → 前进（每次 2%，两次约 4%）', Math.abs(rR - 0.04) < 0.015,
        '落在 ' + (rR * 100).toFixed(2) + '%');

  // 一次 ← ：退回 2%
  await pressKey('ArrowLeft', 'ArrowLeft', 37);
  await sleep(400);
  const kL = await evaluate(READ_STATE);
  const rL = kL.el && kL.el.dur ? kL.el.time / kL.el.dur : 0;
  console.log('  按一次 ← →', JSON.stringify({ time: kL.el && kL.el.time, ratio: +rL.toFixed(4) }));
  check('按 ← 后退 2%', Math.abs(rR - rL - 0.02) < 0.012,
        (rR * 100).toFixed(2) + '% → ' + (rL * 100).toFixed(2) + '%');

  const keysSeen = await evaluate('window.__keys');
  check('按键确实送到了页面', Array.isArray(keysSeen) && keysSeen.length >= 4,
        JSON.stringify(keysSeen));
  await shootClip('8-keyboard');

  console.log('\n===== 8e. 每首歌自己的封面 =====');
  const cov1 = await evaluate(READ_STATE);
  console.log('  第 1 首:', JSON.stringify({ count: cov1.count, art: cov1.coverArt, url: cov1.coverUrl }));
  check('当前曲目显示自己的封面',
        cov1.coverArt === true && /01-/.test(cov1.coverUrl || ''),
        'is-art=' + cov1.coverArt + '  ' + cov1.coverUrl);
  const url1 = cov1.coverUrl;

  // 切下一首：封面要跟着换，而且不能还是上一首那张
  const nb1 = await centerOf('#bgmNext');
  await clickAt(nb1.x, nb1.y);
  await sleep(1200);
  const cov2 = await evaluate(READ_STATE);
  console.log('  第 2 首:', JSON.stringify({ count: cov2.count, art: cov2.coverArt, url: cov2.coverUrl }));
  check('切歌后封面跟着换成新的（不是上一首那张）',
        cov2.coverArt === true && cov2.coverUrl !== url1 && /02-/.test(cov2.coverUrl || ''),
        cov2.coverUrl);
  check('曲序跟着走', cov2.count === '02 / 08', cov2.count);
  check('切歌后仍在播放', cov2.playing === 'true', 'data-playing=' + cov2.playing);
  await shootClip('9-cover');

  console.log('\n===== 9. 窄屏：封面让位、控件不越界 =====');
  await send('Emulation.setDeviceMetricsOverride', {
    width: 390, height: 844, deviceScaleFactor: 2, mobile: true,
  });
  await sleep(800);
  const narrow = await evaluate(`(function(){
    var t = document.getElementById('bgmTitle');
    var c = document.querySelector('.bgm-cover');
    var n = document.getElementById('bgmCount');
    var bar = document.getElementById('bgmBar');
    if (!t || !bar) return null;
    var r = bar.getBoundingClientRect();
    return {
      // 窄屏让位的是封面和曲序，曲名留下来（靠 ellipsis 自适应）——
      // 只留三个光秃秃的按钮才真的不知道在放哪首
      coverHidden: !c || getComputedStyle(c).display === 'none',
      countHidden: !n || getComputedStyle(n).display === 'none',
      titleVisible: getComputedStyle(t).display !== 'none',
      titleClipped: t.scrollWidth > t.clientWidth + 1,
      barWidth: Math.round(r.width),
      barHeight: Math.round(r.height),
      left: Math.round(r.left),
      right: Math.round(window.innerWidth - r.right),
      bottom: Math.round(window.innerHeight - r.bottom)
    };
  })()`);
  console.log('  窄屏状态:', JSON.stringify(narrow));
  check('窄屏下封面让位', !!narrow && narrow.coverHidden === true);
  check('窄屏下曲名仍在（超长走省略号）', !!narrow && narrow.titleVisible === true,
        narrow ? '标题是否被截断=' + narrow.titleClipped : '');
  check('窄屏下播放器不越出视口', !!narrow && narrow.left >= 0 && narrow.right >= 0 && narrow.bottom >= 0,
    narrow ? '左 ' + narrow.left + 'px / 右 ' + narrow.right + 'px / 下 ' + narrow.bottom +
             'px，' + narrow.barWidth + '×' + narrow.barHeight : '');
  await shootClip('4-narrow');
  await send('Emulation.clearDeviceMetricsOverride');
  await sleep(500);

  console.log('\n===== 10. 收起 / 展开 =====');
  const k0 = await evaluate(READ_STATE);
  check('进站默认是展开状态（没被上次的收起状态记住）',
        k0.collapsed === false && k0.barVisible === true && k0.miniVisible === false,
        'collapsed=' + k0.collapsed + ' bar=' + k0.barVisible + ' mini=' + k0.miniVisible);
  const urlBefore = k0.coverUrl;

  const minBtn = await centerOf('#bgmMin');
  await clickAt(minBtn.x, minBtn.y);
  await sleep(700);
  const k1 = await evaluate(READ_STATE);
  console.log('  收起后:', JSON.stringify({
    collapsed: k1.collapsed, bar: k1.barVisible, mini: k1.miniVisible,
    playing: k1.playing, miniArt: k1.miniArt, miniUrl: k1.miniUrl }));
  check('点收起按钮后：面板隐、唱片现',
        k1.collapsed === true && k1.barVisible === false && k1.miniVisible === true);
  check('收起不影响播放', k1.playing === 'true', 'data-playing=' + k1.playing);
  check('唱片中央带着当前曲目的封面（和面板上那张是同一张）',
        k1.miniArt === true && !!k1.miniUrl && !!urlBefore &&
        k1.miniUrl.slice(-20) === urlBefore.slice(-20),
        k1.miniUrl);
  check('唱片有可读的 aria 标签', /展开播放器/.test(k1.miniLabel || ''), k1.miniLabel);

  // 唱片这个形状：按钮是圆的、标贴也是圆的，而且都在面板原来的角上
  check('收起态是正圆（按钮与中央标贴都是圆形）',
        k1.miniSize === '54x54' && k1.miniRadius === '50%' &&
        !!k1.miniLabelSize && k1.miniLabelRadius === '50%',
        '按钮 ' + k1.miniSize + ' r=' + k1.miniRadius +
        '  标贴 ' + k1.miniLabelSize + ' r=' + k1.miniLabelRadius);
  check('中央标贴铺的是当前封面（不是兜底的面具）',
        k1.miniLabelArt === 'cover', 'background-size=' + k1.miniLabelArt);

  // 转不转要跟着播放态走 —— 这是"收起后也能看出在不在放"的全部依据
  check('在播时唱片在转', k1.miniSpin === 'running', 'animation-play-state=' + k1.miniSpin);

  const pb = await centerOf('#bgmPlay');
  if (k1.collapsed) {
    // 这里用 element.click()（合成事件）是**刻意**的：收起时面板是 display:none，
    // 没法派发真实鼠标事件。而且此刻只是把已经在播的音频叫停，
    // 不需要「用户激活」—— 合成事件会假通过的坑只在"解锁自动播放"那一步。
    await evaluate('(function(){document.querySelector("#bgmPlay").click();return 1})()');
  }
  await sleep(1200);
  const kPaused = await evaluate(READ_STATE);
  check('暂停后唱片停转（收起态也能看出没在放）',
        kPaused.miniSpin === 'paused', 'animation-play-state=' + kPaused.miniSpin);
  check('停转时唱片仍在（没有整个消失）',
        kPaused.miniVisible === true && kPaused.miniSize === '54x54', kPaused.miniSize);
  await shootClip('10-collapsed', '.bgm-mini');

  // 恢复播放，再展开
  await evaluate('(function(){document.querySelector("#bgmPlay").click();return 1})()');
  await sleep(1200);
  const kPlaying = await evaluate(READ_STATE);
  check('恢复播放后唱片重新转起来', kPlaying.miniSpin === 'running',
        'animation-play-state=' + kPlaying.miniSpin);

  const miniBtn = await centerOf('#bgmMini');
  await clickAt(miniBtn.x, miniBtn.y);
  await sleep(700);
  const k2 = await evaluate(READ_STATE);
  console.log('  展开后:', JSON.stringify({
    collapsed: k2.collapsed, bar: k2.barVisible, mini: k2.miniVisible, playing: k2.playing }));
  check('点圆钮后：面板回来、圆钮隐',
        k2.collapsed === false && k2.barVisible === true && k2.miniVisible === false);
  check('展开后仍在播放', k2.playing === 'true', 'data-playing=' + k2.playing);
  await shootClip('11-expanded', '.bgm-bar');

  // ---- 收尾：正常流程与 button-first 场景共用 ----
  // （函数声明会提升，所以上面那个提前返回的场景也能调到它）
  async function finish() {
    if (OUT_PNG) {
      fs.mkdirSync(path.dirname(OUT_PNG), { recursive: true });
      const shot = await send('Page.captureScreenshot', { format: 'png' });
      fs.writeFileSync(OUT_PNG, Buffer.from(shot.data, 'base64'));
      console.log('\n整页截图: ' + OUT_PNG);
    }

    console.log(`\n===== 汇总: ${pass.length} 通过 / ${fail.length} 失败 =====`);
    if (fail.length) {
      console.log('失败项:');
      fail.forEach((f) => console.log('  · ' + f));
    }
  }

  await finish();
  ws.close();
  cleanup();
  process.exit(fail.length ? 1 : 0);
})().catch((err) => {
  console.error('探针出错: ' + err.message);
  process.exit(2);
});
