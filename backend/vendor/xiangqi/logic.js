
// logic.js — Stronger AI v2 (ID-AB, Quiescence, TT, Killers, History, LMR, NMP)

let winLossStats = { redWins: 0, blackWins: 0 };

function initialBoard() {
  const board = Array.from({ length: 10 }, () => Array(9).fill(null));

  const redBackRow = ["r", "n", "b", "a", "k", "a", "b", "n", "r"].map(t => ({ t, c: "red" }));
  const blackBackRow = ["r", "n", "b", "a", "k", "a", "b", "n", "r"].map(t => ({ t, c: "black" }));

  board[0] = blackBackRow;
  board[2][1] = board[2][7] = { t: "c", c: "black" };
  [0, 2, 4, 6, 8].forEach(c => board[3][c] = { t: "s", c: "black" });

  board[9] = redBackRow;
  board[7][1] = board[7][7] = { t: "c", c: "red" };
  [0, 2, 4, 6, 8].forEach(c => board[6][c] = { t: "s", c: "red" });

  return board;
}

function applyMove(board, from, to) {
  const newBoard = board.map(row => row.slice());
  newBoard[to[0]][to[1]] = newBoard[from[0]][from[1]];
  newBoard[from[0]][from[1]] = null;
  return newBoard;
}

function inBounds(r, c) {
  return r >= 0 && r < 10 && c >= 0 && c < 9;
}

function clearPath(board, r1, r2, c) {
  const min = Math.min(r1, r2);
  const max = Math.max(r1, r2);
  for (let i = min + 1; i < max; i++) {
    if (board[i][c]) return false;
  }
  return true;
}

function getLegalMovesFiltered(board, r, c) {
  const piece = board[r][c];
  if (!piece) return [];
  const { t, c: color } = piece;
  const enemy = color === "red" ? "black" : "red";
  const moves = [];

  switch (t) {
    case "k": {
      const range = color === "red" ? [7, 9] : [0, 2];
      [[1, 0], [-1, 0], [0, 1], [0, -1]].forEach(([dr, dc]) => {
        const nr = r + dr, nc = c + dc;
        if (nr >= range[0] && nr <= range[1] && nc >= 3 && nc <= 5) {
          const target = board[nr][nc];
          if (!target || target.c === enemy) moves.push([nr, nc]);
        }
      });
      // flying general (face-to-face)
      for (let i = r + 1; i < 10; i++) {
        const p = board[i][c];
        if (p) {
          if (p.t === "k" && p.c !== color && clearPath(board, r, i, c)) moves.push([i, c]);
          break;
        }
      }
      for (let i = r - 1; i >= 0; i--) {
        const p = board[i][c];
        if (p) {
          if (p.t === "k" && p.c !== color && clearPath(board, i, r, c)) moves.push([i, c]);
          break;
        }
      }
      break;
    }
    case "a": {
      const range = color === "red" ? [7, 9] : [0, 2];
      [[1, 1], [-1, 1], [1, -1], [-1, -1]].forEach(([dr, dc]) => {
        const nr = r + dr, nc = c + dc;
        if (nr >= range[0] && nr <= range[1] && nc >= 3 && nc <= 5) {
          const target = board[nr][nc];
          if (!target || target.c === enemy) moves.push([nr, nc]);
        }
      });
      break;
    }
    case "b": {
      [[2, 2], [2, -2], [-2, 2], [-2, -2]].forEach(([dr, dc]) => {
        const mr = r + dr / 2, mc = c + dc / 2;
        const nr = r + dr, nc = c + dc;
        if (inBounds(nr, nc) && board[mr][mc] == null) {
          if ((color === "red" && nr >= 5) || (color === "black" && nr <= 4)) {
            const target = board[nr][nc];
            if (!target || target.c === enemy) moves.push([nr, nc]);
          }
        }
      });
      break;
    }
    case "n": {
      const knightMoves = [
        [-2, -1, -1, 0], [-2, 1, -1, 0],
        [-1, -2, 0, -1], [-1, 2, 0, 1],
        [1, -2, 0, -1], [1, 2, 0, 1],
        [2, -1, 1, 0], [2, 1, 1, 0]
      ];
      knightMoves.forEach(([dr, dc, br, bc]) => {
        const brd = r + br, bcd = c + bc;
        const nr = r + dr, nc = c + dc;
        if (inBounds(nr, nc) && board[brd][bcd] == null) {
          const target = board[nr][nc];
          if (!target || target.c === enemy) moves.push([nr, nc]);
        }
      });
      break;
    }
    case "r": {
      [[1, 0], [-1, 0], [0, 1], [0, -1]].forEach(([dr, dc]) => {
        for (let i = 1; i < 10; i++) {
          const nr = r + dr * i, nc = c + dc * i;
          if (!inBounds(nr, nc)) break;
          const target = board[nr][nc];
          if (!target) moves.push([nr, nc]);
          else {
            if (target.c === enemy) moves.push([nr, nc]);
            break;
          }
        }
      });
      break;
    }
    case "c": {
      [[1, 0], [-1, 0], [0, 1], [0, -1]].forEach(([dr, dc]) => {
        let screen = false;
        for (let i = 1; i < 10; i++) {
          const nr = r + dr * i, nc = c + dc * i;
          if (!inBounds(nr, nc)) break;
          const target = board[nr][nc];
          if (!screen) {
            if (!target) moves.push([nr, nc]);
            else screen = true;
          } else {
            if (target) {
              if (target.c === enemy) moves.push([nr, nc]);
              break;
            }
          }
        }
      });
      break;
    }
    case "s": {
      const forward = color === "red" ? -1 : 1;
      const nr = r + forward;
      if (inBounds(nr, c) && (!board[nr][c] || board[nr][c].c === enemy)) {
        moves.push([nr, c]);
      }
      if ((color === "red" && r <= 4) || (color === "black" && r >= 5)) {
        [[0, 1], [0, -1]].forEach(([dr, dc]) => {
          const nc = c + dc;
          if (inBounds(r, nc) && (!board[r][nc] || board[r][nc].c === enemy)) {
            moves.push([r, nc]);
          }
        });
      }
      break;
    }
  }
  return moves;
}

