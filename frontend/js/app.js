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

  // ---------------- 账号 / 会话 ----------------
  function currentUser() {
    try { return JSON.parse(localStorage.getItem("cf_user") || "null"); }
    catch (e) { return null; }
  }
  function saveUser(u) { localStorage.setItem("cf_user", JSON.stringify(u)); }
  function userId() { const u = currentUser(); return u ? u.user_id : ""; }

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
    state.board.setFen("");
    showSettingsForm();
  }

  // ---------------- 对局设置 / 开始对局 ----------------
  // 开始对局页 = 只有「对局设置 + 开始对局」；对局室整页独立，点开始对局才出现
  function showSettingsForm() {
    if (avatarAdapter) avatarAdapter.stop(); // 退出对局：清空语音队列
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
      state.board.setFen(game.fen);
      updateWinbarLabels();
      showGameRoom();
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
        initAvatarAdapter(true);
        connectDhWs(game.game_id);
      }
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

  function initAvatarAdapter(dhEnabled) {
    if (avatarAdapter || !dhEnabled || !window.AvatarAdapter) return;
    fetch("/api/info")
      .then(function (r) { return r.json(); })
      .then(function (info) {
        var x = info.xmov || {};
        if (!x.app_id) { setDhState("off"); return; }
        avatarAdapter = new AvatarAdapter({
          appId: x.app_id,
          appSecret: x.app_secret,
          gateway: x.gateway,
        });
        window.__avatarAdapter = avatarAdapter; // 调试/验证口：CDP 检查队列与情绪超时
        avatarAdapter.onState = function (s) { setDhState(s); };
        avatarAdapter.onEmotionReset = function () {
          // 问题11：情绪超时自动重置为平静
          if (el.emotionChip) el.emotionChip.textContent = "情绪 平静";
        };
        avatarAdapter.onReady = function () {
          el.avatar.style.display = "none";
          el.avatarContainer.classList.remove("hidden");
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

  async function makeMove(file, rank) {
    if (state.gameOver) return;
    state.busy = true;
    state.board.setBusy(true);
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
      if (llm) {
        el.speech.textContent = llm.speech_text;
        el.emotionChip.textContent = "情绪 " + llm.emotion_tag;
        el.actionChip.textContent = "动作 " + llm.action_tag;
      } else {
        // 问题1：言语触发决策后 AI 静默思索，只播思考动画
        el.speech.textContent = "…";
        el.emotionChip.textContent = "情绪 平静";
        el.actionChip.textContent = "动作 思考";
      }
      if (resp.avatar_command) {
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

      const hasMate = resp.events.some(function (e) { return e.indexOf("将死") >= 0; });
      const hasStale = resp.events.some(function (e) { return e.indexOf("困毙") >= 0; });
      if (hasMate) {
        state.gameOver = true;
        const userWon = resp.events.some(function (e) { return e.indexOf("玩家获胜") >= 0; });
        setStatus(userWon ? "对局结束：你将死 AI，赢了！点击「开始对局」再来一盘" : "对局结束：你被将死了，AI 获胜。点击「开始对局」再来一盘");
        renderRecords();
      } else if (hasStale) {
        state.gameOver = true;
        setStatus("对局结束：困毙，和棋。点击「开始对局」再来一盘");
        renderRecords();
      } else {
        setStatus(yourTurnText());
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
