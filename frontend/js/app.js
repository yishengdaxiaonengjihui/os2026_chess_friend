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
  };

  const AVATARS = { laozhang: ["🧓", "老张"], xiaoya: ["👩", "小雅"] };

  const state = {
    board: new ChessBoard(el.board),
    game: null,
    fen: "",
    busy: false,
    selected: null, // {file, rank}
    targets: [],
  };

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
      state.fen = game.fen;
      state.selected = null;
      state.targets = [];
      state.board.clearSelection();
      state.board.setFen(game.fen);
      setStatus("该你走棋（红方）");
      addEvent("新对局开始，你是红方，先行。");
      if (!game.digital_human_enabled) {
        el.avatar.style.opacity = "0.4";
        el.avatar.title = "数字人已降级（ENABLE_DIGITAL_HUMAN=false）";
      } else {
        el.avatar.style.opacity = "1";
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
      const res = await API.legalMoves(state.fen, "red");
      const targets = [];
      for (const m of res.moves) {
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
    state.busy = true;
    state.board.setBusy(true);
    setStatus("AI 思考中…");
    try {
      const fromSq = fileToSq(state.selected.file, state.selected.rank);
      const toSq = fileToSq(file, rank);
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
      if (hasMate) setStatus("对局结束：你被将死了，老张险胜！点击「新开对局」再来一盘");
      else if (hasStale) setStatus("对局结束：困毙，和棋。");
      else setStatus("该你走棋（红方）");
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
  el.personality.addEventListener("change", function () { setAvatar(el.personality.value); });

  // 启动
  newGame();
})();