const chineseChars = {
  r: "車", n: "馬", b: "相", a: "仕", k: "帥", c: "炮", s: "兵",
  R: "車", N: "馬", B: "象", A: "士", K: "將", C: "砲", S: "卒"
};

function findKing(board, color) {
  for (let r = 0; r < 10; r++) {
    for (let c = 0; c < 9; c++) {
      const piece = board[r][c];
      if (piece && piece.t === "k" && piece.c === color) {
        return [r, c];
      }
    }
  }
  return null;
}

function isInCheck(board, color) {
  const enemy = color === "red" ? "black" : "red";
  const kingPos = findKing(board, color);
  if (!kingPos) return false;

  for (let r = 0; r < 10; r++) {
    for (let c = 0; c < 9; c++) {
      const piece = board[r][c];
      if (piece && piece.c === enemy) {
        const moves = getLegalMovesFiltered(board, r, c);
        if (moves.some(([mr, mc]) => mr === kingPos[0] && mc === kingPos[1])) {
          return true;
        }
      }
    }
  }
  return false;
}

function isCheckmate(board, color) {
  for (let r = 0; r < 10; r++) {
    for (let c = 0; c < 9; c++) {
      const piece = board[r][c];
      if (piece && piece.c === color) {
        const moves = getLegalMovesFiltered(board, r, c);
        for (const move of moves) {
          const simulated = applyMove(board, [r, c], move);
          if (!isInCheck(simulated, color)) return false;
        }
      }
    }
  }
  return true;
}

// --- Evaluation ---
const BASE_VALUES = { k: 10000, a: 20, b: 20, n: 45, r: 100, c: 60, s: 12 };

