// CDP 前端 E2E 验证（第三轮接力）：绝杀判赢(result 字段渲染) / 主动叙事台词真正播放
// 额外校验后端为新代码（响应含 result/game_over 字段）——可抓住"旧后端未重启"回归
// 用法: node scripts/cdp_e2e_check.js <port> <baseUrl>
"use strict";
const http = require("http");

const PORT = process.argv[2] || "9223";
const BASE = process.argv[3] || "http://127.0.0.1:8010";
const OPENING_FEN = "rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR w - - 0 1";

function getJson(url) {
  return new Promise((resolve, reject) => {
    http.get(url, (res) => {
      let d = "";
      res.on("data", (c) => (d += c));
      res.on("end", () => { try { resolve(JSON.parse(d)); } catch (e) { reject(e); } });
    }).on("error", reject);
  });
}
function postJson(url, data) {
  return new Promise((resolve, reject) => {
    const body = JSON.stringify(data);
    const req = http.request(url, {
      method: "POST",
      headers: { "Content-Type": "application/json", "Content-Length": Buffer.byteLength(body) },
    }, (res) => {
      let d = "";
      res.on("data", (c) => (d += c));
      res.on("end", () => { try { resolve(JSON.parse(d)); } catch (e) { reject(e); } });
    });
    req.on("error", reject);
    req.write(body);
    req.end();
  });
}
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
let results = [];
function check(name, ok, detail) {
  results.push({ name, ok, detail });
  console.log((ok ? "PASS" : "FAIL") + " | " + name + (detail ? " | " + detail : ""));
}

let msgId = 0;
const pending = new Map();
let ws = null;
function send(method, params) {
  return new Promise((resolve, reject) => {
    const id = ++msgId;
    pending.set(id, { resolve, reject });
    ws.send(JSON.stringify({ id, method, params: params || {} }));
  });
}
async function evalJs(expr) {
  const r = await send("Runtime.evaluate", { expression: expr, returnByValue: true });
  if (r.exceptionDetails) {
    throw new Error("eval exception: " + JSON.stringify(r.exceptionDetails.exception || r.exceptionDetails.text));
  }
  const ro = r.result;
  if (ro && ro.value !== undefined) return ro.value;
  return ro && ro.value;
}
async function pollEval(expr, timeoutMs) {
  const t0 = Date.now();
  for (;;) {
    try { const v = await evalJs(expr); if (v) return v; } catch (e) { /* retry */ }
    if (Date.now() - t0 > timeoutMs) return null;
    await sleep(250);
  }
}

// 点击红子直到出现合法着法高亮（跨多颗红子重试）
async function clickPieceWithTarget(maxRetries) {
  for (let i = 0; i < (maxRetries || 8); i++) {
    await evalJs(`(() => {
      const ps = document.querySelectorAll('.piece.red');
      const p = ps[${i}];
      if (!p) return false;
      const pr = p.getBoundingClientRect();
      const board = document.getElementById('board');
      board.dispatchEvent(new MouseEvent('click', {clientX: pr.left + pr.width/2, clientY: pr.top + pr.height/2, bubbles: true}));
      return true;
    })()`);
    const t = await pollEval(`document.querySelectorAll('.cell-dot').length`, 2000);
    if (t && t > 0) return true;
  }
  return false;
}
async function clickFirstTarget() {
  return evalJs(`(() => {
    const board = document.getElementById('board');
    const br = board.getBoundingClientRect();
    const t = document.querySelector('.cell-dot');
    if (!t) return false;
    const tr = t.getBoundingClientRect();
    board.dispatchEvent(new MouseEvent('click', {clientX: tr.left + tr.width/2, clientY: tr.top + tr.height/2, bubbles: true}));
    return true;
  })()`);
}

// 注入一次 makeMove 拦截（只拦 /api/moves，不拦 /api/moves/legal），返回响应对象
async function installMoveInterceptor(varName, responseObj) {
  await evalJs(`(() => {
    window.__origFetch = window.fetch;
    window.__interceptOnce = false;
    const RESP = ${JSON.stringify(responseObj)};
    window.fetch = function(url, opts){
      const u = String(url);
      const isMove = u.indexOf('/api/moves') >= 0 && u.indexOf('/api/moves/legal') < 0;
      if (isMove && !window.__interceptOnce) {
        window.__interceptOnce = true;
        return Promise.resolve(new Response(JSON.stringify(RESP), {status:200, headers:{'Content-Type':'application/json'}}));
      }
      return window.__origFetch.apply(this, arguments);
    };
    true;
  })()`);
}
async function restoreFetch() {
  await evalJs(`if (window.__origFetch) { window.fetch = window.__origFetch; window.__origFetch = null; } true;`);
}

