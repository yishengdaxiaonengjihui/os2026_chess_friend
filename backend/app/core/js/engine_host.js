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

// ---------- 问题8：引擎走法多样性 ----------
// 开局库：常见开局着法（加权随机）。moveNumber 1~5 对应黑方前 5 次应手（红方先行）。
// 坐标 [rank, file]：rank0=黑方底部，rank9=红方底部。file0=a .. file8=i。
// 注意：黑方行棋坐标按棋盘坐标书写（黑在 rank0 侧）。前 5 手用谱，之后纯引擎。
const OPENING_BOOK_MAX_MOVE = 5; // 棋谱只管前 5 手（5 个半回合），之后走引擎深搜
const OPENING_LINES = {
  red: [
    { w: 6, name: "中炮(炮二平五)", from: [7, 1], to: [7, 4] },
    { w: 4, name: "仙人指路(兵三进一)", from: [6, 2], to: [5, 2] },
    { w: 4, name: "飞相(相三进五)", from: [9, 2], to: [7, 4] },
    { w: 3, name: "跳马(马八进七)", from: [9, 1], to: [7, 0] },
    { w: 3, name: "上士(士四进五)", from: [9, 3], to: [8, 4] },
    { w: 2, name: "兵一进一(边兵)", from: [6, 0], to: [5, 0] },
  ],
  black: [
    // 修正（原坐标有误）：屏风马应走 h0->g2（马8进7 护中），原 b0->a2 是往边角跳
    { w: 5, name: "屏风马(马8进7)", from: [0, 7], to: [2, 6] },
    // 修正（原从马位起步永远不合法）：顺手炮是 h2->e2（炮8平5），原 [0,1]->[0,4] 错
    { w: 5, name: "顺手炮(炮8平5)", from: [2, 7], to: [2, 4] },
    // 修正：跳边马在 h 侧 h0->i1（马8进9），原 [0,1]->[1,0] 错
    { w: 3, name: "跳边马(马8进9)", from: [0, 7], to: [1, 8] },
    { w: 3, name: "上士(士4进5)", from: [0, 3], to: [1, 4] },
    { w: 2, name: "卒3进1", from: [3, 2], to: [4, 2] },
    { w: 2, name: "飞象(象3进5)", from: [0, 2], to: [2, 4] },
  ],
};

function weightedPick(candidates, rng) {
  const r = rng();
  const total = candidates.reduce((s, c) => s + c.w, 0);
  let acc = 0;
  for (const c of candidates) {
    acc += c.w;
    if (r < acc / total) return c;
  }
  return candidates[candidates.length - 1];
}

function legalMove(board, from, to) {
  return logic.getLegalMoves(board, from[0], from[1]).some(
    (t) => t[0] === to[0] && t[1] === to[1]
  );
}

// 开局加权随机：仅开局阶段（moveNumber<=OPENING_BOOK_MAX_MOVE）从候选开局库中按权重随机选合法着法。
function openingDiverseMove(board, color, moveNumber, rng) {
  if (moveNumber > OPENING_BOOK_MAX_MOVE) return null;
  const lines = color === "red" ? OPENING_LINES.red : OPENING_LINES.black;
  const legalCands = lines.filter((c) => legalMove(board, c.from, c.to));
  if (legalCands.length === 0) return null;
  const pick = weightedPick(legalCands, rng);
  return { from: pick.from, to: pick.to, opening: pick.name };
}

// 中局候选加权随机：枚举全部合法着法（用已暴露的 getLegalMovesFiltered），
// 对每个用 evaluateBoard 打分，取 topN 按权重选择，避免每次都是同一手棋。
function midgameDiverseMove(board, color, difficulty, rng) {
  const all = [];
  for (let r = 0; r < 10; r++) {
    for (let c = 0; c < 9; c++) {
      const p = board[r][c];
      if (p && p.c === color) {
        const list = logic.getLegalMovesFiltered(board, r, c);
        for (const t of list) {
          // 送吃保护：走完这一步若己方老帅受攻(被吃/被将军)，视为非法着法，
          // 与 legal_moves action 口径一致。防止被将死时返回"解不了将"的伪着法。
          const nb = logic.applyMove(board, [r, c], t);
          if (logic.isInCheck(nb, color)) continue;
          all.push({ from: [r, c], to: t });
        }
      }
    }
  }
  if (all.length === 0) return null;
  // 打分：走完后的局面评估（对当前走棋方）
  const scored = all.map((m) => ({
    m,
    s: logic.evaluateBoard(logic.applyMove(board, m.from, m.to), color),
  }));
  scored.sort((a, b) => b.s - a.s);
  // 候选窗口：随棋力增大而收窄（高棋力更少随机，避免太弱）
  const topN = Math.max(2, Math.min(6, Math.round(8 - difficulty * 0.8)));
  const candidates = scored.slice(0, topN);
  const best = candidates[0].s;
  // 权重：与最优分差越近权重越高（softmax 风格，温差=120）
  const temp = 120;
  const weights = candidates.map((c) => Math.exp((c.s - best) / temp));
  const total = weights.reduce((a, b) => a + b, 0);
  let r = rng() * total;
  let chosen = candidates[0];
  for (let i = 0; i < candidates.length; i++) {
    r -= weights[i];
    if (r <= 0) { chosen = candidates[i]; break; }
  }
  return { from: chosen.m.from, to: chosen.m.to, score: chosen.s, candidates: topN };
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
          for (const t of list) {
            // 送吃保护：走完这一步若己方老帅受攻（被吃/被将军），视为非法着法
            const nb = logic.applyMove(board, [r, c], t);
            if (!logic.isInCheck(nb, color)) {
              moves.push({ from: sqOf([r, c]), to: sqOf(t) });
            }
          }
        }
      }
    }
    respond({ ok: true, moves: moves });
  } else if (input.action === "ai_move") {
    const board = boardFromFen(input.fen);
    const color = input.color === "black" ? "black" : "red";
    const diversity = !!input.diversity;
    const diversityProb = typeof input.diversityProb === "number" ? input.diversityProb : 0.45;
    let mv = null;

    // 问题8：开局库加权随机（仅开局阶段且开启多样性，前 OPENING_BOOK_MAX_MOVE 手）
    if (diversity && input.diversityOpening !== false &&
        typeof input.moveNumber === "number" && input.moveNumber <= OPENING_BOOK_MAX_MOVE) {
      mv = openingDiverseMove(board, color, input.moveNumber, Math.random);
    }

    // 问题8：中局候选加权随机（以概率走「加权候选」而非「深搜最优」）
    if (!mv && diversity && Math.random() < diversityProb) {
      mv = midgameDiverseMove(board, color, input.difficulty || 3, Math.random);
    }

    // 兜底：正常引擎搜索（含原开局库）
    if (!mv) {
      mv = logic.getAIMove(board, color, input.difficulty || 3, {
        useOpeningBook: !!input.useOpeningBook,
        moveNumber: typeof input.moveNumber === "number" ? input.moveNumber : undefined,
        timeMs: typeof input.timeMs === "number" ? input.timeMs : null,
      });
    }
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
