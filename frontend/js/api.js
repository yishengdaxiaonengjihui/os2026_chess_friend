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

  function jsonBody(data) {
    return {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    };
  }

  const API = {
    async health() {
      return request("/health");
    },
    async newGame(userId, personality) {
      return request("/api/games", jsonBody({ user_id: userId, personality: personality }));
    },
    async legalMoves(fen, color) {
      const q = new URLSearchParams({ fen: fen, color: color });
      return request("/api/moves/legal?" + q.toString());
    },
    async makeMove(gameId, userId, fromSq, toSq) {
      return request("/api/moves", jsonBody({ game_id: gameId, user_id: userId, from_sq: fromSq, to_sq: toSq }));
    },
  };

  global.API = API;
})(window);
