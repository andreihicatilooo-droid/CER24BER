export class CanvasEngine {
  constructor(canvas) {
    this.canvas = canvas;
    this.ctx = canvas.getContext("2d");
    this.clickHandlers = [];
    this.resize();
    window.addEventListener("resize", () => this.resize());
    canvas.addEventListener("click", (event) => this.handleClick(event));
  }

  resize() {
    const ratio = window.devicePixelRatio || 1;
    const width = this.canvas.clientWidth || window.innerWidth;
    const height = this.canvas.clientHeight || window.innerHeight;
    this.canvas.width = Math.floor(width * ratio);
    this.canvas.height = Math.floor(height * ratio);
    this.ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
  }

  clear(fill = "#0f172a") {
    this.ctx.fillStyle = fill;
    this.ctx.fillRect(0, 0, this.canvas.clientWidth, this.canvas.clientHeight);
    this.clickHandlers = [];
  }

  roundedRect(x, y, w, h, r, fill, stroke = null, lineWidth = 1) {
    const c = this.ctx;
    c.beginPath();
    c.moveTo(x + r, y);
    c.lineTo(x + w - r, y);
    c.quadraticCurveTo(x + w, y, x + w, y + r);
    c.lineTo(x + w, y + h - r);
    c.quadraticCurveTo(x + w, y + h, x + w - r, y + h);
    c.lineTo(x + r, y + h);
    c.quadraticCurveTo(x, y + h, x, y + h - r);
    c.lineTo(x, y + r);
    c.quadraticCurveTo(x, y, x + r, y);
    c.closePath();
    c.fillStyle = fill;
    c.fill();
    if (stroke) {
      c.lineWidth = lineWidth;
      c.strokeStyle = stroke;
      c.stroke();
    }
  }

  text(value, x, y, options = {}) {
    const {
      color = "#e2e8f0",
      size = 14,
      weight = "600",
      align = "left",
      baseline = "alphabetic",
      font = "Segoe UI",
    } = options;
    const c = this.ctx;
    c.fillStyle = color;
    c.textAlign = align;
    c.textBaseline = baseline;
    c.font = `${weight} ${size}px ${font}`;
    c.fillText(String(value), x, y);
  }

  registerClick(x, y, w, h, handler) {
    this.clickHandlers.push({ x, y, w, h, handler });
  }

  handleClick(event) {
    const rect = this.canvas.getBoundingClientRect();
    const px = event.clientX - rect.left;
    const py = event.clientY - rect.top;
    for (const zone of this.clickHandlers) {
      if (px >= zone.x && px <= zone.x + zone.w && py >= zone.y && py <= zone.y + zone.h) {
        zone.handler();
        return;
      }
    }
  }
}

export function drawCard(engine, { x, y, label, selected = false, trump = false }) {
  const cardFill = selected ? "#eff6ff" : "#ffffff";
  const stroke = selected ? "#3b82f6" : "#334155";
  engine.roundedRect(x, y, 56, 82, 8, cardFill, stroke, selected ? 3 : 1);

  const suit = label.slice(-1);
  const rank = label.slice(0, -1);
  const isRed = suit === "♥" || suit === "♦";
  const color = isRed ? "#dc2626" : "#111827";

  engine.text(`${rank}${suit}`, x + 8, y + 18, { color, size: 15, weight: "700" });
  engine.text(suit, x + 28, y + 46, { color, size: 26, weight: "700", align: "center", baseline: "middle" });

  if (trump) {
    engine.roundedRect(x + 38, y + 6, 12, 12, 4, "#f59e0b");
  }
}

export function drawDeck(engine, { x, y, count = 0 }) {
  // Рисуем стопку карт (3 слоя для эффекта толщины)
  const colors = ["#1e40af", "#2563eb", "#3b82f6"];
  const offsets = [4, 2, 0];
  
  for (let i = 0; i < 3; i++) {
    engine.roundedRect(x + offsets[i], y + offsets[i], 56, 82, 8, colors[i], "#0c4a6e", 1);
  }
  
  // Текст с количеством карт
  engine.text(String(count), x + 28, y + 42, {
    color: "#e0f2fe",
    size: 24,
    weight: "700",
    align: "center",
    baseline: "middle",
  });
}
