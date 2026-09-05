// chessboard.js —— 中国象棋棋盘渲染与交互（零依赖，坐标与后端一致）
// 文件 a-i(0..8)，行 0-9（0=黑方在上）。大写=红方、小写=黑方。
"use strict";

(function (global) {
  const PIECE_CHARS = {
    K: "帅", A: "仕", B: "相", N: "马", R: "车", C: "炮", P: "兵",
    k: "将", a: "士", b: "象", n: "马", r: "车", c: "炮", p: "卒",
  };
  const FILES = ["a", "b", "c", "d", "e", "f", "g", "h", "i"];

  function parseFen(fen) {
    const ranks = fen.split(" ")[0].split("/");
    const cells = [];
    for (const rank of ranks) {
      for (const ch of rank) {
        if (/[0-9]/.test(ch)) {
          for (let i = 0; i < parseInt(ch, 10); i++) cells.push(null);
        } else {
          cells.push(ch);
        }
      }
    }
    return cells; // 90 格, index = rank*9 + file
  }

  class ChessBoard {
    constructor(container) {
      this.el = container;
      this.fen = "";
      this.selected = null;       // {file, rank}
      this.targets = [];          // [{file, rank, capture}]
      this.aiFrom = null;
      this.aiTo = null;
      this.onSquareClick = null;
      this._layout = null;
      this._build();
      this._onResize = () => { if (this.fen) this.setFen(this.fen); };
      window.addEventListener("resize", this._onResize);
    }

    _build() {
      const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
      svg.setAttribute("class", "grid");
      this.svg = svg;
      this.layer = document.createElement("div");
      this.layer.style.cssText = "position:absolute;inset:0;";
      this.trailSvg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
      this.trailSvg.setAttribute("class", "trail-layer");
      this.trailSvg.setAttribute("viewBox", "0 0 1 1");
      this.el.appendChild(svg);
      this.el.appendChild(this.layer);
      this.el.appendChild(this.trailSvg);
      this.el.addEventListener("click", (ev) => this._onClick(ev));
    }

    _computeLayout() {
      const r = this.el.getBoundingClientRect();
      const padX = r.width * 0.055;
      const padY = r.height * 0.06;
      const gridW = r.width - 2 * padX;
      const gridH = r.height - 2 * padY;
      return {
        w: r.width, h: r.height, padX, padY,
        stepX: gridW / 8, stepY: gridH / 9,
      };
    }

    _x(file) { const L = this._layout; return L.padX + file * L.stepX; }
    _y(rank) { const L = this._layout; return L.padY + rank * L.stepY; }

    _drawGrid() {
      const L = this._layout;
      const svg = this.svg;
      svg.setAttribute("viewBox", "0 0 " + L.w + " " + L.h);
      svg.innerHTML = "";
      const stroke = "#5a3d22";
      const sw = Math.max(1, L.stepX * 0.02);
      // 边框 + 横线 + 竖线
      const lines = [];
      // 竖线：左右两边边框贯通；中间列在河界带(行4~5之间)断开，形成“楚河汉界”留白
      for (let f = 0; f < 9; f++) {
        if (f === 0 || f === 8) {
          lines.push([this._x(f), L.padY, this._x(f), L.padY + 9 * L.stepY, true]);
        } else {
          lines.push([this._x(f), L.padY, this._x(f), this._y(4), false]);
          lines.push([this._x(f), this._y(5), this._x(f), L.padY + 9 * L.stepY, false]);
        }
      }
      for (let r = 0; r < 10; r++) lines.push([L.padX, this._y(r), L.padX + 8 * L.stepX, this._y(r), r === 0 || r === 9]);
      // 河界内只画竖线（去掉中间4条横线）
      for (let r = 1; r <= 4; r++) {
        lines.push([L.padX, this._y(r), L.padX + 8 * L.stepX, this._y(r), false]);
      }
      // 九宫斜线（上下）
      lines.push([this._x(3), this._y(0), this._x(5), this._y(2), false]);
      lines.push([this._x(5), this._y(0), this._x(3), this._y(2), false]);
      lines.push([this._x(3), this._y(7), this._x(5), this._y(9), false]);
      lines.push([this._x(5), this._y(7), this._x(3), this._y(9), false]);

      for (const [x1, y1, x2, y2, bold] of lines) {
        const ln = document.createElementNS("http://www.w3.org/2000/svg", "line");
        ln.setAttribute("x1", x1); ln.setAttribute("y1", y1);
        ln.setAttribute("x2", x2); ln.setAttribute("y2", y2);
        ln.setAttribute("stroke", stroke);
        ln.setAttribute("stroke-width", bold ? sw * 1.6 : sw);
        svg.appendChild(ln);
      }
      // 炮/兵 位点
      const dots = [[1,2],[7,2],[1,7],[7,7],[0,3],[2,3],[4,3],[6,3],[8,3],[0,6],[2,6],[4,6],[6,6],[8,6]];
      for (const [f, r] of dots) {
        const c = document.createElementNS("http://www.w3.org/2000/svg", "circle");
        c.setAttribute("cx", this._x(f)); c.setAttribute("cy", this._y(r));
        c.setAttribute("r", sw * 1.1); c.setAttribute("fill", stroke);
        svg.appendChild(c);
      }
      // 楚河 汉界（河界中心：文件4、行4.5；text-anchor+dominant-baseline 双居中，保证位置精准）
      const txt = (text, x, y) => {
        const t = document.createElementNS("http://www.w3.org/2000/svg", "text");
        t.setAttribute("x", x);
        t.setAttribute("y", y);
        t.setAttribute("text-anchor", "middle");
        t.setAttribute("dominant-baseline", "central");
        t.setAttribute("fill", "#7a5230");
        t.setAttribute("font-size", L.stepX * 0.62);
        t.setAttribute("font-family", "KaiTi, STKaiti, serif");
        t.textContent = text;
        svg.appendChild(t);
      };
      const riverY = L.padY + 4.5 * L.stepY;
      txt("楚 河", this._x(3), riverY);
      txt("汉 界", this._x(5), riverY);
    }

    setFen(fen) {
      this.fen = fen;
      this._layout = this._computeLayout();
      // 防御：容器不可见（display:none，如对局室尚未显示）时 getBoundingClientRect 为 0，
      // 此刻渲染会画出 0 尺寸网格；延迟到下一帧，等容器显示后再渲染。
      // 空 FEN（清屏）不需要重画网格，直接跳过排队避免隐藏状态下无限 rAF。
      if ((!this._layout.w || !this._layout.h) && fen) {
        if (this._pendingFen) return; // 已有待重画，避免重复排队
        this._pendingFen = fen;
        requestAnimationFrame(() => {
          this._pendingFen = null;
          if (this.fen) this.setFen(this.fen);
        });
        return;
      }
      this.trailSvg.setAttribute("viewBox", "0 0 " + this._layout.w + " " + this._layout.h);
      this._drawGrid();
      const cells = parseFen(fen);
      this.layer.innerHTML = "";
      for (let i = 0; i < 90; i++) {
        if (!cells[i]) continue;
        const file = i % 9, rank = Math.floor(i / 9);
        const p = document.createElement("div");
        p.className = "piece " + (cells[i] === cells[i].toUpperCase() ? "red" : "black");
        p.textContent = PIECE_CHARS[cells[i]] || cells[i];
        p.style.left = this._x(file) + "px";
        p.style.top = this._y(rank) + "px";
        p.dataset.file = file;
        p.dataset.rank = rank;
        p.style.width = p.style.height = Math.min(this._layout.stepX, this._layout.stepY) * 0.82 + "px";
        if (this.selected && this.selected.file === file && this.selected.rank === rank) p.classList.add("selected");
        if (this.aiFrom && this.aiFrom[0] === file && this.aiFrom[1] === rank) p.classList.add("ai-last");
        if (this.aiTo && this.aiTo[0] === file && this.aiTo[1] === rank) p.classList.add("ai-last");
        this.layer.appendChild(p);
      }
    }

    _onClick(ev) {
      const L = this._layout;
      if (!L) return;
      const r = this.el.getBoundingClientRect();
      const x = ev.clientX - r.left;
      const y = ev.clientY - r.top;
      const file = Math.round((x - L.padX) / L.stepX);
      const rank = Math.round((y - L.padY) / L.stepY);
      if (file < 0 || file > 8 || rank < 0 || rank > 9) return;
      if (this.onSquareClick) this.onSquareClick(file, rank);
    }

    select(file, rank) {
      this.selected = { file, rank };
      this.setFen(this.fen);
    }

    clearSelection() {
      this.selected = null;
      this.targets = [];
      this.setFen(this.fen);
    }

    highlightTargets(targets) {
      // targets: [{file, rank, capture}]
      this.targets = targets || [];
      this.layer.querySelectorAll(".cell-dot").forEach((d) => d.remove());
      for (const t of this.targets) {
        const d = document.createElement("div");
        d.className = "cell-dot " + (t.capture ? "capture" : "target");
        d.style.left = this._x(t.file) + "px";
        d.style.top = this._y(t.rank) + "px";
        this.layer.appendChild(d);
      }
    }

    clearTargets() {
      this.targets = [];
      this.layer.querySelectorAll(".cell-dot").forEach((d) => d.remove());
    }

    markAiMove(fromSq, toSq) {
      this.aiFrom = [FILES.indexOf(fromSq[0]), parseInt(fromSq[1], 10)];
      this.aiTo = [FILES.indexOf(toSq[0]), parseInt(toSq[1], 10)];
      this.setFen(this.fen);
      this.showTrail(fromSq, toSq, "ai");
    }

    showTrail(fromSq, toSq, cls) {
      // 移动轨迹：从源格到目标格画一条淡出的线 + 终点圆点（方便看清棋子走向）
      const L = this._layout;
      if (!L) return;
      const ff = FILES.indexOf(fromSq[0]);
      const fr = parseInt(fromSq[1], 10);
      const tf = FILES.indexOf(toSq[0]);
      const tr = parseInt(toSq[1], 10);
      const x1 = this._x(ff), y1 = this._y(fr);
      const x2 = this._x(tf), y2 = this._y(tr);
      const line = document.createElementNS("http://www.w3.org/2000/svg", "line");
      line.setAttribute("x1", x1); line.setAttribute("y1", y1);
      line.setAttribute("x2", x2); line.setAttribute("y2", y2);
      line.setAttribute("class", "trail " + (cls || ""));
      const dot = document.createElementNS("http://www.w3.org/2000/svg", "circle");
      dot.setAttribute("cx", x2); dot.setAttribute("cy", y2);
      dot.setAttribute("r", L.stepX * 0.12);
      dot.setAttribute("class", "trail-dot " + (cls || ""));
      this.trailSvg.appendChild(line);
      this.trailSvg.appendChild(dot);
      setTimeout(function () { line.remove(); dot.remove(); }, 1500);
    }

    movePiece(fromSq, toSq, fen) {
      // 乐观落子：立即把棋子滑到目标格（不等待后端），吃子则移除目标格棋子
      const ff = FILES.indexOf(fromSq[0]);
      const fr = parseInt(fromSq[1], 10);
      const tf = FILES.indexOf(toSq[0]);
      const tr = parseInt(toSq[1], 10);
      const L = this._layout;
      if (!L) { this.fen = fen; return; }
      let mover = null;
      for (const p of Array.from(this.layer.querySelectorAll(".piece"))) {
        const f = parseInt(p.dataset.file, 10);
        const r = parseInt(p.dataset.rank, 10);
        if (f === ff && r === fr) { mover = p; }
        else if (f === tf && r === tr) { p.remove(); } // 吃子
      }
      if (!mover) { this.fen = fen; return; }
      mover.dataset.file = tf;
      mover.dataset.rank = tr;
      mover.classList.remove("selected");
      mover.style.left = this._x(tf) + "px";
      mover.style.top = this._y(tr) + "px";
      this.showTrail(fromSq, toSq, "user");
      this.fen = fen;
    }

    setBusy(busy) {
      this.el.classList.toggle("busy", busy);
    }
  }

  global.ChessBoard = ChessBoard;
})(window);
