#!/usr/bin/env node
// ページを「動かして」確かめるための最小 CDP ドライバ。依存ゼロ（Node 22+ の
// 組み込み WebSocket を使う。npm install も playwright も不要）。
//
// driver.sh のスクリーンショットは表示領域を撮るだけで、クリックも DOM 取得も
// できない。折りたたみ・アンカージャンプ・data-track のクリック計測など、
// 「触ってみないと分からない」変更はこちらで確認する。
//
// Usage:
//   probe.mjs <url> [options]
//     --eval <js>       ページ内で評価して結果を JSON で標準出力へ（最後に実行）
//     --pre <js>        クリック前に評価（gtag のスパイ設置など。結果は出力しない）
//     --click <sel>     セレクタをクリック（複数指定可・指定順に実行）
//     --hash <#frag>    読み込み後に location.hash を設定（アンカー挙動の確認）
//     --shot <out.png>  スクリーンショット
//     --full            --shot をページ全体にする（既定は 1280x900 の表示領域）
//     --wait <ms>       各操作後の待ち時間（既定 400）
//     --settle <ms>     load 後の待ち時間（既定 1200。地図やfetchがあるページは伸ばす）
//
// 例:
//   probe.mjs http://localhost:8000/pokemon/ --eval "document.querySelectorAll('[data-track]').length"
//   probe.mjs http://localhost:8000/pokemon/ --click '.content-collapse summary' --shot /tmp/open.png --full
import { spawn } from 'node:child_process';
import { mkdtempSync, rmSync, writeFileSync, statSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

const CHROME = process.env.CHROME
  || ['/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
      '/Applications/Chromium.app/Contents/MacOS/Chromium'].find(p => {
        try { return statSync(p).isFile(); } catch { return false; }
      })
  || 'google-chrome';

const argv = process.argv.slice(2);
const url = argv[0];
if (!url || url.startsWith('--')) {
  console.error('usage: probe.mjs <url> [--eval js] [--click sel] [--hash #f] [--shot out.png] [--full] [--wait ms] [--settle ms]');
  process.exit(2);
}
const opt = { clicks: [], wait: 400, settle: 1200, full: false };
for (let i = 1; i < argv.length; i++) {
  const a = argv[i];
  if (a === '--eval') opt.eval = argv[++i];
  else if (a === '--pre') opt.pre = argv[++i];
  else if (a === '--click') opt.clicks.push(argv[++i]);
  else if (a === '--hash') opt.hash = argv[++i];
  else if (a === '--shot') opt.shot = argv[++i];
  else if (a === '--full') opt.full = true;
  else if (a === '--wait') opt.wait = Number(argv[++i]);
  else if (a === '--settle') opt.settle = Number(argv[++i]);
  else { console.error(`unknown option: ${a}`); process.exit(2); }
}

const sleep = ms => new Promise(r => setTimeout(r, ms));
const profile = mkdtempSync(join(tmpdir(), 'pokefuta-probe-'));
const port = 9500 + Math.floor(Math.random() * 400);

const chrome = spawn(CHROME, [
  '--headless=new', '--disable-gpu', '--no-first-run', '--no-default-browser-check',
  `--user-data-dir=${profile}`, `--remote-debugging-port=${port}`,
  '--window-size=1280,900', '--hide-scrollbars', 'about:blank',
], { stdio: 'ignore' });

let ws, msgId = 0, sessionId = null;
const pending = new Map();

function send(method, params = {}, useSession = true) {
  const id = ++msgId;
  const msg = { id, method, params };
  if (useSession && sessionId) msg.sessionId = sessionId;
  ws.send(JSON.stringify(msg));
  return new Promise((resolve, reject) => pending.set(id, { resolve, reject }));
}

async function cleanup(code) {
  try { ws?.close(); } catch {}
  chrome.kill('SIGKILL');
  try { rmSync(profile, { recursive: true, force: true }); } catch {}
  process.exit(code);
}

try {
  // ── DevTools エンドポイントが立ち上がるまで待つ ──
  let browserWsUrl = null;
  for (let i = 0; i < 100; i++) {
    try {
      const r = await fetch(`http://127.0.0.1:${port}/json/version`);
      browserWsUrl = (await r.json()).webSocketDebuggerUrl;
      if (browserWsUrl) break;
    } catch {}
    await sleep(100);
  }
  if (!browserWsUrl) throw new Error('Chrome の DevTools エンドポイントに繋がらない');

  ws = new WebSocket(browserWsUrl);
  await new Promise((res, rej) => { ws.onopen = res; ws.onerror = e => rej(new Error('ws error')); });

  const loadEvents = [];
  ws.onmessage = ev => {
    const m = JSON.parse(ev.data);
    if (m.id && pending.has(m.id)) {
      const { resolve, reject } = pending.get(m.id);
      pending.delete(m.id);
      m.error ? reject(new Error(`${m.error.message} (${JSON.stringify(m.error.data ?? '')})`)) : resolve(m.result);
    } else if (m.method === 'Page.loadEventFired') loadEvents.push(m);
  };

  // ── タブを作って attach（flatten モードで sessionId 経由に統一）──
  const { targetId } = await send('Target.createTarget', { url: 'about:blank' }, false);
  ({ sessionId } = await send('Target.attachToTarget', { targetId, flatten: true }, false));

  await send('Page.enable');
  await send('Runtime.enable');
  await send('Page.navigate', { url });
  for (let i = 0; i < 150 && loadEvents.length === 0; i++) await sleep(100);
  await sleep(opt.settle);

  const evaluate = async (expr, label) => {
    const r = await send('Runtime.evaluate', {
      expression: expr, returnByValue: true, awaitPromise: true,
    });
    if (r.exceptionDetails) {
      throw new Error(`${label}: ${r.exceptionDetails.exception?.description || r.exceptionDetails.text}`);
    }
    return r.result?.value;
  };

  if (opt.pre) await evaluate(opt.pre, 'pre');

  if (opt.hash) {
    await evaluate(`location.hash = ${JSON.stringify(opt.hash)}; true`, 'hash');
    await sleep(opt.wait);
  }

  for (const sel of opt.clicks) {
    // 要素の中心を実座標でクリックする（scrollIntoView 後に座標を取り直す）。
    // el.click() だけだと :hover/レイアウト起因の不具合を見落とすため、
    // Input.dispatchMouseEvent で本物のクリックを送る。
    const box = await evaluate(`(() => {
      const el = document.querySelector(${JSON.stringify(sel)});
      if (!el) return null;
      el.scrollIntoView({ block: 'center', behavior: 'instant' });
      const r = el.getBoundingClientRect();
      return { x: r.left + r.width / 2, y: r.top + r.height / 2, w: r.width, h: r.height };
    })()`, `click ${sel}`);
    if (!box) throw new Error(`click: セレクタが見つからない: ${sel}`);
    if (box.w === 0 || box.h === 0) throw new Error(`click: 要素のサイズが 0 (非表示?): ${sel}`);
    for (const type of ['mousePressed', 'mouseReleased']) {
      await send('Input.dispatchMouseEvent', {
        type, x: box.x, y: box.y, button: 'left', clickCount: 1,
      });
    }
    await sleep(opt.wait);
  }

  let out;
  if (opt.eval) out = await evaluate(opt.eval, 'eval');

  if (opt.shot) {
    const params = { format: 'png' };
    if (opt.full) {
      // ページ全体。captureBeyondViewport だけだと高さが足りないことがあるので
      // レイアウト実寸を clip に渡す。
      const size = await evaluate(`(() => {
        const d = document.documentElement, b = document.body;
        return { w: Math.max(d.scrollWidth, b.scrollWidth), h: Math.max(d.scrollHeight, b.scrollHeight) };
      })()`, 'size');
      params.captureBeyondViewport = true;
      params.clip = { x: 0, y: 0, width: size.w, height: Math.min(size.h, 30000), scale: 1 };
    }
    const { data } = await send('Page.captureScreenshot', params);
    writeFileSync(opt.shot, Buffer.from(data, 'base64'));
    console.error(`[probe] shot -> ${opt.shot}`);
  }

  if (opt.eval) console.log(JSON.stringify(out, null, 2));
  await cleanup(0);
} catch (err) {
  console.error(`[probe] ERROR: ${err.message}`);
  await cleanup(1);
}
