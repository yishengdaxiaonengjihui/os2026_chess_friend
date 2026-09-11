// app.js —— 适老化数字人中国象棋棋友：登录 / 主界面三 Tab / 对局编排
"use strict";

(function () {
  const FILES = ["a", "b", "c", "d", "e", "f", "g", "h", "i"];

  const el = {
    // 登录
    loginView: document.getElementById("login-view"),
    appView: document.getElementById("app-view"),
    loginNickname: document.getElementById("login-nickname"),
    btnCreateAccount: document.getElementById("btn-create-account"),
    loginUsers: document.getElementById("login-users"),
    // 顶栏
    userLabel: document.getElementById("user-label"),
    btnLogout: document.getElementById("btn-logout"),
    // Tab
    tabStart: document.getElementById("tab-start"),
    tabRecords: document.getElementById("tab-records"),
    tabSettings: document.getElementById("tab-settings"),
    // 对局设置
    setSide: document.getElementById("set-side"),
    setPersonality: document.getElementById("set-personality"),
    setStrength: document.getElementById("set-strength"),
    btnStartGame: document.getElementById("btn-start-game"),
    menuArea: document.getElementById("menu-area"),
    gameSettings: document.getElementById("game-settings"),
    gameLayout: document.getElementById("game-layout"),
    btnBackMenu: document.getElementById("btn-back-menu"),
    // 棋谱回放（整页视图）
    replayView: document.getElementById("replay-view"),
    replayBoard: document.getElementById("replay-board"),
    replayStatus: document.getElementById("replay-status"),
    replayInfo: document.getElementById("replay-info"),
    replayEvents: document.getElementById("replay-events"),
    rpFirst: document.getElementById("rp-first"),
    rpPrev: document.getElementById("rp-prev"),
    rpNext: document.getElementById("rp-next"),
    rpLast: document.getElementById("rp-last"),
    btnReplayBack: document.getElementById("btn-replay-back"),
    // 对局
    board: document.getElementById("board"),
    status: document.getElementById("status"),
    winFill: document.getElementById("win-fill"),
    winbarRed: document.getElementById("winbar-red"),
    winbarBlack: document.getElementById("winbar-black"),
    btnUndo: document.getElementById("btn-undo"),
    btnDraw: document.getElementById("btn-draw"),
    btnResign: document.getElementById("btn-resign"),
    speech: document.getElementById("speech"),
    avatar: document.getElementById("avatar"),
    avatarName: document.getElementById("avatar-name"),
    avatarContainer: document.getElementById("avatar-container"),
    emotionChip: document.getElementById("emotion-chip"),
    actionChip: document.getElementById("action-chip"),
    dhChip: document.getElementById("dh-chip"),
    events: document.getElementById("events"),
    profile: document.getElementById("profile"),
    memories: document.getElementById("memories"),
    // 步骤4：语音/文字对话
    btnMic: document.getElementById("btn-mic"),
    voiceStatus: document.getElementById("voice-status"),
    voiceText: document.getElementById("voice-text"),
    // 棋谱管理
    btnRefreshRecords: document.getElementById("btn-refresh-records"),
    recordsList: document.getElementById("records-list"),
    // 通用设置
    accountName: document.getElementById("account-name"),
    renameNickname: document.getElementById("rename-nickname"),
    btnRename: document.getElementById("btn-rename"),
    btnDeleteAccount: document.getElementById("btn-delete-account"),
    modelList: document.getElementById("model-list"),
    setChatPref: document.getElementById("set-chat-pref"),
    btnSaveChatPref: document.getElementById("btn-save-chat-pref"),
    chatPrefMsg: document.getElementById("chat-pref-msg"),
    // 模态
    modalMask: document.getElementById("modal-mask"),
    modalTitle: document.getElementById("modal-title"),
    modalBody: document.getElementById("modal-body"),
    modalClose: document.getElementById("modal-close"),
    modalBack: document.getElementById("modal-back"),
  };

  const AVATARS = { laozhang: ["🧓", "老张"], xiaoya: ["👩", "小雅"] };

  const state = {
    board: new ChessBoard(el.board),
    game: null,
    fen: "",
    busy: false,
    gameOver: false,
    userSide: "red", // 玩家执子：red / black
    selected: null,  // {file, rank}
    targets: [],
  };

  let legalCache = {}; // key: fen|color -> moves[]

  // 步骤3：用户长考提醒 —— 轮到用户后较长时间没落子，AI 温和搭话
  // 问题13：12s -> 30s 才提醒；整局最多提醒 2 次，避免频繁重复"你慢慢走"；
  // 台词改为简短语气词（见 chatter.js thinkLong），不再是一大句。
  const LONG_THINK_MS = 30000;
  const LONG_THINK_MAX = 2;
  let longThinkTimer = null;
  let longThinkFired = false;
  let longThinkCount = 0;
  function startLongThinkTimer() {
    clearLongThinkTimer();
    if (longThinkCount >= LONG_THINK_MAX) return; // 整局最多提醒 2 次
    longThinkFired = false;
    longThinkTimer = setTimeout(function () {
      longThinkFired = true;
      if (!state.game || state.gameOver || state.busy) return;
      if (!window.Chatter) return;
      longThinkCount += 1;
      const line = Chatter.thinkLong(currentPersonality());
      if (line) {
        el.speech.textContent = line;
        if (avatarAdapter) avatarAdapter.speak({ speech_text: line, emotion_tag: "平静" });
      }
    }, LONG_THINK_MS);
  }
  function clearLongThinkTimer() {
    if (longThinkTimer) { clearTimeout(longThinkTimer); longThinkTimer = null; }
  }

  // ---------------- 账号 / 会话 ----------------
  function currentUser() {
    try { return JSON.parse(localStorage.getItem("cf_user") || "null"); }
    catch (e) { return null; }
  }
  function saveUser(u) { localStorage.setItem("cf_user", JSON.stringify(u)); }
  function userId() { const u = currentUser(); return u ? u.user_id : ""; }
  function currentPersonality() {
    // 步骤3：口语库需要知道当前棋友人格；从开始对局页下拉读取
    return el.setPersonality ? el.setPersonality.value : "laozhang";
  }

  // ---------------- 视图 / Tab ----------------
  function showView(name) {
    el.loginView.classList.toggle("hidden", name !== "login");
    el.appView.classList.toggle("hidden", name !== "app");
  }
  function showTab(name) {
    document.querySelectorAll(".tab").forEach(function (t) { t.classList.toggle("active", t.dataset.tab === name); });
    el.tabStart.classList.toggle("hidden", name !== "start");
    el.tabRecords.classList.toggle("hidden", name !== "records");
    el.tabSettings.classList.toggle("hidden", name !== "settings");
    if (name === "start") initStartTab();
    if (name === "records") renderRecords();
    if (name === "settings") renderSettings();
  }

  // ---------------- 登录 ----------------
  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
    });
  }

  async function renderLoginUsers() {
    try {
      const res = await API.listUsers();
      const list = res.users || [];
      el.loginUsers.innerHTML = "";
      if (!list.length) {
        el.loginUsers.innerHTML = "<div class='muted'>还没有账号，输入昵称创建一个吧</div>";
        return;
      }
      list.forEach(function (u) {
        const b = document.createElement("button");
        b.className = "user-btn";
        b.innerHTML = "<span class='u-nick'>" + esc(u.nickname) + "</span><span class='u-meta'>" + (u.games_count || 0) + " 局</span>";
        b.addEventListener("click", function () { loginAs(u); });
        el.loginUsers.appendChild(b);
      });
    } catch (e) {
      el.loginUsers.innerHTML = "<div class='muted'>账号加载失败：" + esc(e.message) + "</div>";
    }
  }

  el.btnCreateAccount.addEventListener("click", createAccount);
  el.loginNickname.addEventListener("keydown", function (ev) { if (ev.key === "Enter") createAccount(); });
  async function createAccount() {
    const nick = el.loginNickname.value.trim();
    if (!nick) return;
    try {
      const u = await API.createUser(nick);
      el.loginNickname.value = "";
      loginAs(u);
    } catch (e) {
      alert("创建账号失败：" + e.message);
    }
  }

  function loginAs(u) {
    saveUser(u);
    el.userLabel.textContent = u.nickname;
    showView("app");
    showTab("start");
  }

  el.btnLogout.addEventListener("click", function () { logout(); });
  function logout() {
    localStorage.removeItem("cf_user");
    if (dhWs) { try { dhWs.close(); } catch (e) { /* 忽略 */ } dhWs = null; }
    resetGameState();
    showView("login");
    renderLoginUsers();
  }

  function resetGameState() {
    state.game = null;
    state.fen = "";
    state.gameOver = false;
    state.userSide = "red";
    state.selected = null;
    state.targets = [];
    legalCache = {};
    longThinkCount = 0; // 新对局重置长考提醒次数
    clearLongThinkTimer();
    state.board.setFen("");
    showSettingsForm();
  }

  // ---------------- 对局设置 / 开始对局 ----------------
  // 开始对局页 = 只有「对局设置 + 开始对局」；对局室整页独立，点开始对局才出现
  function showSettingsForm() {
    if (avatarAdapter) avatarAdapter.stop(); // 退出对局：清空语音队列
    stopVoice(); // 退出对局：停止麦克风监听
    el.gameLayout.classList.add("hidden");
    el.menuArea.classList.remove("hidden");
  }
  function showGameRoom() {
    el.menuArea.classList.add("hidden");
    el.gameLayout.classList.remove("hidden");
  }
  function initStartTab() { showSettingsForm(); }
  function yourTurnText() { return state.userSide === "black" ? "该你走棋（黑方）" : "该你走棋（红方）"; }

  function updateWinbarLabels() {
    if (state.userSide === "black") {
      el.winbarRed.textContent = "红方(AI)";
      el.winbarBlack.textContent = "黑方(你)";
    } else {
      el.winbarRed.textContent = "红方(你)";
      el.winbarBlack.textContent = "黑方(AI)";
    }
  }

  el.btnStartGame.addEventListener("click", newGame);
  el.btnBackMenu.addEventListener("click", function () { showTab("start"); });
  document.querySelectorAll(".tab").forEach(function (t) {
    t.addEventListener("click", function () { showTab(t.dataset.tab); });
  });

  async function newGame() {
    state.busy = true;
    state.board.setBusy(true);
    try {
      const personality = el.setPersonality.value;
      const side = el.setSide.value;
      const strength = el.setStrength.value;
      setAvatar(personality);
      resetPanel();
      const game = await API.newGame(userId(), personality, side, strength);
      state.game = game;
      state.gameOver = false;
      state.userSide = game.side === "black" ? "black" : "red";
      state.fen = game.fen;
      state.selected = null;
      state.targets = [];
      legalCache = {};
      state.board.clearSelection();
      updateWinbarLabels();
      showGameRoom(); // 先显示对局室（棋盘获得真实尺寸）再渲染棋盘
      state.board.setFen(game.fen);
      if (game.ai_opening && game.ai_opening.from_sq) {
        state.board.markAiMove(game.ai_opening.from_sq, game.ai_opening.to_sq);
        addEvent("AI(红) 先行：" + game.ai_opening.from_sq + "→" + game.ai_opening.to_sq);
        setStatus("AI(红) 已落子，该你走棋（黑方）");
      } else {
        setStatus("该你走棋（红方）");
        addEvent("新对局开始，你是红方，先行。");
      }
      if (!game.digital_human_enabled) {
        el.avatar.style.opacity = "0.4";
        el.avatar.title = "数字人已降级（ENABLE_DIGITAL_HUMAN=false）";
        setDhState("off");
      } else {
        el.avatar.style.opacity = "1";
        setDhState("idle");
        initAvatarAdapter(true, personality);
        connectDhWs(game.game_id);
      }
      // 步骤4增强：开局后麦克风自动开启（无需手动点），自动判断是否说完一句
      autoStartVoice();
    } catch (err) {
      setStatus("开局失败：" + err.message);
    } finally {
      state.busy = false;
      state.board.setBusy(false);
    }
  }

  // ---------------- 棋盘落子 ----------------
  function fileToSq(file, rank) { return FILES[file] + rank; }

  function pieceAt(file, rank) {
    if (!state.fen) return null;
    const ranks = state.fen.split(" ")[0].split("/");
    const row = ranks[rank] || "";
    let idx = 0;
    for (const ch of row) {
      if (/[0-9]/.test(ch)) { idx += parseInt(ch, 10); continue; }
      if (idx === file) return ch;
      idx++;
    }
    return null;
  }
  function isRed(ch) { return !!ch && ch === ch.toUpperCase(); }
  function isUserPiece(ch) { return state.userSide === "red" ? isRed(ch) : !isRed(ch); }

  // 本地乐观落子（仅即时渲染，权威 FEN 以后端为准）
  function expandRow(row) {
    const out = [];
    for (const ch of row) {
      if (/[0-9]/.test(ch)) { for (let i = 0; i < +ch; i++) out.push(null); }
      else out.push(ch);
    }
    return out;
  }
  function compressRow(arr) {
    let s = "", run = 0;
    for (const c of arr) {
      if (!c) run++;
      else { if (run) { s += run; run = 0; } s += c; }
    }
    if (run) s += run;
    return s;
  }
  function applyLocalMove(fen, fromSq, toSq) {
    const parts = fen.split(" ");
    const ranks = parts[0].split("/").map(expandRow);
    const ff = fromSq.charCodeAt(0) - 97, fr = +fromSq[1];
    const tf = toSq.charCodeAt(0) - 97, tr = +toSq[1];
    const piece = ranks[fr][ff];
    ranks[tr][tf] = piece;
    ranks[fr][ff] = null;
    parts[0] = ranks.map(compressRow).join("/");
    parts[1] = parts[1] === "w" ? "b" : "w";
    return parts.join(" ");
  }

  function setStatus(t) { el.status.textContent = t; }

  function addEvent(text) {
    const li = document.createElement("li");
    li.textContent = new Date().toLocaleTimeString("zh-CN", { hour12: false }) + "  " + text;
    el.events.prepend(li);
    const muted = el.events.querySelector(".muted");
    if (muted) muted.remove();
  }

  function renderProfile(profile) {
    if (!profile) return;
    el.profile.innerHTML = "";
    const rows = [
      ["昵称", profile.nickname],
      ["棋风", profile.style],
      ["棋力", profile.strength],
      ["偏好", profile.preferences || "—"],
      ["惯用开局", profile.opening || "—"],
      ["备注", profile.notes || "—"],
    ];
    for (const kv of rows) {
      const d = document.createElement("div");
      d.innerHTML = "<b>" + kv[0] + "：</b>" + kv[1];
      el.profile.appendChild(d);
    }
    if (profile.stats && profile.stats.games > 0) {
      const s = profile.stats;
      const d = document.createElement("div");
      d.innerHTML = "<b>历史战绩：</b>共" + s.games + "局 · 胜" + s.wins + "负" + s.losses + "平" + s.draws + " · 吃子" + s.user_captures + "枚";
      el.profile.appendChild(d);
    }
  }

  function renderMemories(list) {
    el.memories.innerHTML = "";
    if (!list || list.length === 0) {
      const li = document.createElement("li");
      li.className = "muted";
      li.textContent = "暂无（下几局后这里会有 AI 记住你的话）";
      el.memories.appendChild(li);
      return;
    }
    for (const m of list) {
      const li = document.createElement("li");
      li.textContent = "💬 " + m;
      el.memories.appendChild(li);
    }
  }

  function setAvatar(personality) {
    const a = AVATARS[personality] || AVATARS.laozhang;
    el.avatar.textContent = a[0];
    el.avatarName.textContent = a[1];
  }

  function resetPanel() {
    el.speech.textContent = "你好呀，咱开局下棋吧！";
    el.emotionChip.textContent = "情绪 --";
    el.actionChip.textContent = "动作 --";
    el.winFill.style.width = "50%";
    el.events.innerHTML = "<li class='muted'>暂无</li>";
    el.profile.innerHTML = "<span class='muted'>开局后逐步生成…</span>";
    renderMemories([]);
    setStatus("开局中…");
  }

  // ---------------- 数字人 ----------------
  function setDhState(state) {
    const map = {
      speaking: "🎤 数字人：讲话中",
      thinking: "🤔 让我想想…",
      idle: "🤖 数字人：就绪",
      off: "⛔ 数字人：已关闭",
    };
    el.dhChip.textContent = map[state] || ("🤖 数字人：" + state);
  }

  let dhWs = null;
  let avatarAdapter = null;

  function initAvatarAdapter(dhEnabled, personality) {
    personality = personality || "laozhang";
    if (!dhEnabled || !window.AvatarAdapter) return;
    // 双凭证（问题14）：人格切换后必须用该人格的 AppId/AppSecret 重建会话
    if (avatarAdapter) {
      if (avatarAdapter._personality === personality) return; // 同一人格无需重建
      try { avatarAdapter.dispose(); } catch (e) { /* 忽略 */ }
      avatarAdapter = null;
      window.__avatarAdapter = null;
    }
    fetch("/api/info")
      .then(function (r) { return r.json(); })
      .then(function (info) {
        var x = info.xmov || {};
        var cred = (x.personalities && x.personalities[personality]) || x;
        if (!cred.app_id) { setDhState("off"); return; }
        avatarAdapter = new AvatarAdapter({
          appId: cred.app_id,
          appSecret: cred.app_secret,
          gateway: x.gateway || cred.gateway,
        });
        avatarAdapter._personality = personality; // 记录当前人格（供切换重建判断）
        window.__avatarAdapter = avatarAdapter; // 调试/验证口：CDP 检查队列与情绪超时
        avatarAdapter.onState = function (s) { setDhState(s); };
        avatarAdapter.onEmotionReset = function () {
          // 问题11：情绪超时自动重置为平静
          if (el.emotionChip) el.emotionChip.textContent = "情绪 平静";
        };
        avatarAdapter.onReady = function () {
          // 数字人就绪：显示横屏画布，隐藏 emoji 占位头像
          var fb = document.getElementById("avatar-fallback");
          if (fb) fb.style.display = "none";
          el.avatarContainer.classList.remove("hidden");
        };
        // 回声防护：数字人发声时暂停麦克风识别，播完恢复，避免 TTS 被收进去再当输入
        avatarAdapter.onSpeechStart = function () { voiceMute(); };
        avatarAdapter.onSpeechEnd = function () { voiceUnmute(); };
        // 每句播完把 AI 台词记入字幕历史（时间戳=播放结束时刻，贴近回声发生期），
        // 供"相邻行相似度 + 时间窗"回声检测比对
        avatarAdapter.onSpeechDone = function (text) {
          lastAiTs = Date.now(); // 记录播放完成时刻（isEchoText 时间窗）
          recordSubtitle(text, "ai");
        };
        avatarAdapter.init();
      })
      .catch(function () { setDhState("off"); });
  }

  function connectDhWs(gameId) {
    if (dhWs) { try { dhWs.close(); } catch (e) { /* 忽略 */ } dhWs = null; }
    try {
      const proto = location.protocol === "https:" ? "wss://" : "ws://";
      dhWs = new WebSocket(proto + location.host + "/ws/game/" + gameId);
      dhWs.onmessage = function (ev) {
        let msg;
        try { msg = JSON.parse(ev.data); } catch (e) { return; }
        if (msg.type === "avatar_state" && msg.state) setDhState(msg.state);
      };
      dhWs.onclose = function () { dhWs = null; };
    } catch (e) { /* WS 不可用时静默 */ }
  }

  // ---------------- 步骤4：语音/文字对话（开局自动开启 + 自动判断说完一句）----------------
  let sr = null;        // SpeechRecognition 实例
  let srActive = false; // 是否在识别中
  let srFinal = "";     // 已确认的识别文本
  let srLastActive = 0; // 最近一次识别到语音的时间戳（静默检测用）
  let srSilenceTimer = null; // 静默检测定时器
  let srAuto = false;   // 自动监听模式（开局后开启，onend 自动重启）

  function initVoice() {
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SR) {
      if (el.btnMic) { el.btnMic.disabled = true; el.btnMic.title = "浏览器不支持语音识别"; }
      if (el.voiceStatus) el.voiceStatus.textContent = "浏览器不支持语音识别";
      return;
    }
    sr = new SR();
    sr.lang = "zh-CN";
    sr.continuous = true;
    sr.interimResults = true;
    sr.onresult = function (ev) {
      let interim = "", final = "";
      for (let i = ev.resultIndex; i < ev.results.length; i++) {
        const t = ev.results[i][0].transcript;
        if (ev.results[i].isFinal) final += t; else interim += t;
      }
      if (final) srFinal += final;
      srLastActive = Date.now(); // 有语音活动，刷新静默计时
      const shown = (srFinal + interim).trim();
      if (el.voiceText) el.voiceText.textContent = shown;
      if (el.voiceStatus) el.voiceStatus.textContent = "正在听…";
      // 有 final 结果时，立刻做一次"说完"判定（浏览器已确认一句）
      if (final) scheduleSilenceCheck();
    };
    sr.onerror = function (ev) {
      if (ev.error === "not-allowed" || ev.error === "service-not-allowed") {
        srActive = false;
        srAuto = false;
        stopSilenceCheck();
        if (el.voiceStatus) el.voiceStatus.textContent = "麦克风权限被拒绝，请点麦克风重试";
        if (el.btnMic) el.btnMic.classList.remove("listening");
      } else if (ev.error === "no-speech") {
        // 静音：若已有文字则当作说完
        maybeSend();
      }
    };
    sr.onend = function () {
      srActive = false;
      if (el.btnMic) el.btnMic.classList.remove("listening");
      maybeSend();
      // 自动监听模式：识别结束后自动重启，保持一直能听到
      // （回声防护：数字人发声期间的停止(srMuted)不重启，播完由 voiceUnmute 恢复）
      if (srAuto && !srMuted && state.game && !state.gameOver) {
        scheduleSilenceCheck();
        try { sr.start(); srActive = true; if (el.btnMic) el.btnMic.classList.add("listening"); }
        catch (e) { /* 重启失败，静默 */ }
      } else {
        stopSilenceCheck();
      }
    };
  }

  // 静默检测：识别到内容后，若 1.2s 内没有新的语音结果，判定为"说完一句话"
  function scheduleSilenceCheck() {
    stopSilenceCheck();
    srSilenceTimer = setTimeout(function () {
      const idle = Date.now() - srLastActive;
      if (idle >= 1200 && srFinal.trim()) {
        const text = srFinal.trim();
        srFinal = "";
        if (el.voiceText) el.voiceText.textContent = "";
        // 回声防护：数字人台词（或其回声变体）被误收则丢弃
        if (isEcho(text)) return;
        recordSubtitle(text, "user");
        sendUserSpeech(text);
      }
    }, 1300);
  }
  function stopSilenceCheck() {
    if (srSilenceTimer) { clearTimeout(srSilenceTimer); srSilenceTimer = null; }
  }

  function stopVoice() {
    srAuto = false;
    stopSilenceCheck();
    if (sr && srActive) { try { sr.stop(); } catch (e) { /* 忽略 */ } }
    srActive = false;
    if (el.btnMic) el.btnMic.classList.remove("listening");
    if (el.voiceStatus) el.voiceStatus.textContent = "已停止听讲，点麦克风重新开启";
  }

  // ---- 回声防护：数字人发声期间彻底关闭麦克风，播完(留余量)恢复 ----
  let srMuted = false; // 是否被数字人播放静音（非用户主动停止）
  let srUnmuteTimer = null; // 恢复识别延时（等 TTS 尾音/混响过去）
  const SR_UNMUTE_DELAY = 1800; // 播完后再等 1.8s 恢复，杜绝尾音/混响回声（原 1s 偏短）
  function voiceMute() {
    srMuted = true;
    stopSilenceCheck();
    if (srUnmuteTimer) { clearTimeout(srUnmuteTimer); srUnmuteTimer = null; }
    srFinal = ""; // 丢弃静音瞬间可能残留的半句识别，防止误发
    if (el.voiceText) el.voiceText.textContent = "";
    // 用 abort() 立即终止并丢弃全部已采集音频（stop() 会先处理缓冲，TTS 开头仍可能被收进去）
    if (sr && srActive) { try { sr.abort(); } catch (e) { /* 忽略 */ } }
    srActive = false;
    if (el.btnMic) el.btnMic.classList.remove("listening");
  }
  function voiceUnmute() {
    srMuted = false;
    // 自动监听模式下恢复识别（仍在对局、未被用户手动关闭时），延迟等尾音过去
    if (srUnmuteTimer) { clearTimeout(srUnmuteTimer); srUnmuteTimer = null; }
    srUnmuteTimer = setTimeout(function () {
      srUnmuteTimer = null;
      // 兜底：若数字人此刻仍在发声状态(估算不足/语速极慢)，继续关闭再等
      if (avatarAdapter && avatarAdapter._playing) {
        voiceUnmute();
        return;
      }
      if (srAuto && state.game && !state.gameOver && sr) {
        srLastActive = Date.now();
        if (!srActive) startListening();
      }
    }, SR_UNMUTE_DELAY);
  }

  // ---- 回声过滤（用户方案：字幕历史 + 相邻行相似度 + 时间窗）----
  // 字幕历史：AI 台词 + 已确认用户发言（带时间戳），用于判断新识别行是否回声
  let subtitleHistory = [];
  let lastAiTs = 0; // 最近一句 AI 台词播放完成的时刻（isEchoText 时间窗用）
  const ECHO_SIM_THRESHOLD = 0.85;  // 相似度阈值（用户建议 0.85-0.92）
  const ECHO_TIME_WINDOW = 3000;    // 时间窗 < 3s（原 2.2s，尾音+识别延迟可能超窗）
  const SUBTITLE_MAX = 16;

  function recordSubtitle(text, src) {
    if (!text) return;
    subtitleHistory.push({ text: text, ts: Date.now(), src: src || "user" });
    if (subtitleHistory.length > SUBTITLE_MAX) subtitleHistory.shift();
  }

  // 编辑距离（Levenshtein）
  function editDistance(a, b) {
    const m = a.length, n = b.length;
    if (!m) return n; if (!n) return m;
    const dp = new Uint32Array(n + 1);
    for (let j = 0; j <= n; j++) dp[j] = j;
    for (let i = 1; i <= m; i++) {
      let prev = dp[0];
      dp[0] = i;
      for (let j = 1; j <= n; j++) {
        const tmp = dp[j];
        const cost = a[i - 1] === b[j - 1] ? 0 : 1;
        dp[j] = Math.min(dp[j] + 1, dp[j - 1] + 1, prev + cost);
        prev = tmp;
      }
    }
    return dp[n];
  }

  // 字符集合 Jaccard（对中文口语识别变体更鲁棒）
  function jaccardSim(a, b) {
    const sa = new Set(a), sb = new Set(b);
    if (!sa.size && !sb.size) return 1;
    let inter = 0;
    for (const ch of sa) { if (sb.has(ch)) inter++; }
    return inter / (sa.size + sb.size - inter);
  }

  // 两行文本相似度：编辑距离相似度 与 Jaccard 取较高者
  function textSimilarity(a, b) {
    if (!a || !b) return 0;
    if (a === b) return 1;
    const maxLen = Math.max(a.length, b.length);
    const editSim = maxLen ? 1 - editDistance(a, b) / maxLen : 1;
    return Math.max(editSim, jaccardSim(a, b));
  }

  // 回声判定：与时间窗内(<=2.2s)的历史行相似度>=阈值 -> 回声
  function isEchoByHistory(text, now) {
    if (!text) return false;
    const t = now || Date.now();
    for (let i = subtitleHistory.length - 1; i >= 0; i--) {
      const h = subtitleHistory[i];
      if (t - h.ts > ECHO_TIME_WINDOW) break; // 历史按时间有序，超出窗口忽略
      if (textSimilarity(text, h.text) >= ECHO_SIM_THRESHOLD) return true;
    }
    return false;
  }

  // 快速路径：识别文本与 AI 刚说的台词精确/子串一致（仅限 AI 播完后的时间窗内，
  // 避免超窗后用户说相同内容被误判——时间间隔是回声判定的硬条件）
  function isEchoText(text) {
    if (!avatarAdapter || !avatarAdapter.lastSpeechText) return false;
    if (Date.now() - lastAiTs > ECHO_TIME_WINDOW) return false; // 超窗不判回声
    const ai = (avatarAdapter.lastSpeechText || "").trim();
    if (!ai || !text) return false;
    return text === ai || ai.indexOf(text) >= 0 || text.indexOf(ai) >= 0;
  }

  // 统一回声判定：任一命中即回声
  function isEcho(text) {
    return isEchoText(text) || isEchoByHistory(text);
  }

  // 调试/验证口：回声过滤算法单测（CDP 与真实排障用）
  window.__echoDebug = {
    sim: function (a, b) { return textSimilarity(a, b); },
    isEcho: function (t) { return isEcho(t); },
    record: function (t, s) { recordSubtitle(t, s); },
    history: function () { return subtitleHistory.slice(); },
    clear: function () { subtitleHistory = []; },
    threshold: ECHO_SIM_THRESHOLD,
    window: ECHO_TIME_WINDOW,
  };

  function maybeSend() {
    const text = (srFinal || "").trim();
    if (!text) return;
    srFinal = "";
    if (el.voiceText) el.voiceText.textContent = "";
    // 回声防护：数字人刚才说的话（或其回声变体）被麦克风误收 -> 丢弃
    if (isEcho(text)) {
      if (el.voiceStatus) el.voiceStatus.textContent = "正在听…";
      return;
    }
    recordSubtitle(text, "user");
    sendUserSpeech(text);
  }

  // 发送用户说的话给棋友，并播报 AI 回复（bargeIn 高优先级）
  async function sendUserSpeech(text) {
    if (!state.game) { if (el.voiceStatus) el.voiceStatus.textContent = "请先开始对局"; return; }
    if (el.voiceStatus) el.voiceStatus.textContent = "你说：" + text;
    if (el.speech) el.speech.textContent = "（你说）" + text;
    try {
      const res = await API.chat(state.game.game_id, state.game.user_id, text);
      if (res.status === "noise_ignored") {
        if (el.voiceStatus) el.voiceStatus.textContent = "没听清，再说一遍？";
        return;
      }
      const reply = res.reply;
      if (reply) {
        if (el.speech) el.speech.textContent = reply.speech_text;
        if (el.emotionChip) el.emotionChip.textContent = "情绪 " + reply.emotion_tag;
        if (el.actionChip) el.actionChip.textContent = "动作 " + reply.action_tag;
        // 高优先级播报：打断当前数字人语音，优先回应玩家
        if (avatarAdapter) {
          avatarAdapter.bargeIn({ speech_text: reply.speech_text, emotion_tag: reply.emotion_tag });
        } else {
          setDhState("speaking");
        }
      }
      if (el.voiceStatus) el.voiceStatus.textContent = "正在听…";
    } catch (err) {
      if (el.voiceStatus) el.voiceStatus.textContent = "发送失败：" + err.message;
    }
  }

  // 自动开启监听（开局后调用）：无需手动点麦克风
  function autoStartVoice() {
    if (!sr) { initVoice(); if (!sr) return; }
    srAuto = true;
    srLastActive = Date.now();
    if (!srActive) startListening();
  }

  // 事件绑定：点击切换 开/停
  function bindVoice() {
    if (!el.btnMic) return;
    el.btnMic.addEventListener("click", function (e) {
      e.preventDefault();
      if (srActive) { stopVoice(); }
      else { srAuto = true; startListening(); }
    });
  }

  function startListening() {
    if (!sr) { initVoice(); if (!sr) return; }
    if (!state.game) { if (el.voiceStatus) el.voiceStatus.textContent = "请先开始对局"; return; }
    // 回声防护：数字人正在发声时不让麦克风启动，避免 TTS 被收进去
    if (srMuted) {
      if (el.voiceStatus) el.voiceStatus.textContent = "棋友正在说话，稍等一下…";
      return;
    }
    srFinal = "";
    srLastActive = Date.now();
    srActive = true;
    if (el.btnMic) el.btnMic.classList.add("listening");
    if (el.voiceStatus) el.voiceStatus.textContent = "正在听…";
    try { sr.start(); } catch (e) { srActive = false; if (el.btnMic) el.btnMic.classList.remove("listening"); }
  }

  // 初始化语音（页面加载时探测支持性，进入对局即可用）
  initVoice();
  bindVoice();

  // ---------------- 选子 / 落子 ----------------
  async function selectPiece(file, rank) {
    const piece = pieceAt(file, rank);
    if (!piece || !isUserPiece(piece)) { state.board.clearSelection(); return; }
    state.selected = { file, rank };
    state.board.select(file, rank);
    try {
      const color = state.userSide;
      const key = state.fen + "|" + color;
      let moves = legalCache[key];
      if (!moves) {
        const res = await API.legalMoves(state.fen, color);
        moves = res.moves;
        legalCache[key] = moves;
      }
      const targets = [];
      for (const m of moves) {
        if (m.from !== fileToSq(file, rank)) continue;
        const tf = FILES.indexOf(m.to[0]);
        const tr = parseInt(m.to[1], 10);
        targets.push({ file: tf, rank: tr, capture: !!pieceAt(tf, tr) });
      }
      state.targets = targets;
      state.board.highlightTargets(targets);
    } catch (err) {
      setStatus("获取着法失败：" + err.message);
    }
  }

  // 步骤2：AI 思考停顿时长 —— 按局面加权随机，制造真人感
  function aiThinkDelay(resp) {
    // 基础随机：0.8~1.8 秒
    let delay = 800 + Math.random() * 1000;
    const ev = (resp && resp.events ? resp.events : []).join(" ");
    // 关键局面（吃子/将军/胜负）多"想"一会儿：+0.6~1.8 秒
    if (/吃子|将军|将死|困毙/.test(ev)) {
      delay += 600 + Math.random() * 1200;
    }
    return Math.round(delay);
  }

  async function makeMove(file, rank) {
    if (state.gameOver) return;
    state.busy = true;
    state.board.setBusy(true);
    clearLongThinkTimer(); // 用户已落子，取消长考提醒
    // 问题2：落子属游戏操作，不粗暴打断正在播放的语音；新评论进入适配器队列排队
    const fromSq = fileToSq(state.selected.file, state.selected.rank);
    const toSq = fileToSq(file, rank);
    const optimistic = applyLocalMove(state.fen, fromSq, toSq);
    state.fen = optimistic;
    state.board.movePiece(fromSq, toSq, optimistic);
    legalCache = {};
    setStatus("你已落子，老张想想怎么走…");
    try {
      const resp = await API.makeMove(state.game.game_id, state.game.user_id, fromSq, toSq);
      // 步骤2：真人感思考停顿 —— 拿到 AI 应手后不立即落子，先"琢磨"一会儿
      setDhState("thinking");
      // 问题13：去掉"每手必嘟囔"——AI 落子前不再说"嗯…这步得琢磨琢磨"，
      // 减少开口频率，让数字人只在关键节点或用户搭话时说话，更像真人。
      const thinkDelay = aiThinkDelay(resp);
      await new Promise(function (r) { setTimeout(r, thinkDelay); });
      state.fen = resp.new_fen;
      state.board.setFen(resp.new_fen);
      if (resp.ai_move && resp.ai_move.from_sq) {
        state.board.markAiMove(resp.ai_move.from_sq, resp.ai_move.to_sq);
        addEvent("你 " + fromSq + "→" + toSq + "，AI " + resp.ai_move.from_sq + "→" + resp.ai_move.to_sq + (resp.ai_move.piece ? "（" + resp.ai_move.piece + "）" : ""));
      } else {
        addEvent("你 " + fromSq + "→" + toSq);
      }
      for (const e of resp.events) addEvent(e);

      const llm = resp.llm_output;
      const pers = currentPersonality();
      if (llm) {
        // 步骤3：口语化补丁 —— 在 LLM 台词前按局面补一句口头禅，去机械感
        let speechText = llm.speech_text;
        if (window.Chatter) {
          const banter = Chatter.afterMove(pers, resp);
          if (banter.line && !speechText.startsWith(banter.line)) {
            speechText = banter.line + speechText;
          }
        }
        el.speech.textContent = speechText;
        el.emotionChip.textContent = "情绪 " + llm.emotion_tag;
        el.actionChip.textContent = "动作 " + llm.action_tag;
      } else {
        // 问题1：言语触发决策后 AI 静默思索。
        // 问题13：静默就真静默——不再用口语库补话，避免后端"不开口"时前端越权播语音。
        el.speech.textContent = "…";
        el.emotionChip.textContent = "情绪 平静";
        el.actionChip.textContent = "动作 思考";
      }
      if (resp.avatar_command) {
        // 主动叙事（llm 为空但数字人开口）：把台词显示到气泡，与"…"区分开
        if (!llm && resp.avatar_command.speech_text) {
          el.speech.textContent = resp.avatar_command.speech_text;
          el.emotionChip.textContent = "情绪 " + (resp.avatar_command.emotion_tag || "平静");
          el.actionChip.textContent = "动作 " + (resp.avatar_command.action_tag || "idle");
        }
        if (avatarAdapter) avatarAdapter.speak(resp.avatar_command);
        else setDhState("speaking");
      } else if (llm) {
        setDhState("off");
      } else {
        setDhState("thinking");
      }
      if (resp.ai_move && typeof resp.ai_move.win_probability === "number") {
        const userWin = (1 - resp.ai_move.win_probability) * 100;
        el.winFill.style.width = Math.max(2, Math.min(98, userWin)) + "%";
      }
      renderProfile(resp.profile);
      renderMemories(resp.long_term_memories);

      // 对局结束优先用后端 result（win/lose/draw），更可靠；兜底按事件推断
      if (resp.game_over || (resp.result && resp.result !== "none")) {
        state.gameOver = true;
        clearLongThinkTimer();
        if (resp.result === "win") {
          setStatus("对局结束：你将死 AI，赢了！点击「开始对局」再来一盘");
        } else if (resp.result === "lose") {
          setStatus("对局结束：你被将死了，AI 获胜。点击「开始对局」再来一盘");
        } else if (resp.result === "draw") {
          setStatus("对局结束：困毙，和棋。点击「开始对局」再来一盘");
        } else {
          const hasMate = resp.events.some(function (e) { return e.indexOf("将死") >= 0; });
          if (hasMate) {
            const userWon = resp.events.some(function (e) { return e.indexOf("玩家获胜") >= 0; });
            setStatus(userWon ? "对局结束：你将死 AI，赢了！点击「开始对局」再来一盘" : "对局结束：你被将死了，AI 获胜。点击「开始对局」再来一盘");
          } else {
            setStatus("对局结束。点击「开始对局」再来一盘");
          }
        }
        renderRecords();
      } else if (resp.events.some(function (e) { return e.indexOf("困毙") >= 0; })) {
        state.gameOver = true;
        clearLongThinkTimer();
        setStatus("对局结束：困毙，和棋。点击「开始对局」再来一盘");
        renderRecords();
      } else {
        setStatus(yourTurnText());
        startLongThinkTimer(); // 步骤3：轮到用户，启动长考提醒
      }
    } catch (err) {
      setStatus("落子失败：" + err.message);
    } finally {
      state.busy = false;
      state.board.setBusy(false);
      state.selected = null;
      state.targets = [];
      state.board.clearTargets();
      state.board.clearSelection();
    }
  }

  state.board.onSquareClick = function (file, rank) {
    if (state.busy) return;
    if (state.gameOver) return;
    if (!state.game) { setStatus("请先开始对局"); return; }
    if (state.selected) {
      const isTarget = state.targets.some(function (t) { return t.file === file && t.rank === rank; });
      if (isTarget) { makeMove(file, rank); return; }
      const piece = pieceAt(file, rank);
      if (piece && isUserPiece(piece)) { selectPiece(file, rank); return; }
      state.selected = null;
      state.targets = [];
      state.board.clearSelection();
      return;
    }
    selectPiece(file, rank);
  };

  // ---------------- 悔棋 / 和棋 / 认输 ----------------
  el.btnUndo.addEventListener("click", undoMove);
  async function undoMove() {
    if (state.busy || !state.game) return;
    state.busy = true;
    state.board.setBusy(true);
    try {
      const res = await API.undo(state.game.game_id);
      state.fen = res.fen;
      state.selected = null;
      state.targets = [];
      legalCache = {};
      state.board.clearSelection();
      state.board.clearTargets();
      state.board.setFen(res.fen);
      setStatus("已悔棋一步，" + yourTurnText());
      addEvent("悔棋一步");
    } catch (err) {
      setStatus("悔棋失败：" + err.message);
    } finally {
      state.busy = false;
      state.board.setBusy(false);
    }
  }

  el.btnDraw.addEventListener("click", drawOffer);
  async function drawOffer() {
    if (state.busy || state.gameOver || !state.game) return;
    if (!window.confirm("提出和棋？AI 会判断是否同意。")) return;
    state.busy = true;
    state.board.setBusy(true);
    try {
      const res = await API.drawOffer(state.game.game_id);
      const llm = res.llm_output || {};
      el.speech.textContent = llm.speech_text || (res.accepted ? "咱就和了吧。" : "还早呢，再下几手。");
      if (avatarAdapter) avatarAdapter.speak({ ssml: llm.speech_text, emotion_sdk: llm.emotion_tag });
      else setDhState("speaking");
      if (res.accepted) {
        state.gameOver = true;
        setStatus("对局结束：和棋！点击「开始对局」再来一盘");
        addEvent("🤝 和棋：AI 同意和棋");
        renderRecords();
      } else {
        setStatus("AI 不同意和棋，继续对局（" + (state.userSide === "black" ? "该你走棋·黑方" : "该你走棋·红方") + "）");
        addEvent("🤝 提出和棋，AI 暂不同意，继续下");
      }
    } catch (err) {
      setStatus("和棋请求失败：" + err.message);
    } finally {
      state.busy = false;
      state.board.setBusy(false);
    }
  }

  el.btnResign.addEventListener("click", resignGame);
  async function resignGame() {
    if (state.busy || state.gameOver || !state.game) return;
    if (!window.confirm("确定认输吗？认输后本局判负。")) return;
    state.busy = true;
    state.board.setBusy(true);
    try {
      const res = await API.resign(state.game.game_id);
      const llm = res.llm_output || {};
      el.speech.textContent = llm.speech_text || "没事老哥，胜负常有，咱再开一局！";
      if (avatarAdapter) avatarAdapter.speak({ ssml: llm.speech_text, emotion_sdk: llm.emotion_tag });
      else setDhState("speaking");
      state.gameOver = true;
      setStatus("对局结束：你认输了，AI 获胜。点击「开始对局」再来一盘");
      addEvent("🏳 认输：本局判负");
      renderRecords();
    } catch (err) {
      setStatus("认输失败：" + err.message);
    } finally {
      state.busy = false;
      state.board.setBusy(false);
    }
  }

  // ---------------- 棋谱管理 ----------------
  function resultText(r) { return { win: "胜", lose: "负", draw: "和" }[r] || "未结束"; }
  function resultCls(r) { return { win: "s-win", lose: "s-lose", draw: "s-draw" }[r] || "s-none"; }

  el.btnRefreshRecords.addEventListener("click", renderRecords);
  async function renderRecords() {
    if (!userId()) return;
    el.recordsList.className = "";
    el.recordsList.innerHTML = "<div class='muted'>加载中…</div>";
    try {
      const res = await API.listGames(userId());
      if (!res.games || res.games.length === 0) {
        el.recordsList.innerHTML = "<div class='muted'>暂无棋谱（下完一局后自动保存）</div>";
        return;
      }
      el.recordsList.innerHTML = "";
      res.games.forEach(function (g) {
        const row = document.createElement("div");
        row.className = "record-row";
        row.innerHTML =
          "<span class='rec-state " + resultCls(g.result) + "'>" + resultText(g.result) + "</span>" +
          "<span class='rec-star'>" + (g.starred ? "⭐" : "☆") + "</span>" +
          "<span class='rec-date'>" + (g.created_at || "").slice(0, 16) + "</span>" +
          "<span class='rec-moves'>" + g.move_count + " 手</span>" +
          "<button class='mini-btn' data-act='view'>查看</button>" +
          "<button class='mini-btn' data-act='star'>" + (g.starred ? "取消加精" : "加精") + "</button>" +
          "<button class='mini-btn danger-btn' data-act='del'>删除</button>";
        row.querySelector("[data-act=view]").addEventListener("click", function () { viewRecord(g.game_id); });
        row.querySelector("[data-act=star]").addEventListener("click", async function () {
          try { await API.starGame(g.game_id, !g.starred); renderRecords(); }
          catch (e) { alert("加精失败：" + e.message); }
        });
        row.querySelector("[data-act=del]").addEventListener("click", async function () {
          if (!window.confirm("删除这局棋谱？")) return;
          try { await API.deleteGame(g.game_id); renderRecords(); }
          catch (e) { alert("删除失败：" + e.message); }
        });
        el.recordsList.appendChild(row);
      });
    } catch (e) {
      el.recordsList.innerHTML = "<div class='muted'>棋谱加载失败：" + esc(e.message) + "</div>";
    }
  }

  // ---------------- 棋谱回放（整页对局室样式：棋盘 + 上一手/下一手 + 返回） ----------------
  let replay = null; // { board, steps, step }

  function buildReplaySteps(startFen, moves) {
    const steps = [{ fen: startFen, from: null, to: null, label: "开局", events: [] }];
    let f = startFen;
    for (const m of moves) {
      if (m.user_move && m.user_move.from && m.user_move.to) {
        f = applyLocalMove(f, m.user_move.from, m.user_move.to);
        steps.push({
          fen: f,
          from: m.user_move.from,
          to: m.user_move.to,
          label: (m.user_move.piece_name || m.user_move.piece) + " " + m.user_move.from + "→" + m.user_move.to,
          events: [],
        });
      }
      if (m.ai_move && m.ai_move.from_sq && m.ai_move.to_sq) {
        f = applyLocalMove(f, m.ai_move.from_sq, m.ai_move.to_sq);
        steps.push({
          fen: f,
          from: m.ai_move.from_sq,
          to: m.ai_move.to_sq,
          label: "AI " + m.ai_move.from_sq + "→" + m.ai_move.to_sq,
          events: m.events || [],
        });
      }
    }
    return steps;
  }

  function renderReplayStep() {
    const i = replay.step;
    const s = replay.steps[i];
    replay.board.setFen(s.fen);
    if (s.from && s.to) replay.board.markAiMove(s.from, s.to);
    el.replayInfo.textContent = "第 " + i + " 步 / 共 " + (replay.steps.length - 1) + " 步 · " + s.label;
    el.replayEvents.innerHTML = s.events && s.events.length
      ? s.events.map(function (e) { return "<div>· " + e + "</div>"; }).join("")
      : "<div class='muted'>（无事件）</div>";
    el.rpFirst.disabled = i === 0;
    el.rpPrev.disabled = i === 0;
    el.rpNext.disabled = i >= replay.steps.length - 1;
    el.rpLast.disabled = i >= replay.steps.length - 1;
  }

  async function viewRecord(gameId) {
    // 整页变成对局室样式的棋谱回放
    el.replayStatus.textContent = "棋谱回放";
    el.replayInfo.textContent = "加载中…";
    el.menuArea.classList.add("hidden");
    el.replayView.classList.remove("hidden");
    try {
      const res = await API.gameMoves(gameId);
      const startFen = res.start_fen || "rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR w - - 0 1";
      const steps = buildReplaySteps(startFen, res.moves || []);
      replay = { board: new ChessBoard(el.replayBoard), steps: steps, step: 0 };
      renderReplayStep();
    } catch (err) {
      el.replayInfo.textContent = "棋谱加载失败：" + err.message;
    }
  }

  function closeReplay() {
    el.replayView.classList.add("hidden");
    el.menuArea.classList.remove("hidden");
    showTab("records");
  }

  el.rpFirst.addEventListener("click", function () { if (replay) { replay.step = 0; renderReplayStep(); } });
  el.rpPrev.addEventListener("click", function () { if (replay && replay.step > 0) { replay.step--; renderReplayStep(); } });
  el.rpNext.addEventListener("click", function () { if (replay && replay.step < replay.steps.length - 1) { replay.step++; renderReplayStep(); } });
  el.rpLast.addEventListener("click", function () { if (replay) { replay.step = replay.steps.length - 1; renderReplayStep(); } });
  el.btnReplayBack.addEventListener("click", closeReplay);

  // ---------------- 通用设置 ----------------
  async function renderSettings() {
    const u = currentUser();
    el.accountName.textContent = u ? "当前账号：" + u.nickname : "-";
    loadChatPrefIntoSelect(u);
    try {
      const res = await API.listModels();
      el.modelList.innerHTML = "";
      res.models.forEach(function (m) {
        const d = document.createElement("div");
        d.className = "model-row";
        d.innerHTML = "<span>" + esc(m.label) + "</span>" + (m.current ? "<span class='tag'>当前</span>" : "");
        d.addEventListener("click", async function () {
          if (m.current) return;
          if (!window.confirm("切换模型为「" + m.label + "」？")) return;
          try { await API.switchModel(m.id); renderSettings(); }
          catch (e) { alert("切换失败：" + e.message); }
        });
        el.modelList.appendChild(d);
      });
    } catch (e) {
      el.modelList.innerHTML = "<div class='muted'>模型加载失败</div>";
    }
  }

  el.btnRename.addEventListener("click", renameAccount);
  async function renameAccount() {
    const nick = el.renameNickname.value.trim();
    if (!nick) return;
    try {
      const u = await API.renameUser(userId(), nick);
      saveUser(u);
      el.userLabel.textContent = u.nickname;
      el.renameNickname.value = "";
      renderSettings();
      alert("昵称已改为：" + u.nickname);
    } catch (e) { alert("改名失败：" + e.message); }
  }

  el.btnDeleteAccount.addEventListener("click", deleteAccount);
  async function deleteAccount() {
    if (!window.confirm("确定删除当前账号及其全部棋谱、记忆？此操作不可恢复！")) return;
    try {
      await API.deleteUser(userId());
      logout();
    } catch (e) { alert("删除失败：" + e.message); }
  }

  // 问题12：闲聊三档偏好
  el.btnSaveChatPref.addEventListener("click", saveChatPref);
  async function saveChatPref() {
    const pref = el.setChatPref.value;
    if (!["quiet", "balanced", "chatty"].includes(pref)) return;
    try {
      const u = await API.setChatPref(userId(), pref);
      saveUser(u);
      el.chatPrefMsg.textContent = "已保存：" + { quiet: "安静", balanced: "普通", chatty: "爱聊天" }[pref] + "（下次开局生效）";
      el.chatPrefMsg.className = "ok";
    } catch (e) {
      el.chatPrefMsg.textContent = "保存失败：" + e.message;
      el.chatPrefMsg.className = "muted";
    }
  }

  function loadChatPrefIntoSelect(u) {
    if (!el.setChatPref || !u) return;
    el.setChatPref.value = ["quiet", "balanced", "chatty"].includes(u.chat_pref) ? u.chat_pref : "balanced";
  }

  // ---------------- 模态 ----------------
  el.modalBack.addEventListener("click", function () { el.modalMask.classList.add("hidden"); });
  el.modalClose.addEventListener("click", function () { el.modalMask.classList.add("hidden"); });
  el.modalMask.addEventListener("click", function (e) {
    if (e.target === el.modalMask) el.modalMask.classList.add("hidden");
  });

  // ---------------- 启动 ----------------
  const saved = currentUser();
  if (saved && saved.user_id) {
    loginAs(saved);
  } else {
    showView("login");
    renderLoginUsers();
  }
})();