// Simple piece-square tables (from Red's perspective)
const PST = {
  s: [
    [0,0,0, 0,0,0, 0,0,0],
    [0,0,0, 1,1,1, 0,0,0],
    [0,1,1, 2,2,2, 1,1,0],
    [0,1,2, 3,4,3, 2,1,0],
    [0,0,1, 2,3,2, 1,0,0],
    [0,0,0, 1,2,1, 0,0,0],
    [0,0,0, 0,1,0, 0,0,0],
    [0,0,0, 0,0,0, 0,0,0],
    [0,0,0, 0,0,0, 0,0,0],
    [0,0,0, 0,0,0, 0,0,0],
  ],
  r: [
    [0,1,1, 1,1,1, 1,1,0],
    [0,2,2, 2,2,2, 2,2,0],
    [0,2,3, 3,3,3, 3,2,0],
    [0,2,3, 4,5,4, 3,2,0],
    [0,2,3, 4,6,4, 3,2,0],
    [0,2,3, 4,5,4, 3,2,0],
    [0,2,3, 3,4,3, 3,2,0],
    [0,2,2, 2,2,2, 2,2,0],
    [0,1,1, 1,1,1, 1,1,0],
    [0,0,0, 0,0,0, 0,0,0],
  ],
  c: [
    [0,1,1, 1,1,1, 1,1,0],
    [0,2,2, 2,2,2, 2,2,0],
    [0,2,3, 3,3,3, 3,2,0],
    [0,2,3, 4,4,4, 3,2,0],
    [0,2,3, 4,5,4, 3,2,0],
    [0,2,3, 4,4,4, 3,2,0],
    [0,2,3, 3,3,3, 3,2,0],
    [0,2,2, 2,2,2, 2,2,0],
    [0,1,1, 1,1,1, 1,1,0],
    [0,0,0, 0,0,0, 0,0,0],
  ],
  n: [
    [0,1,2, 2,2,2, 2,1,0],
    [0,2,3, 3,3,3, 3,2,0],
    [0,3,4, 5,5,5, 4,3,0],
    [0,3,5, 6,7,6, 5,3,0],
    [0,2,4, 5,6,5, 4,2,0],
    [0,2,3, 4,5,4, 3,2,0],
    [0,1,2, 3,4,3, 2,1,0],
    [0,1,1, 2,2,2, 1,1,0],
    [0,0,1,  1,1,1, 1,0,0],
    [0,0,0, 0,0,0, 0,0,0],
  ],
  b: [
    [0,0,0, 0,0,0, 0,0,0],
    [0,0,1, 1,1,1, 1,0,0],
    [0,0,1, 2,2,2, 1,0,0],
    [0,0,2, 3,3,3, 2,0,0],
    [0,0,2, 3,4,3, 2,0,0],
    [0,0,2, 3,3,3, 2,0,0],
    [0,0,1, 2,2,2, 1,0,0],
    [0,0,1, 1,1,1, 1,0,0],
    [0,0,0, 0,0,0, 0,0,0],
    [0,0,0, 0,0,0, 0,0,0],
  ],
  a: [
    [0,0,0, 0,1,0, 0,0,0],
    [0,0,0, 1,2,1, 0,0,0],
    [0,0,0, 1,3,1, 0,0,0],
    [0,0,0,  1,2,1, 0,0,0],
    [0,0,0, 0,1,0, 0,0,0],
    [0,0,0, 0,1,0, 0,0,0],
    [0,0,0, 1,2,1, 0,0,0],
    [0,0,0, 1,3,1, 0,0,0],
    [0,0,0, 1,2,1, 0,0,0],
    [0,0,0, 0,1,0, 0,0,0],
  ],
  k: [
    [0,0,0, 0,1,0, 0,0,0],
    [0,0,0, 0,2,0, 0,0,0],
    [0,0,0, 0,2,0, 0,0,0],
    [0,0,0, 0,1,0, 0,0,0],
    [0,0,0, 0,0,0, 0,0,0],
    [0,0,0, 0,0,0, 0,0,0],
    [0,0,0, 0,1,0, 0,0,0],
    [0,0,0, 0,2,0,  0,0,0],
    [0,0,0, 0,2,0, 0,0,0],
    [0,0,0, 0,1,0, 0,0,0],
  ],
};

