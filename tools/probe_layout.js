'use strict';
/**
 * 窄屏布局体检：把「手机上横向溢出 / 元素互相挤在一起」变成可定位的清单。
 *
 * 用法：
 *   node tools/probe_layout.js <url> [宽=390] [高=844] [输出png]
 *
 * 为什么不用普通截图判断：
 *   截图只能看出「右边被切了」，看不出是**哪个元素**撑宽的。
 *   横向溢出会顺着父级一路传染（一个定宽子元素能让整页能横向滚动），
 *   靠肉眼逐层试错非常慢。这里直接把越界的元素连同它的选择器列出来。
 *
 * 和 tools/probe_bgm.js 的分工：那个是播放器状态机验证器，
 * 这个是布局体检 —— 只管几何，不管交互。
 */

const { spawn } = require('child_process');
const fs = require('fs');
const http = require('http');
const os = require('os');
const path = require('path');

const EDGE = 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe';
const PORT = 9413;

const TARGET_URL = process.argv[2];
const WIDTH = parseInt(process.argv[3] || '390', 10);
const HEIGHT = parseInt(process.argv[4] || '844', 10);
const OUT_PNG = process.argv[5] || '';

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

function getJSON(url) {
  return new Promise((resolve, reject) => {
    http.get(url, (res) => {
      let d = '';
      res.on('data', (c) => (d += c));
      res.on('end', () => { try { resolve(JSON.parse(d)); } catch (e) { reject(e); } });
    }).on('error', reject);
  });
}

// 挑出所有越界的元素。只看元素本身，不展开它的子节点 ——
// 父级被撑宽时子级也会集体越界，那样刷屏且找不到根因。
const DIAG = `(function(){
  var vw = window.innerWidth;
  var de = document.documentElement;
  function desc(el){
    var s = el.tagName.toLowerCase();
    if (el.id) s += '#' + el.id;
    else if (el.className && typeof el.className === 'string')
      s += '.' + el.className.trim().split(/\\s+/).slice(0,2).join('.');
    return s;
  }
  var all = document.querySelectorAll('*');
  var wide = [];
  for (var i = 0; i < all.length; i++) {
    var el = all[i];
    var cs = getComputedStyle(el);
    if (cs.display === 'none' || cs.visibility === 'hidden') continue;
    var r = el.getBoundingClientRect();
    if (r.width === 0 && r.height === 0) continue;
    // 越界判定留 1px 容差，避免亚像素误报
    if (r.right > vw + 1 || r.left < -1) {
      wide.push({ sel: desc(el),
                  left: Math.round(r.left), right: Math.round(r.right),
                  w: Math.round(r.width),
                  display: cs.display, position: cs.position,
                  cls: (typeof el.className === 'string' ? el.className : '') });
    }
  }
  // 只保留「没有同样越界的父级」的那些 —— 那些才是根因
  var rootCause = wide.filter(function(item){
    return !wide.some(function(other){
      return other.cls && item.cls && other !== item &&
             other.right >= item.right - 1 && other.left <= item.left + 1 &&
             other !== item;
    });
  });
  return {
    innerWidth: vw,
    docScrollWidth: de.scrollWidth,
    bodyScrollWidth: document.body.scrollWidth,
    overflowX: de.scrollWidth - vw,
    total: wide.length,
    offenders: wide.slice(0, 16),
    rootCause: rootCause.slice(0, 12)
  };
})()`;

const FIT = `(function(){
  // 顺带量一下几个关键区块的高度占比，看"挤在一起"的具体程度
  function h(sel){ var e = document.querySelector(sel); return e ? Math.round(e.getBoundingClientRect().height) : null; }
  function r(sel){ var e = document.querySelector(sel); if(!e) return null;
    var b = e.getBoundingClientRect(); return {w:Math.round(b.width), h:Math.round(b.height),
      left:Math.round(b.left), right:Math.round(innerWidth-b.right), bottom:Math.round(innerHeight-b.bottom)}; }
  return {
    vw: innerWidth, vh: innerHeight,
    bgmBar: r('#bgmBar'),
    mainTitle: h('.main-title'),
    stepsGrid: h('.steps-grid'),
    hero: h('.hero-image')
  };
})()`;

