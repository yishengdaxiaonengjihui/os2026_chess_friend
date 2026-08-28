// app.js —— 游戏编排：新开局、点击落子、AI 应手、棋友面板更新
"use strict";

(function () {
  const FILES = ["a", "b", "c", "d", "e", "f", "g", "h", "i"];

  const el = {
    board: document.getElementById("board"),
    status: document.getElementById("status"),
    winFill: document.getElementById("win-fill"),
    personality: document.getElementById("personality"),
    btnNew: document.getElementById("btn-new-game"),
    speech: document.getElementById("speech"),
    avatar: document.getElementById("avatar"),
    avatarName: document.getElementById("avatar-name"),
    emotionChip: document.getElementById("emotion-chip"),
    actionChip: document.getElementById("action-chip"),
    events: document.getElementById("events"),
    profile: document.getElementById("profile"),
    memories: document.getElementById("memories"),
    dhChip: document.getElementById("dh-chip"),
    avatarContainer: document.getElementById("avatar-container"),
    btnUndo: document.getElementById("btn-undo"),
    btnGames: document.getElementById("btn-games"),
    btnDraw: document.getElementById("btn-draw"),
    btnResign: document.getElementById("btn-resign"),
    gamesList: document.getElementById("games-list"),
    modalMask: document.getElementById("modal-mask"),
    modalTitle: document.getElementById("modal-title"),
    modalBody: document.getElementById("modal-body"),
    modalClose: document.getElementById("modal-close"),
  };

  const AVATARS = { laozhang: ["🧓", "老张"], xiaoya: ["👩", "小雅"] };

  const state = {
    board: new ChessBoard(el.board),
    game: null,
    fen: "",
    busy: false,
    gameOver: false,
    selected: null, // {file, rank}
    targets: [],
  };

  let legalCache = {}; // key: fen|color -> moves[]（同一局面重复选子不再请求后端）

  function userId() {
    let id = localStorage.getItem("cf_user_id");
    if (!id) {
      id = "u-" + Date.now().toString(36) + Math.random().toString(36).slice(2, 6);
      localStorage.setItem("cf_user_id", id);
    }
    return id;
  }

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

  // ---- 本地乐观落子用的 FEN 工具（仅用于即时渲染，权威 FEN 以后端为准）----
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
    for (const [k, v] of rows) {
      const d = document.createElement("div");
      d.innerHTML = "<b>" + k + "：</b>" + v;
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

  // ---- 数字人状态指示（第三阶段）----
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

  // 初始化数字人适配层（星云 SDK 优先，朗读降级）；每页只建一次
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
        avatarAdapter.onState = function (s) { setDhState(s); };
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

  function resetPanel() {
    el.speech.textContent = "你好呀老哥，咱开局杀一盘！";
    el.emotionChip.textContent = "情绪 --";
    el.actionChip.textContent = "动作 --";
    el.winFill.style.width = "50%";
    el.events.innerHTML = "<li class='muted'>暂无</li>";
    el.profile.innerHTML = "<span class='muted'>开局后逐步生成…</span>";
    renderMemories([]);
    setStatus("开局中…");
  }

  async function newGame() {
    state.busy = true;
    state.board.setBusy(true);
    try {
      const personality = el.personality.value;
      setAvatar(personality);
      resetPanel();
      const game = await API.newGame(userId(), personality);
      state.game = game;
      state.gameOver = false;
      state.fen = game.fen;
      state.selected = null;
      state.targets = [];
      legalCache = {};
      state.board.clearSelection();
      state.board.setFen(game.fen);
      setStatus("该你走棋（红方）");
      addEvent("新对局开始，你是红方，先行。");
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

  async function selectPiece(file, rank) {
    const piece = pieceAt(file, rank);
    if (!piece || !isRed(piece)) { state.board.clearSelection(); return; }
    state.selected = { file, rank };
    state.board.select(file, rank);
    try {
      const key = state.fen + "|red";
      let moves = legalCache[key];
      if (!moves) {
        const res = await API.legalMoves(state.fen, "red");
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
    // 用户落子 = 主动打断数字人讲话（barge-in）
    if (avatarAdapter) avatarAdapter.stop();
    const fromSq = fileToSq(state.selected.file, state.selected.rank);
    const toSq = fileToSq(file, rank);
    // 乐观落子：先本地渲染你的着法（滑动动画），不等后端
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

      // 棋友面板
      const llm = resp.llm_output;
      el.speech.textContent = llm.speech_text;
      if (resp.avatar_command) {
        if (avatarAdapter) avatarAdapter.speak(resp.avatar_command);
        else setDhState("speaking");
      } else {
        setDhState("off");
      }
      el.emotionChip.textContent = "情绪 " + llm.emotion_tag;
      el.actionChip.textContent = "动作 " + llm.action_tag;
      if (resp.ai_move && typeof resp.ai_move.win_probability === "number") {
        const userWin = (1 - resp.ai_move.win_probability) * 100;
        el.winFill.style.width = Math.max(2, Math.min(98, userWin)) + "%";
      }
      renderProfile(resp.profile);
      renderMemories(resp.long_term_memories);

      // 终局判断
      const hasMate = resp.events.some(function (e) { return e.indexOf("将死") >= 0; });
      const hasStale = resp.events.some(function (e) { return e.indexOf("困毙") >= 0; });
      if (hasMate) {
        state.gameOver = true;
        const userWon = resp.events.some(function (e) { return e.indexOf("玩家获胜") >= 0; });
        setStatus(userWon ? "对局结束：你将死老张，赢了！点击「新开对局」再来一盘" : "对局结束：你被将死了，老张险胜！点击「新开对局」再来一盘");
        refreshGamesList();
      } else if (hasStale) {
        state.gameOver = true;
        setStatus("对局结束：困毙，和棋。点击「新开对局」再来一盘");
        refreshGamesList();
      } else {
        setStatus("该你走棋（红方）");
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
    if (!state.game) { setStatus("请先新开对局"); return; }
    if (state.selected) {
      const isTarget = state.targets.some(function (t) { return t.file === file && t.rank === rank; });
      if (isTarget) { makeMove(file, rank); return; }
      const piece = pieceAt(file, rank);
      if (piece && isRed(piece)) { selectPiece(file, rank); return; }
      state.selected = null;
      state.targets = [];
      state.board.clearSelection();
      return;
    }
    selectPiece(file, rank);
  };

  el.btnNew.addEventListener("click", newGame);

  // ---- 人格切换：同步后端（新人格重新开始聊天记忆）----
  el.personality.addEventListener("change", function () {
    const p = el.personality.value;
    setAvatar(p);
    if (state.game) {
      API.setPersonality(state.game.game_id, p)
        .then(function () {
          addEvent("已切换棋友人格：" + (p === "xiaoya" ? "小雅（温柔陪练）" : "老张（豪爽棋友）"));
          setStatus("该你走棋（红方）");
          el.speech.textContent = p === "xiaoya" ? "你好呀，咱们慢慢下，不急～" : "好嘞，换我老张陪你杀一盘！";
        })
        .catch(function () { /* 切换失败静默 */ });
    }
  });

  // ---- 悔棋 ----
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
      setStatus("已悔棋一步，该你走棋（红方）");
      addEvent("悔棋一步");
    } catch (err) {
      setStatus("悔棋失败：" + err.message);
    } finally {
      state.busy = false;
      state.board.setBusy(false);
    }
  }

  // ---- 和棋（AI 自动判断）/ 认输 ----
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
        setStatus("对局结束：和棋！点击「新开对局」再来一盘");
        addEvent("🤝 和棋：AI 同意和棋");
        refreshGamesList();
      } else {
        setStatus("AI 不同意和棋，继续对局（该你走棋）");
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
      setStatus("对局结束：你认输了，老张获胜。点击「新开对局」再来一盘");
      addEvent("🏳 认输：本局判负");
      refreshGamesList();
    } catch (err) {
      setStatus("认输失败：" + err.message);
    } finally {
      state.busy = false;
      state.board.setBusy(false);
    }
  }

  // ---- 棋谱库 ----
  function resultText(r) {
    return { win: "胜", lose: "负", draw: "和" }[r] || "未结束";
  }
  async function refreshGamesList() {
    try {
      const res = await API.listGames(userId());
      if (!res.games || res.games.length === 0) {
        el.gamesList.textContent = "对局落子后自动保存";
        el.gamesList.className = "muted";
        return;
      }
      el.gamesList.className = "";
      el.gamesList.innerHTML = "";
      res.games.slice(0, 5).forEach(function (g) {
        const row = document.createElement("div");
        row.className = "game-mini";
        row.textContent = (g.created_at || "").slice(5, 16) + " · " + g.move_count + "手 · " + resultText(g.result);
        row.title = "点击查看完整棋谱";
        row.addEventListener("click", function () { openGamesLibrary(); });
        el.gamesList.appendChild(row);
      });
    } catch (e) { /* 静默 */ }
  }

  el.btnGames.addEventListener("click", openGamesLibrary);
  async function openGamesLibrary() {
    el.modalTitle.textContent = "棋谱库";
    el.modalBody.innerHTML = "<div class='muted'>加载中…</div>";
    el.modalMask.classList.remove("hidden");
    try {
      const res = await API.listGames(userId());
      if (!res.games || res.games.length === 0) {
        el.modalBody.innerHTML = "<div class='muted'>暂无棋谱（下完一局后自动保存）</div>";
        return;
      }
      el.modalBody.innerHTML = res.games.map(function (g) {
        return "<div class='game-row' data-gid='" + g.game_id + "'>" +
          (g.created_at || "").slice(0, 16) + " · " + g.move_count + "手 · " + resultText(g.result) +
          "</div>";
      }).join("");
      el.modalBody.querySelectorAll(".game-row").forEach(function (row) {
        row.addEventListener("click", function () { showGameMoves(row.getAttribute("data-gid")); });
      });
    } catch (err) {
      el.modalBody.innerHTML = "<div class='muted'>棋谱库加载失败：" + err.message + "</div>";
    }
  }

  async function showGameMoves(gameId) {
    el.modalTitle.textContent = "棋谱 " + gameId;
    el.modalBody.innerHTML = "<div class='muted'>加载中…</div>";
    try {
      const res = await API.gameMoves(gameId);
      if (!res.moves || res.moves.length === 0) {
        el.modalBody.innerHTML = "<div class='muted'>暂无着法记录</div>";
        return;
      }
      const rows = res.moves.map(function (m) {
        const um = m.user_move ? (m.user_move.piece_name || m.user_move.piece) + " " + m.user_move.from + "→" + m.user_move.to : "";
        const am = (m.ai_move && m.ai_move.from_sq) ? " · 黑 " + m.ai_move.from_sq + "→" + m.ai_move.to_sq : "";
        const ev = (m.events && m.events.length) ? "<span class='mv-events'>" + m.events.join("；") + "</span>" : "";
        return "<div class='move-row'>第" + m.move_index + "手 " + um + am + ev + "</div>";
      }).join("");
      el.modalBody.innerHTML = rows;
    } catch (err) {
      el.modalBody.innerHTML = "<div class='muted'>棋谱加载失败：" + err.message + "</div>";
    }
  }

  el.modalClose.addEventListener("click", function () { el.modalMask.classList.add("hidden"); });
  el.modalMask.addEventListener("click", function (e) {
    if (e.target === el.modalMask) el.modalMask.classList.add("hidden");
  });

  // 启动
  newGame();
  refreshGamesList();
})();
