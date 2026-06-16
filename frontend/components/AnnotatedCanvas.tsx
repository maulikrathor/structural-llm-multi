// components/AnnotatedCanvas.tsx
// Draws the structural outline fresh on a blank canvas using real coordinates.
// No superimposition — clean diagram with labeled corners and connecting lines.

import { useEffect, useRef } from "react";

interface Corner {
  label: string;
  x: number;
  y: number;
}

interface Props {
  corners: Corner[];
}

function getLabelOffset(corner: Corner, allCorners: Corner[]): { dx: number; dy: number } {
  const xs = allCorners.map((c) => c.x);
  const ys = allCorners.map((c) => c.y);
  const cx = (Math.min(...xs) + Math.max(...xs)) / 2;
  const cy = (Math.min(...ys) + Math.max(...ys)) / 2;
  const dx = corner.x - cx;
  const dy = corner.y - cy;
  return {
    dx: dx >= 0 ? 10 : -22,
    dy: dy >= 0 ? -14 : 16,
  };
}

export default function AnnotatedCanvas({ corners }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    if (!canvasRef.current || corners.length === 0) return;

    const canvas = canvasRef.current;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const W = 520;
    const H = 520;
    const PAD = 60; // padding so labels near edges aren't clipped
    canvas.width = W;
    canvas.height = H;

    // Dark background matching the app theme
    ctx.fillStyle = "#1a1d27";
    ctx.fillRect(0, 0, W, H);

    const xs = corners.map((c) => c.x);
    const ys = corners.map((c) => c.y);
    const minX = Math.min(...xs);
    const maxX = Math.max(...xs);
    const minY = Math.min(...ys);
    const maxY = Math.max(...ys);
    const rangeX = maxX - minX || 1;
    const rangeY = maxY - minY || 1;

    const drawW = W - PAD * 2;
    const drawH = H - PAD * 2;

    // Keep aspect ratio
    const scale = Math.min(drawW / rangeX, drawH / rangeY);
    const offsetX = PAD + (drawW - rangeX * scale) / 2;
    const offsetY = PAD + (drawH - rangeY * scale) / 2;

    function toCanvas(cx: number, cy: number) {
      return {
        px: offsetX + (cx - minX) * scale,
        // Flip Y: structural Y=0 is bottom, canvas Y=0 is top
        py: offsetY + (maxY - cy) * scale,
      };
    }

    // Draw structural outline (solid amber lines)
    ctx.strokeStyle = "#f59e0b";
    ctx.lineWidth = 2;
    ctx.setLineDash([]);
    ctx.beginPath();
    const first = toCanvas(corners[0].x, corners[0].y);
    ctx.moveTo(first.px, first.py);
    for (let i = 1; i < corners.length; i++) {
      const p = toCanvas(corners[i].x, corners[i].y);
      ctx.lineTo(p.px, p.py);
    }
    ctx.closePath();
    ctx.stroke();

    // Draw corner dots and labels
    corners.forEach((corner) => {
      const { px, py } = toCanvas(corner.x, corner.y);
      const offset = getLabelOffset(corner, corners);

      // Dot
      ctx.beginPath();
      ctx.arc(px, py, 5, 0, Math.PI * 2);
      ctx.fillStyle = "#f59e0b";
      ctx.fill();
      ctx.strokeStyle = "#0f1117";
      ctx.lineWidth = 1.5;
      ctx.stroke();

      // Label background
      ctx.font = "bold 13px sans-serif";
      const lx = px + offset.dx;
      const ly = py + offset.dy;
      const tw = ctx.measureText(corner.label).width;
      ctx.fillStyle = "rgba(0,0,0,0.75)";
      ctx.fillRect(lx - 2, ly - 12, tw + 6, 16);

      // Label text
      ctx.fillStyle = "#f59e0b";
      ctx.fillText(corner.label, lx + 1, ly);
    });

  }, [corners]);

  return (
    <div className="annotated-wrapper">
      <h3>Structural Diagram</h3>
      <canvas
        ref={canvasRef}
        style={{
          maxWidth: "100%",
          borderRadius: "8px",
          border: "1px solid var(--border)",
          display: "block",
        }}
      />
    </div>
  );
}
