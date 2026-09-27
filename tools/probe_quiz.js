'use strict';
/* 独立答题页探针：node tools/probe_quiz.js
 * 检查项：签到页渲染 → 出首题 → 一路点完 24 题 → 结果出人名 → 播放器仍在
 * 另外监听 console/异常，确保从首页拆出来时没漏掉依赖的全局变量。 */
const { spawn } = require('child_process');
const fs = require('fs');
const http = require('http');
const os = require('os');
const path = require('path');

const EDGE = 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe';
const PORT = 9421;
const BASE = process.argv[2] || 'http://127.0.0.1:8899';
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
let pass = 0, fail = 0;
const check = (label, ok, detail) => {
  ok ? pass++ : fail++;
  console.log(`  ${ok ? '✅' : '❌'} ${label}${detail ? '  → ' + detail : ''}`);
};

function getJSON(url) {
  return new Promise((resolve, reject) => {
    http.get(url, (res) => {
      let d = '';
      res.on('data', (c) => (d += c));
      res.on('end', () => { try { resolve(JSON.parse(d)); } catch (e) { reject(e); } });
    }).on('error', reject);
  });
}

(async () => {
  const profile = path.join(os.tmpdir(), 'yys-quiz-' + Date.now());
  const args = [
    '--headless=new', '--disable-gpu', '--no-sandbox', '--no-first-run',
    '--hide-scrollbars', '--mute-audio',
    '--autoplay-policy=no-user-gesture-required',
    '--remote-debugging-port=' + PORT, '--remote-allow-origins=*',
    '--user-data-dir=' + profile, '--window-size=1280,900', 'about:blank',
  ];
  const edge = spawn(EDGE, args, { stdio: 'ignore' });
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
  let id = 0; const pend = {}; const errors = [];
  ws.addEventListener('message', (ev) => {
    const o = JSON.parse(ev.data);
    if (o.id && pend[o.id]) { pend[o.id](o); delete pend[o.id]; }
    if (o.method === 'Runtime.consoleAPICalled' && o.params.type === 'error')
      errors.push('console.error: ' + (o.params.args[0] || {}).description);
    if (o.method === 'Runtime.exceptionThrown')
      errors.push('异常: ' + ((o.params.exceptionDetails || {}).text || '') + ' ' +
        (((o.params.exceptionDetails || {}).exception || {}).description || ''));
  });
  const send = (m, p) => new Promise((r) => { const i = ++id; pend[i] = r; ws.send(JSON.stringify({ id: i, method: m, params: p })); });
  const evaluate = async (expr) => {
    const r = await send('Runtime.evaluate', { expression: expr, returnByValue: true, awaitPromise: true });
    return r.result ? r.result.result.value : null;
  };
  const goto = async (url) => {
    await send('Page.navigate', { url });
    for (let i = 0; i < 80; i++) {
      const ok = await evaluate('!!document.querySelector(".quiz-container")').catch(() => false);
      if (ok) break;
      await sleep(250);
    }
    await sleep(1800);
  };

  await send('Page.enable');
  await send('Runtime.enable');

  console.log('\n===== 答题页 =====');
  await goto(BASE + '/quiz.html');
  const k0 = JSON.parse(await evaluate(`JSON.stringify({
    title: document.title,
    index: (document.getElementById('quizIndex')||{}).textContent,
    q: (document.getElementById('quizQuestionText')||{}).textContent,
    opts: document.querySelectorAll('.quiz-option').length,
    back: !!document.querySelector('.quiz-back'),
    bgm: !!document.getElementById('bgmBar')
  })`));
  console.log('  ' + JSON.stringify(k0));
  check('页面标题是「签订契约」', /签订契约/.test(k0.title || ''), k0.title);
  check('进站直接显示第一题（不用再点开浮层）', k0.index === 'Q1 / 24' && k0.q.length > 4, k0.index + ' ' + k0.q.slice(0, 12));
  check('首题给出了选项按钮', k0.opts >= 2, k0.opts + ' 个');
  check('有返回首页的入口', k0.back === true);
  check('播放器跟着过来了（答着题也能听歌）', k0.bgm === true);

  // 一路点到底：每次点第一个选项
  const total = parseInt((k0.index || '').split('/')[1] || '24', 10);
  for (let i = 0; i < total; i++) {
    await evaluate('document.querySelectorAll(".quiz-option")[0].click()');
    await sleep(40);
  }
  await sleep(600);
  const res = JSON.parse(await evaluate(`JSON.stringify({
    areaShown: getComputedStyle(document.getElementById('quizResultArea')).display,
    qaShown: getComputedStyle(document.getElementById('quizQuestionArea')).display,
    name: (document.getElementById('quizResultName')||{}).textContent,
    desc: (document.getElementById('quizResultDesc')||{}).textContent.slice(0, 24),
    bgmReady: document.getElementById('bgmBar').classList.contains('is-ready')
  })`));
  console.log('  ' + JSON.stringify(res));
  check('答完 24 题出结果（切到了结果区）',
        res.areaShown === 'block' && res.qaShown === 'none');
  check('结果里有角色名和介绍', !!res.name && res.name.length > 2 && res.desc.length > 5,
        res.name + ' / ' + res.desc);
  check('播放器初始化完成（没有因为缺依赖报错）', res.bgmReady === true);

  // 重新签订
  await evaluate('document.getElementById("quizRestartBtn").click()');
  await sleep(500);
  const again = await evaluate('document.getElementById("quizIndex").textContent');
  check('「重新签订」能重开一轮', again === 'Q1 / 24', again);

  console.log('\n===== 首页 =====');
  await goto(BASE + '/index.html');
  const home = JSON.parse(await evaluate(`JSON.stringify({
    overlay: !!document.getElementById('quizOverlay'),
    href: (document.getElementById('startQuizBtn')||{}).getAttribute
            ? document.getElementById('startQuizBtn').getAttribute('href') : null,
    tag: (document.getElementById('startQuizBtn')||{}).tagName
  })`));
  console.log('  ' + JSON.stringify(home));
  check('首页不再内嵌答题浮层', home.overlay === false);
  check('签订契约变成指向独立页面的链接', home.tag === 'A' && home.href === './quiz.html', home.tag + ' ' + home.href);

  console.log('\n===== JS 报错 =====');
  check('全程没有 JS 报错', errors.length === 0, errors.slice(0, 3).join(' | ') || '干净');

  console.log('\n===== 汇总: %d 通过 / %d 失败 =====', pass, fail);
  ws.close();
  process.exitCode = fail ? 1 : 0;
})().catch((e) => { console.error('探针崩了:', e.message); process.exitCode = 1; });