async function main() {
  let tabs = null;
  for (let i = 0; i < 20; i++) {
    try { tabs = await getJson(`http://127.0.0.1:${PORT}/json/list`); break; } catch (e) { await sleep(500); }
  }
  if (!tabs) { console.log("FATAL: 无法连接 CDP " + PORT); process.exit(1); }
  const page = tabs.find((t) => t.type === "page" && t.url.indexOf(BASE) >= 0)
    || tabs.find((t) => t.type === "page" && t.url.indexOf("edge://") < 0)
    || tabs.find((t) => t.type === "page");
  if (!page) { console.log("FATAL: 无 page target"); process.exit(1); }
  console.log("target: " + page.url);

  ws = new WebSocket(page.webSocketDebuggerUrl);
  await new Promise((resolve, reject) => { ws.onopen = resolve; ws.onerror = reject; });
  ws.onmessage = (ev) => {
    const msg = JSON.parse(ev.data);
    if (msg.id && pending.has(msg.id)) {
      const { resolve, reject } = pending.get(msg.id);
      pending.delete(msg.id);
      if (msg.error) reject(new Error(msg.error.message)); else resolve(msg.result);
    }
  };
  await send("Runtime.enable");
  await send("Page.enable");
  // 固定桌面视口：headless 默认 500x450 会命中移动端断点，棋盘高度百分比塌成 0（6px 边框）
  await send("Emulation.setDeviceMetricsOverride", { width: 1400, height: 900, deviceScaleFactor: 1, mobile: false });

  const pageErrors = [];
  ws.addEventListener("message", (ev) => {
    const msg = JSON.parse(ev.data);
    if (msg.method === "Runtime.exceptionThrown") {
      pageErrors.push(String(msg.params.exceptionDetails && msg.params.exceptionDetails.text));
    } else if (msg.method === "Runtime.consoleAPICalled" && msg.params.type === "error") {
      pageErrors.push(msg.params.args.map((a) => a.value || a.description || "").join(" "));
    }
  });

  // ---- Phase 0.5: 后端为新代码（响应含 result/game_over）----
  try {
    const g = await postJson(BASE + "/api/games", { user_id: "cdp-fresh-" + Date.now(), personality: "laozhang" });
    const legal = await getJson(`${BASE}/api/moves/legal?fen=${encodeURIComponent(g.fen)}&color=red`);
    const mv = legal.moves[0];
    const r = await postJson(BASE + "/api/moves", { game_id: g.game_id, user_id: "cdp-fresh", from_sq: mv.from, to_sq: mv.to });
    const hasFields = Object.prototype.hasOwnProperty.call(r, "result") && Object.prototype.hasOwnProperty.call(r, "game_over");
    check("后端新代码：响应含 result/game_over 字段", !!hasFields, "keys=" + Object.keys(r).join(","));
  } catch (e) {
    check("后端新代码：响应含 result/game_over 字段", false, "ERR " + String(e && e.message || e));
  }

  // ---- Phase 0: 先导航到应用再操作（about:blank 无 localStorage 权限）----
  await send("Page.navigate", { url: BASE + "/" });
  await sleep(2500);
  const ready = await pollEval(`document.readyState === 'complete'`, 10000);
  check("页面加载完成", !!ready);
  await evalJs(`localStorage.setItem('cf_user', JSON.stringify({user_id:'cdp-e2e-' + Date.now(), nickname:'CDP测试'})); true;`);
  await send("Page.navigate", { url: BASE + "/" });
  await sleep(2500);
  const inApp = await pollEval(`!document.getElementById('app-view').classList.contains('hidden') && !!document.getElementById('user-label').textContent`, 10000);
  check("登录进入主界面", !!inApp, "user=" + (await evalJs(`document.getElementById('user-label').textContent`)));

  // ---- 人格回归：用小雅开局（验证状态栏/头像不再硬编码"老张"）----
  await evalJs(`document.getElementById('set-personality').value = 'xiaoya'; true;`);

  // ---- 开始对局 ----
  await evalJs(`document.getElementById('btn-start-game').click(); true;`);
  const roomShown = await pollEval(`!document.getElementById('game-layout').classList.contains('hidden') && document.querySelectorAll('.piece').length >= 10`, 15000);
  check("开始对局进入对局室(棋盘棋子>=10)", !!roomShown, "pieces=" + (await evalJs(`document.querySelectorAll('.piece').length`)));
  const nameShown = await evalJs(`document.getElementById('avatar-name').textContent`);
  check("人格名随选择切换为小雅", nameShown === "小雅", "avatar-name=" + nameShown);

  // ---- Phase A: 真实走一步（新代码不破坏正常对局）----
  const selA = await clickPieceWithTarget(6);
  check("选子后高亮合法着法", !!selA, "targets=" + (await evalJs(`document.querySelectorAll('.cell-dot').length`)));
  await clickFirstTarget();
  // 落子瞬间状态栏应显示当前人格名（回归：不再硬编码"老张想想怎么走"）
  const thinkingStatus = await pollEval(`document.getElementById('status').textContent.indexOf('想想') >= 0`, 6000);
  const stText = await evalJs(`document.getElementById('status').textContent`);
  check("落子瞬间状态栏用当前人格名(小雅,非硬编码'老张')",
    !!thinkingStatus && stText.indexOf("小雅") >= 0 && stText.indexOf("老张") < 0, "status=" + stText);
  // 等待真实落子完成：状态回到"该你走棋"或对局结束
  const settledA = await pollEval(`(function(){ var s=document.getElementById('status').textContent; return (s.indexOf('该你走棋')>=0 || s.indexOf('对局结束')>=0) ? s : ''; })()`, 20000);
  check("真实落子完成（AI 已应手）", !!settledA, "status=" + settledA);

  // ---- Phase B: 主动叙事 -> 台词显示 + 进入 avatar 播放 ----
  const NARR = {
    game_id: "x", user_move: { from: "a0", to: "a1" },
    ai_move: { from_sq: null, to_sq: null, win_probability: 0.5 },
    new_fen: OPENING_FEN, events: [], result: null, game_over: false, llm_output: null,
    avatar_command: { speech_text: "嗯，这盘下得有味儿。", emotion_tag: "平静", action_tag: "idle", emotion_sdk: "neutral", action_semantic: "idle", ssml: "<speak>嗯，这盘下得有味儿。</speak>" },
    long_term_memories: [], profile: { nickname: "x" },
    narrative: { type: "quiet", text: "嗯，这盘下得有味儿。" },
  };
  await installMoveInterceptor("NARR", NARR);
  const selB = await clickPieceWithTarget(8);
  if (selB) await clickFirstTarget();
  const narrShown = await pollEval(`document.getElementById('speech').textContent === '嗯，这盘下得有味儿。'`, 8000);
  check("主动叙事台词显示到气泡", !!narrShown, "speech=" + (await evalJs(`document.getElementById('speech').textContent`)));
  const avatarPlayed = await pollEval(`window.__avatarAdapter && window.__avatarAdapter.lastSpeechText === '嗯，这盘下得有味儿。'`, 8000);
  check("主动叙事进入 avatarAdapter 播放", !!avatarPlayed, "lastSpeech=" + (await evalJs(`window.__avatarAdapter ? window.__avatarAdapter.lastSpeechText : 'no-adapter'`)));
  await restoreFetch();

  // ---- Phase C: 绝杀判赢 -> result=win 渲染胜利 ----
  const WIN = {
    game_id: "x", user_move: { from: "a0", to: "a1" },
    ai_move: { from_sq: null, to_sq: null, win_probability: 0.98 },
    new_fen: OPENING_FEN, events: ["将死：AI 被将死，玩家获胜！"], result: "win", game_over: true, llm_output: null,
    avatar_command: null, long_term_memories: [], profile: { nickname: "x" }, narrative: { type: "none", text: "" },
  };
  await installMoveInterceptor("WIN", WIN);
  const selC = await clickPieceWithTarget(8);
  if (selC) await clickFirstTarget();
  const winStatus = await pollEval(`document.getElementById('status').textContent.indexOf('你将死 AI') >= 0`, 8000);
  check("绝杀判赢：result=win 渲染胜利状态", !!winStatus, "status=" + (await evalJs(`document.getElementById('status').textContent`)));
  await restoreFetch();

  // ---- 汇总 ----
  const failed = results.filter((r) => !r.ok);
  console.log("\n===== CDP E2E SUMMARY: " + (results.length - failed.length) + "/" + results.length + " passed =====");
  if (pageErrors.length) console.log("页面 JS 错误 " + pageErrors.length + " 条: " + pageErrors.slice(0, 6).join(" || "));
  if (failed.length) { failed.forEach((r) => console.log("  FAILED: " + r.name)); process.exit(1); }
  process.exit(0);
}

main().catch((e) => { console.log("FATAL: " + (e && e.stack || e)); process.exit(1); });