(async () => {
  const profile = path.join(os.tmpdir(), 'yys-layout-' + Date.now());
  const edge = spawn(EDGE, [
    '--headless=new', '--disable-gpu', '--no-sandbox', '--no-first-run',
    '--hide-scrollbars', '--mute-audio',
    '--remote-debugging-port=' + PORT,
    '--remote-allow-origins=*',
    '--user-data-dir=' + profile,
    '--window-size=' + WIDTH + ',' + HEIGHT,
    'about:blank',
  ], { stdio: 'ignore' });

  const cleanup = () => {
    try { spawn('taskkill', ['/F', '/T', '/PID', String(edge.pid)], { stdio: 'ignore' }); } catch (e) {}
    try { fs.rmSync(profile, { recursive: true, force: true }); } catch (e) {}
  };
  process.on('exit', cleanup);

  let wsUrl = null;
  for (let i = 0; i < 48 && !wsUrl; i++) {
    try {
      const list = await getJSON(`http://127.0.0.1:${PORT}/json`);
      const p = list.find((t) => t.type === 'page' && t.webSocketDebuggerUrl);
      if (p) wsUrl = p.webSocketDebuggerUrl;
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
    let m; try { m = JSON.parse(ev.data); } catch (e) { return; }
    if (m.id && pending.has(m.id)) {
      const { resolve, reject } = pending.get(m.id);
      pending.delete(m.id);
      if (m.error) reject(new Error(m.error.message)); else resolve(m.result);
    }
  });
  const send = (method, params) => new Promise((resolve, reject) => {
    const id = ++msgId;
    pending.set(id, { resolve, reject });
    ws.send(JSON.stringify({ id, method, params: params || {} }));
  });
  async function evaluate(expression) {
    const r = await send('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true });
    if (r.exceptionDetails) throw new Error(r.exceptionDetails.text);
    return r.result.value;
  }

  await send('Runtime.enable');
  await send('Page.enable');
  // 真机是按视口宽布局的，必须用设备模拟而不是只改窗口大小 ——
  // 否则量到的还是桌面布局，问题会被掩盖。
  await send('Emulation.setDeviceMetricsOverride', {
    width: WIDTH, height: HEIGHT, deviceScaleFactor: 2, mobile: true,
  });
  await send('Page.navigate', { url: TARGET_URL });

  for (let i = 0; i < 60; i++) {
    const ok = await evaluate('document.readyState === "complete"')
      .catch(() => false);
    if (ok) break;
    await sleep(250);
  }
  await sleep(1500);

  const d = await evaluate(DIAG);
  const f = await evaluate(FIT);

  console.log(`视口 ${WIDTH}×${HEIGHT}  (实测 innerWidth=${d.innerWidth})`);
  console.log(`文档可滚动宽度 ${d.docScrollWidth}  横向溢出 ${d.overflowX > 0 ? '★ ' + d.overflowX + 'px' : '无'}`);
  console.log();

  if (d.overflowX > 0) {
    console.log('—— 越界元素（全部 ' + d.total + ' 个，列前 16）——');
    d.offenders.forEach((o) => {
      console.log(`  ${o.sel}`);
      console.log(`      left=${o.left} right=${o.right} w=${o.w}  position=${o.position}`);
    });
    console.log();
  }

  console.log('—— 关键区块几何 ——');
  console.log('  播放器 #bgmBar :', JSON.stringify(f.bgmBar));
  console.log('  主标题高度      :', f.mainTitle);
  console.log('  步骤网格高度    :', f.stepsGrid);
  console.log('  主视觉高度      :', f.hero);

  if (OUT_PNG) {
    fs.mkdirSync(path.dirname(OUT_PNG), { recursive: true });
    const shot = await send('Page.captureScreenshot', {
      format: 'png', captureBeyondViewport: true,
    });
    fs.writeFileSync(OUT_PNG, Buffer.from(shot.data, 'base64'));
    console.log('\n整页截图: ' + OUT_PNG);
  }

  ws.close();
  cleanup();
  process.exit(0);
})().catch((err) => {
  console.error('探针出错: ' + err.message);
  process.exit(2);
});
