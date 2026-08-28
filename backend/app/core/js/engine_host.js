// engine_host.js — Node 宿主：加载 ryoi/xiangqi logic.js，通过 stdin/stdout 提供引擎指令。
// 用法: node engine_host.js <logic.js路径>   （指令经 stdin 传入 JSON）
"use strict";

const fs = require("fs");

const logicPath = process.argv[2];
if (!logicPath) {
  console.error("usage: node engine_host.js <logic.js>");
  process.exit(2);
}

// logic.js 末尾通过 window.logic 暴露接口，Node 下没有 window -> 挂到 globalThis
globalThis.window = globalThis;
eval(fs.readFileSync(logicPath, "utf8"));
const logic = globalThis.window.logic;
if (!logic) {
  console.error("engine load failed: no window.logic");
  process.exit(2);
}

// ---------- FEN <-> 引擎棋盘 ----------
// FEN 约定：大写=红方(下/rank9)，小写=黑方(上/rank0)；p/P=兵/卒，引擎内部用 s
function boardFromFen(fen) {
  const ranks = fen.split(" ")[0].split("/");
  if (ranks.length !== 10) throw new Error("bad fen: expected 10 ranks, got " + ranks.length);
  return ranks.map(function (rank) {
    const row = [];
    for (const ch of rank) {
      if (/[0-9]/.test(ch)) {
        const n = parseInt(ch, 10);
        for (let i = 0; i < n; i++) row.push(null);
      } else {
        const isRed = ch === ch.toUpperCase();
        let t = ch.toLowerCase();
        if (t === "p") t = "s";
        row.push({ t: t, c: isRed ? "red" : "black" });
      }
    }
    return row;
  });
}

function fenFromBoard(board) {
  return board
    .map(function (row) {
      let s = "";
      let empty = 0;
      for (const cell of row) {
        if (!cell) {
          empty++;
          continue;
        }
        if (empty > 0) {
          s += empty;
          empty = 0;
        }
        let t = cell.t.toLowerCase();
        if (t === "s") t = "p";
        s += cell.c === "red" ? t.toUpperCase() : t.toLowerCase();
      }
      if (empty > 0) s += empty;
      return s;
    })
    .join("/");
}

// 引擎坐标 [rank, file] <-> 本仓库坐标 "a0".."i9"（rank0=黑方在上）
function sqOf(rc) {
  return String.fromCharCode(97 + rc[1]) + rc[0];
}

function countLegalMoves(board, color) {
  let n = 0;
  for (let r = 0; r < 10; r++) {
    for (let c = 0; c < 9; c++) {
      const p = board[r][c];
      if (p && p.c === color) n += logic.getLegalMovesFiltered(board, r, c).length;
    }
  }
  return n;
}

function respond(obj) {
  console.log(JSON.stringify(obj));
}

function readInput() {
  const buf = fs.readFileSync(0, "utf8");
  return JSON.parse(buf);
}

let input;
try {
  input = readInput();
} catch (e) {
  respond({ ok: false, error: "bad stdin json: " + String(e) });
  process.exit(1);
}

try {
  if (input.action === "ping") {
    respond({ ok: true, pong: true });
  } else if (input.action === "position") {
    const board = boardFromFen(input.fen);
    const color = input.color === "black" ? "black" : "red";
    respond({
      ok: true,
      in_check: logic.isInCheck(board, color),
      is_checkmate: logic.isCheckmate(board, color),
      is_stalemate: logic.isStalemate(board, color),
      has_legal_moves: logic.hasAnyLegalMoves(board, color),
      legal_move_count: countLegalMoves(board, color),
      evaluate: logic.evaluateBoard(board, color),
    });
  } else if (input.action === "legal_moves") {
    const board = boardFromFen(input.fen);
    const color = input.color === "black" ? "black" : "red";
    const moves = [];
    for (let r = 0; r < 10; r++) {
      for (let c = 0; c < 9; c++) {
        const p = board[r][c];
        if (p && p.c === color) {
          const list = logic.getLegalMovesFiltered(board, r, c);
          for (const t of list) moves.push({ from: sqOf([r, c]), to: sqOf(t) });
        }
      }
    }
    respond({ ok: true, moves: moves });
  } else if (input.action === "ai_move") {
    const board = boardFromFen(input.fen);
    const color = input.color === "black" ? "black" : "red";
    const mv = logic.getAIMove(board, color, input.difficulty || 3, {
      useOpeningBook: !!input.useOpeningBook,
      moveNumber: typeof input.moveNumber === "number" ? input.moveNumber : undefined,
      timeMs: typeof input.timeMs === "number" ? input.timeMs : null,
    });
    if (!mv) {
      respond({ ok: true, move: null, reason: "no-legal-move", legal_move_count: countLegalMoves(board, color) });
      process.exit(0);
    }
    const nb = logic.applyMove(board, mv.from, mv.to);
    const opponent = color === "red" ? "black" : "red";
    respond({
      ok: true,
      move: { from: sqOf(mv.from), to: sqOf(mv.to), color: color },
      newFen: fenFromBoard(nb),
      score: logic.evaluateBoard(nb, color),
      opponent_in_check: logic.isInCheck(nb, opponent),
      opponent_checkmate: logic.isCheckmate(nb, opponent),
      opponent_stalemate: logic.isStalemate(nb, opponent),
      legal_move_count_before: countLegalMoves(board, color),
      legal_move_count_after: countLegalMoves(nb, opponent),
    });
  } else {
    respond({ ok: false, error: "unknown action: " + input.action });
  }
} catch (e) {
  respond({ ok: false, error: String((e && e.message) || e) });
}