function pstScore(t, color, r, c) {
  const table = PST[t];
  if (!table) return 0;
  const rr = color === "red" ? r : 9 - r;
  const v = table[rr][c] || 0;
  return v;
}

function evaluateBoard(board, color) {
  let score = 0;
  for (let r=0; r<10; r++) {
    for (let c=0; c<9; c++) {
      const p = board[r][c];
      if (!p) continue;
      const sign = (p.c === color) ? 1 : -1;
      const t = p.t.toLowerCase();
      const mat = BASE_VALUES[t] || 0;
      let s = mat;
      s += pstScore(t, p.c, r, c);

      if (t === "s") {
        if (p.c === "red" && r <= 4) s += 6;
        if (p.c === "black" && r >= 5) s += 6;
      }

      if (t === "r" || t === "c") {
        const lm = getLegalMovesFiltered(board, r, c).length;
        s += Math.min(10, lm);
      }

      score += sign * s;
    }
  }

  const meInCheck = isInCheck(board, color);
  const themInCheck = isInCheck(board, color === "red" ? "black" : "red");
  if (meInCheck) score -= 30;
  if (themInCheck) score += 30;

  return score;
}

// SAFE legal moves (no self-check)
function getLegalMoves(board, r, c) {
  const piece = board[r][c];
  if (!piece) return [];
  const color = piece.c;
  const pseudo = getLegalMovesFiltered(board, r, c);
  return pseudo.filter(([mr, mc]) => {
    const simulated = applyMove(board, [r, c], [mr, mc]);
    return !isInCheck(simulated, color);
  });
}

function allLegalMoves(board, color) {
  const mv = [];
  for (let r=0; r<10; r++) for (let c=0; c<9; c++) {
    const p = board[r][c];
    if (p && p.c === color) {
      const moves = getLegalMoves(board, r, c);
      for (const m of moves) mv.push({ from:[r,c], to:m, piece: p });
    }
  }
  return mv;
}

function captureValueAt(board, to) {
  const p = board[to[0]][to[1]];
  if (!p) return 0;
  return BASE_VALUES[p.t.toLowerCase()] || 0;
}

function moveKey(m){
  return `${m.from[0]}${m.from[1]}-${m.to[0]}${m.to[1]}`;
}

// --- Opening book (kept small) ---
const BOOK = {
  start_red: { from: [7,1], to: [7,4] },           // 中炮
  start_black_reply: { from: [0,1], to: [2,2] }    // 屏風馬
};

function isInitialLike(board) {
  const start = initialBoard();
  for (let r=0;r<10;r++) for (let c=0;c<9;c++) {
    const a = start[r][c], b = board[r][c];
    if (!a && !b) continue;
    if (!a || !b) return false;
    if (a.t !== b.t || a.c !== b.c) return false;
  }
  return true;
}

function bookMove(board, color, moveNumber) {
  try {
    if (moveNumber === 0 && color === 'red' && isInitialLike(board)) {
      const mv = BOOK.start_red;
      const legal = getLegalMoves(board, mv.from[0], mv.from[1]).some(([r,c])=> r===mv.to[0] && c===mv.to[1]);
      return legal ? { from: mv.from, to: mv.to } : null;
    }
    if (moveNumber === 1 && color === 'black') {
      const mv = BOOK.start_black_reply;
      const legal = getLegalMoves(board, mv.from[0], mv.from[1]).some(([r,c])=> r===mv.to[0] && c===mv.to[1]);
      return legal ? { from: mv.from, to: mv.to } : null;
    }
  } catch (e) {}
  return null;
}

// ============================= Search enhancements =============================
let NODE_COUNT = 0;
let DEADLINE = 0; // epoch ms
let STOPPED = false;

const DEFAULT_NODE_SLICE = 128;

// Transposition table with bound types
// entry: { depth, score, flag: 0=exact, -1=alpha, 1=beta, bestKey }
const TT = new Map();

// Killer moves (two per ply)
const MAX_PLY = 64;
const killers = Array.from({length: MAX_PLY}, () => [null, null]);

// History heuristic: Map moveKey -> score
const history = new Map();

