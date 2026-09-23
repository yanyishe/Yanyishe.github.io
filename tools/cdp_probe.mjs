/**
 * 通过 CDP 从无头 Edge 里把探测结果当纯文本读回来。
 *
 * 为什么不用 --dump-dom / 截图：
 *   - Windows 下 msedge.exe 是启动器，stdout 不会回传给父进程，--dump-dom 拿不到内容
 *   - 截图能看，但断言文字不适合用眼睛核对，容易看漏
 * 所以直接起一个带 remote-debugging-port 的实例，用 CDP 的 Runtime.evaluate 取值。
 *
 * 用法: node tools/cdp_probe.mjs <html路径或url> <等待毫秒> <要执行的表达式>
 * 依赖: Node 22 自带的全局 fetch / WebSocket，无需安装任何包。
 */
import { spawn } from 'node:child_process';
import path from 'node:path';
import os from 'node:os';
import fs from 'node:fs';

const EDGE = 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe';
const [, , target, waitMsArg, expression] = process.argv;
const WAIT = Number(waitMsArg || 4000);
const PORT = 9333 + Math.floor(Math.random() * 200);

const url = /^https?:|^file:/.test(target)
  ? target
  : 'file:///' + path.resolve(target).replace(/\\/g, '/');

const profile = path.join(os.tmpdir(), 'edge-cdp-' + PORT);
fs.rmSync(profile, { recursive: true, force: true });

const child = spawn(EDGE, [
  '--headless=new',
  '--disable-gpu',
  '--no-sandbox',
  '--no-first-run',
  '--hide-scrollbars',
  '--remote-debugging-port=' + PORT,
  '--user-data-dir=' + profile,
  '--window-size=1440,900',
  url,
], { stdio: 'ignore' });

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function findPage() {
  for (let i = 0; i < 80; i++) {
    try {
      const list = await (await fetch(`http://127.0.0.1:${PORT}/json/list`)).json();
      const page = list.find((t) => t.type === 'page' && t.webSocketDebuggerUrl);
      if (page) return page;
    } catch { /* devtools 还没起来 */ }
    await sleep(250);
  }
  throw new Error('devtools endpoint 未就绪');
}

function makeClient(ws) {
  let seq = 0;
  const pending = new Map();
  ws.addEventListener('message', (ev) => {
    const msg = JSON.parse(ev.data);
    const resolve = pending.get(msg.id);
    if (resolve) { pending.delete(msg.id); resolve(msg); }
  });
  return (method, params) => new Promise((resolve) => {
    const id = ++seq;
    pending.set(id, resolve);
    ws.send(JSON.stringify({ id, method, params }));
  });
}

let exitCode = 0;
try {
  const page = await findPage();
  const ws = new WebSocket(page.webSocketDebuggerUrl);
  await new Promise((res, rej) => {
    ws.addEventListener('open', res, { once: true });
    ws.addEventListener('error', rej, { once: true });
  });
  const send = makeClient(ws);

  await sleep(WAIT);   // 等页面里的探针自己跑完

  const res = await send('Runtime.evaluate', {
    expression: expression || 'String(window.__probeResult || "（没有 __probeResult）")',
    returnByValue: true,
    awaitPromise: true,   // 表达式可以返回 Promise（用来跑有 setTimeout 的交互序列）
  });

  const value = res?.result?.result?.value;
  if (res?.result?.exceptionDetails) {
    console.error('页面内执行异常: ' + JSON.stringify(res.result.exceptionDetails));
    exitCode = 2;
  } else {
    console.log(value === undefined ? '(undefined)' : value);
  }
  ws.close();
} catch (err) {
  console.error('CDP 失败: ' + err.message);
  exitCode = 1;
} finally {
  child.kill();
  setTimeout(() => process.exit(exitCode), 150);
}
