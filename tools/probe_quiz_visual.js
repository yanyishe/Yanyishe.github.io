'use strict';
/* 答题页视觉体检：把「背景/卡片/文字」的实际计算值和几何打出来。
 * 用法：node tools/probe_quiz_visual.js <baseUrl> [宽] [高] */
const { spawn } = require('child_process');
const fs = require('fs');
const http = require('http');
const os = require('os');
const path = require('path');

const EDGE = 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe';
const PORT = 9423;
const BASE = process.argv[2] || 'http://127.0.0.1:8899';
const W = parseInt(process.argv[3] || '1280', 10);
const H = parseInt(process.argv[4] || '900', 10);
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

const DIAG = `(function(){
  function cs(sel){ var e = document.querySelector(sel); if (!e) return null;
    var s = getComputedStyle(e);
    return { bg: s.backgroundColor, bgImg: (s.backgroundImage||'').slice(0,40), color: s.color,
             display: s.display, position: s.position, opacity: s.opacity }; }
  function rect(sel){ var e = document.querySelector(sel); if (!e) return null;
    var b = e.getBoundingClientRect();
    return { x: Math.round(b.left), y: Math.round(b.top), w: Math.round(b.width), h: Math.round(b.height) }; }
  return JSON.stringify({
    vw: innerWidth, vh: innerHeight,
    bodyBg: getComputedStyle(document.body).backgroundColor,
    bodyBgImg: getComputedStyle(document.body).backgroundImage.slice(0, 60),
    overlay: cs('.quiz-overlay'), overlayRect: rect('.quiz-overlay'),
    card: cs('.quiz-container'), cardRect: rect('.quiz-container'),
    questionText: (document.getElementById('quizQuestionText')||{}).textContent,
    optionCount: document.querySelectorAll('.quiz-option').length,
    backRect: rect('.quiz-back'),
    bodyChildren: Array.prototype.map.call(document.body.children, function(e){ return e.tagName + '.' + e.className; })
  }, null, 1);
})()`;

(async () => {
  const profile = path.join(os.tmpdir(), 'yys-qv-' + Date.now());
  const edge = spawn(EDGE, [
    '--headless=new', '--disable-gpu', '--no-sandbox', '--no-first-run',
    '--hide-scrollbars', '--mute-audio', '--autoplay-policy=no-user-gesture-required',
    '--remote-debugging-port=' + PORT, '--remote-allow-origins=*',
    '--user-data-dir=' + profile, '--window-size=' + W + ',' + H, 'about:blank',
  ], { stdio: 'ignore' });
  const cleanup = () => {
    try { spawn('taskkill', ['/F', '/T', '/PID', String(edge.pid)], { stdio: 'ignore' }); } catch (e) {}
    try { fs.rmSync(profile, { recursive: true, force: true }); } catch (e) {}
  };
  process.on('exit', cleanup);
  for (let i = 0; i < 40; i++) {
    try { await getJSON('http://127.0.0.1:' + PORT + '/json/version'); break; } catch (e) { await sleep(250); }
  }
  const tabs = await getJSON('http://127.0.0.1:' + PORT + '/json');
  const page = tabs.filter((t) => t.type === 'page' && t.webSocketDebuggerUrl)[0];
  const ws = new WebSocket(page.webSocketDebuggerUrl);
  await new Promise((res, rej) => {
    ws.addEventListener('open', res, { once: true });
    ws.addEventListener('error', () => rej(new Error('WS 失败')), { once: true });
  });
  let id = 0; const pend = {};
  ws.addEventListener('message', (ev) => {
    const o = JSON.parse(ev.data);
    if (o.id && pend[o.id]) { pend[o.id](o); delete pend[o.id]; }
  });
  const send = (m, p) => new Promise((r) => { const i = ++id; pend[i] = r; ws.send(JSON.stringify({ id: i, method: m, params: p })); });
  await send('Page.enable');
  await send('Runtime.enable');
  await send('Page.navigate', { url: BASE + '/quiz.html' });
  for (let i = 0; i < 80; i++) {
    const ok = await send('Runtime.evaluate', { expression: '!!document.querySelector(".quiz-container")', returnByValue: true });
    if (ok.result && ok.result.result && ok.result.result.value) break;
    await sleep(250);
  }
  await sleep(2000);
  const r = await send('Runtime.evaluate', { expression: DIAG, returnByValue: true });
  console.log(r.result.result.value);
  ws.close();
})().catch((e) => console.error('崩了:', e.message));