function boardKey(board, sideToMove) {
  let s = sideToMove === "red" ? "r|" : "b|";
  for (let r = 0; r < 10; r++) {
    for (let c = 0; c < 9; c++) {
      const p = board[r][c];
      if (!p) { s += "."; continue; }
      const ch = p.c === "red" ? p.t.toLowerCase() : p.t.toUpperCase();
      s += ch;
    }
    s += "|";
  }
  return s;
}

// Quiescence: captures only
function quiescence(board, color, alpha, beta, ply=0) {
  if ((NODE_COUNT & 1023) === 0) {
    if (Date.now() > DEADLINE) { STOPPED = true; return alpha; }
  }
  NODE_COUNT++;
  const stand = evaluateBoard(board, color);
  if (stand >= beta) return beta;
  if (alpha < stand) alpha = stand;

  const enemy = color === "red" ? "black" : "red";
  const moves = allLegalMoves(board, color)
    .filter(m => captureValueAt(board, m.to) > 0)
    .sort((a,b)=> (captureValueAt(board,b.to) - captureValueAt(board,a.to)));

  for (const m of moves) {
    const nb = applyMove(board, m.from, m.to);
    const score = -quiescence(nb, enemy, -beta, -alpha, ply+1);
    if (STOPPED) return alpha;
    if (score >= beta) return beta;
    if (score > alpha) alpha = score;
  }
  return alpha;
}

function orderMoves(board, color, moves, ttBestKey, ply){
  const enemy = color === "red" ? "black" : "red";
  const k1 = killers[ply]?.[0];
  const k2 = killers[ply]?.[1];
  const arr = moves.map(m => {
    const key = moveKey(m);
    let score = 0;
    // TT move first
    if (ttBestKey && key === ttBestKey) score += 10_000;
    // Captures by MVV
    const cap = captureValueAt(board, m.to);
    if (cap) score += 300 + cap * 10;
    // Killer moves
    if (k1 && key === k1) score += 250;
    if (k2 && key === k2) score += 200;
    // History heuristic
    score += (history.get(key) || 0);
    // Slight central push
    const [tr, tc] = m.to;
    score += -Math.abs(tc - 4) - Math.abs(tr - 4.5);
    // Check giving bonus (small)
    const nb = applyMove(board, m.from, m.to);
    if (isInCheck(nb, enemy)) score += 40;
    return { m, score };
  });
  arr.sort((a,b)=> b.score - a.score);
  return arr.map(x=>x.m);
}

// Null move pruning (safe-ish). Avoid when in check or shallow.
function nullMovePrune(board, color, depth, alpha, beta){
  if (depth < 3) return null;
  if (isInCheck(board, color)) return null;
  // Make a null move: side to move passes
  const enemy = color === "red" ? "black" : "red";
  const R = 2 + (depth >= 5 ? 1 : 0); // reduction
  const score = -search(board, enemy, depth - 1 - R, -beta, -beta+1, 0, 0); // minimal window
  return score;
}

