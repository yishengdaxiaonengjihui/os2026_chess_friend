// api.js —— 后端 API 客户端（同源相对路径；可用 window.API_BASE 覆盖）
"use strict";

(function (global) {
  const BASE = global.API_BASE || "";

  async function request(path, options) {
    const resp = await fetch(BASE + path, options);
    if (!resp.ok) {
      let detail = resp.status + " " + resp.statusText;
      try {
        const body = await resp.json();
        if (body.detail) detail = body.detail;
      } catch (e) { /* 非 JSON 错误体 */ }
      throw new Error(detail);
    }
    return resp.json();
  }

  function jsonBody(data, method) {
    return {
      method: method || "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    };
  }

  const API = {
    async health() {
      return request("/health");
    },
    async newGame(userId, personality, side, strength) {
      return request("/api/games", jsonBody({ user_id: userId, personality: personality, side: side, strength: strength }));
    },
    // ---- 多用户 ----
    async createUser(nickname) {
      return request("/api/users", jsonBody({ nickname: nickname }));
    },
    async listUsers() {
      return request("/api/users");
    },
    async loginUser(userId) {
      return request("/api/users/login", jsonBody({ user_id: userId }));
    },
    async renameUser(userId, nickname) {
      return request("/api/users/" + encodeURIComponent(userId), jsonBody({ nickname: nickname }, "PATCH"));
    },
    async deleteUser(userId) {
      return request("/api/users/" + encodeURIComponent(userId), { method: "DELETE" });
    },
    async setChatPref(userId, chatPref) {
      return request("/api/users/" + encodeURIComponent(userId) + "/chat-pref", jsonBody({ chat_pref: chatPref }, "PATCH"));
    },
    // ---- 棋谱管理 ----
    async starGame(gameId, starred) {
      return request("/api/games/" + gameId + "/star", jsonBody({ starred: starred }));
    },
    async deleteGame(gameId) {
      return request("/api/games/" + gameId, { method: "DELETE" });
    },
    // ---- 模型管理 ----
    async listModels() {
      return request("/api/models");
    },
    async switchModel(model) {
      return request("/api/models", jsonBody({ model: model }));
    },
    async legalMoves(fen, color) {
      const q = new URLSearchParams({ fen: fen, color: color });
      return request("/api/moves/legal?" + q.toString());
    },
    async makeMove(gameId, userId, fromSq, toSq) {
      return request("/api/moves", jsonBody({ game_id: gameId, user_id: userId, from_sq: fromSq, to_sq: toSq }));
    },
    async setPersonality(gameId, personality) {
      return request("/api/games/" + gameId + "/personality", jsonBody({ personality: personality }));
    },
    async undo(gameId) {
      return request("/api/games/" + gameId + "/undo", { method: "POST" });
    },
    async listGames(userId) {
      return request("/api/games?user_id=" + encodeURIComponent(userId));
    },
    async gameMoves(gameId) {
      return request("/api/games/" + gameId + "/moves");
    },
    async drawOffer(gameId) {
      return request("/api/games/" + gameId + "/draw", { method: "POST" });
    },
    async resign(gameId) {
      return request("/api/games/" + gameId + "/resign", { method: "POST" });
    },
  };

  global.API = API;
})(window);