// Core alpha-beta with LMR, killers, history, TT, time control
function search(board, color, depth, alpha, beta, ply, allowNull=1) {
  if ((NODE_COUNT & (DEFAULT_NODE_SLICE-1)) === 0) {
    if (Date.now() > DEADLINE) { STOPPED = true; return alpha; }
  }
  NODE_COUNT++;

  const key = boardKey(board, color);
  const tte = TT.get(key);
  if (tte && tte.depth >= depth) {
    if (tte.flag === 0) return tte.score;
    if (tte.flag === -1 && tte.score <= alpha) return alpha;
    if (tte.flag === 1 && tte.score >= beta) return beta;
  }

  if (depth === 0) {
    const q = quiescence(board, color, alpha, beta, ply);
    return q;
  }

  // Null-move pruning
  if (allowNull && depth >= 3) {
    const nms = nullMovePrune(board, color, depth, alpha, beta);
    if (nms !== null && nms >= beta) {
      return nms;
    }
  }

  const movesRaw = allLegalMoves(board, color);
  if (movesRaw.length === 0) {
    if (isInCheck(board, color)) return -99999 + (5 - depth);
    return 0;
  }

  const ttBestKey = tte?.bestKey || null;
  const moves = orderMoves(board, color, movesRaw, ttBestKey, ply);
  const enemy = color === "red" ? "black" : "red";

  let bestScore = -Infinity;
  let bestMove = moves[0];
  let nodeType = -1; // assume alpha node

  for (let i=0;i<moves.length;i++){
    const m = moves[i];
    const nb = applyMove(board, m.from, m.to);

    // Late Move Reductions: reduce depth for quiet, late moves
    let newDepth = depth - 1;
    const isCapture = !!captureValueAt(board, m.to);
    const givesCheck = isInCheck(nb, enemy);
    if (depth >= 3 && i >= 4 && !isCapture && !givesCheck) {
      newDepth = depth - 2; // reduce one extra ply
    }

    let score = -search(nb, enemy, newDepth, -beta, -alpha, ply+1, 1);
    if (STOPPED) return alpha;

    // Principal variation search (re-search if improved after reduction)
    if (newDepth !== depth-1 && score > alpha) {
      score = -search(nb, enemy, depth-1, -beta, -alpha, ply+1, 1);
      if (STOPPED) return alpha;
    }

    if (score > bestScore) {
      bestScore = score;
      bestMove = m;
      if (score > alpha) {
        alpha = score;
        nodeType = 0; // exact
        // store killer on a fail-high that isn't a capture
        if (!isCapture) {
          const mk = moveKey(m);
          const ks = killers[ply];
          if (ks[0] !== mk) { ks[1] = ks[0]; ks[0] = mk; }
          // bump history
          history.set(mk, (history.get(mk) || 0) + depth*depth);
        }
      }
      if (alpha >= beta) {
        nodeType = 1; // beta
        break;
      }
    }
  }

  // Save to TT
  const bestKey = bestMove ? moveKey(bestMove) : null;
  TT.set(key, { depth, score: bestScore, flag: nodeType, bestKey });

  return bestScore;
}

// Iterative deepening with aspiration windows
function searchRoot(board, color, maxDepth, timeMs){
  const enemy = color === "red" ? "black" : "red";
  const movesRaw = allLegalMoves(board, color);
  if (movesRaw.length === 0) return null;

  // Initial ordering without TT
  let ordered = orderMoves(board, color, movesRaw, null, 0);

  let bestMove = ordered[0];
  let bestScore = -Infinity;
  let alpha = -Infinity, beta = Infinity;

  let prevScore = 0;

  for (let depth=1; depth<=maxDepth; depth++){
    // Aspiration window around previous score
    let window = 30; // centipawn-ish
    alpha = (depth === 1) ? -Infinity : prevScore - window;
    beta  = (depth === 1) ?  Infinity : prevScore + window;

    let localBest = ordered[0];
    let localBestScore = -Infinity;

    for (let attempt=0; attempt<3; attempt++){
      for (let i=0;i<ordered.length;i++){
        const m = ordered[i];
        const nb = applyMove(board, m.from, m.to);
        const sc = -search(nb, enemy, depth-1, -beta, -alpha, 1, 1);
        if (STOPPED) break;
        if (sc > localBestScore) {
          localBestScore = sc;
          localBest = m;
        }
        if (sc > alpha) alpha = sc;
      }
      if (STOPPED) break;
      // if failed low/high, widen window and try again
      if (localBestScore <= alpha + 1 && attempt === 0 && depth > 1) {
        alpha = -Infinity; beta = Infinity; // fully widen
      } else if (localBestScore >= beta - 1 && attempt === 0 && depth > 1) {
        alpha = -Infinity; beta = Infinity;
      } else {
        break;
      }
    }

    if (STOPPED) break;

    prevScore = localBestScore;
    bestMove = localBest;
    bestScore = localBestScore;

    // Re-order next iteration with PV first
    const pvKey = moveKey(bestMove);
    ordered.sort((a,b)=> (moveKey(b)===pvKey) - (moveKey(a)===pvKey));
  }

  return bestMove || null;
}

// --- Legacy simple policy (kept for low difficulty and as fallback) ---
function simpleScoreMove(board, color, move) {
  const after = applyMove(board, move.from, move.to);
  const base = evaluateBoard(after, color);
  const cap = captureValueAt(board, move.to) * 0.2;
  const safe = isInCheck(after, color) ? -50 : 0;
  return base + cap + safe;
}

// Difficulty mapping and time budgets
function mapSkillToDifficulty(skill) {
  return Math.max(1, Math.min(6, Number(skill || 3)));
}
function mapSkillToDepth(skill) {
  return ({1:3,2:4,3:6,4:7,5:8,6:9})[skill] || 6;
}
function timeBudgetMsForSkill(skill){
  return ({1:250,2:350,3:500,4:700,5:900,6:1200})[skill] || 600;
}

// Main AI selection with time control
function getAIMove(board, color, difficulty = 1, options) {
  const useOpeningBook = options && options.useOpeningBook;
  const moveNumber = options && typeof options.moveNumber === 'number' ? options.moveNumber : undefined;
  const timeMs = options && typeof options.timeMs === 'number' ? options.timeMs : null;

  // Opening book
  if (useOpeningBook) {
    const mv = bookMove(board, color, moveNumber ?? -1);
    if (mv) return mv;
  }

  // Baselines
  if (difficulty <= 1) {
    const allMoves = allLegalMoves(board, color);
    if (allMoves.length === 0) return null;
    const scored = allMoves.map(m => ({ m, s: simpleScoreMove(board, color, m) }));
    scored.sort((a,b)=> b.s - a.s);
    const k = Math.max(1, Math.floor(scored.length / 3));
    return scored[Math.floor(Math.random() * k)].m;
  }

  if (difficulty === 2) {
    const allMoves = allLegalMoves(board, color);
    if (allMoves.length === 0) return null;
    let best = allMoves[0], bestS = -Infinity;
    for (const m of allMoves) {
      const s = simpleScoreMove(board, color, m);
      if (s > bestS) { bestS = s; best = m; }
    }
    return best;
  }

  // difficulty >= 3 -> iterative deepening alpha-beta with enhancements
  const maxDepth = Math.min(10, 2 + difficulty * 2); // 3->8, 4->10 (cap 10), 5->10, 6->10
  const budget = timeMs ?? 700; // default if none provided

  // Reset search state
  TT.clear();
  killers.forEach(k => { k[0] = k[1] = null; });
  history.clear();
  NODE_COUNT = 0;
  STOPPED = false;
  DEADLINE = Date.now() + budget;

  const mv = searchRoot(board, color, maxDepth, budget);
  return mv || null;
}

// Adaptive wrapper
function getAIMoveAdaptive(board, color, opts) {
  const o = opts || {};
  const skill = Math.max(1, Math.min(6, Number(o.playerSkill || 3)));
  const difficulty = mapSkillToDifficulty(skill);
  const timeMs = timeBudgetMsForSkill(skill);
  const mv = getAIMove(board, color, difficulty, { useOpeningBook: !!o.useOpeningBook, moveNumber: o.moveNumber, timeMs });
  if (!mv) return null;
  return { ...mv, meta: { effectiveDifficulty: difficulty, effectiveDepth: mapSkillToDepth(skill), timeMs } };
}

function hasAnyLegalMoves(board, color) {
  for (let r = 0; r < 10; r++) {
    for (let c = 0; c < 9; c++) {
      const piece = board[r][c];
      if (piece && piece.c === color) {
        const moves = getLegalMoves(board, r, c);
        if (moves.length > 0) return true;
      }
    }
  }
  return false;
}

function isStalemate(board, color) {
  return !isInCheck(board, color) && !hasAnyLegalMoves(board, color);
}

window.logic = {
  getAIMove,
  getAIMoveAdaptive,
  initialBoard,
  applyMove,
  getLegalMovesFiltered,
  getLegalMoves,
  chineseChars,
  isInCheck,
  isCheckmate,
  findKing,
  evaluateBoard,
  hasAnyLegalMoves,
  isStalemate,
  boardKey
};
