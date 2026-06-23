"use client";

import { useEffect } from "react";

const COLORS = ["var(--accent)", "var(--primary)", "#ffffff", "var(--success)"];

export function ConfettiBurst({ active }: { active: boolean }) {
  useEffect(() => {
    if (!active) return;
    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduceMotion) return;

    const canvas = document.createElement("canvas");
    canvas.style.cssText =
      "position:fixed;inset:0;width:100%;height:100%;pointer-events:none;z-index:30000;";
    canvas.width = window.innerWidth;
    canvas.height = window.innerHeight;
    document.body.appendChild(canvas);
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const particles = Array.from({ length: 90 }, () => ({
      x: window.innerWidth / 2 + (Math.random() - 0.5) * 120,
      y: window.innerHeight * 0.55,
      vx: (Math.random() - 0.5) * 10,
      vy: -Math.random() * 12 - 4,
      size: Math.random() * 6 + 3,
      rot: Math.random() * Math.PI,
      spin: (Math.random() - 0.5) * 0.3,
      color: COLORS[Math.floor(Math.random() * COLORS.length)],
      life: 1,
    }));

    let frame = 0;
    let raf = 0;
    const tick = () => {
      frame += 1;
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      let alive = 0;
      for (const p of particles) {
        p.x += p.vx;
        p.y += p.vy;
        p.vy += 0.28;
        p.rot += p.spin;
        p.life -= 0.012;
        if (p.life <= 0) continue;
        alive += 1;
        ctx.save();
        ctx.translate(p.x, p.y);
        ctx.rotate(p.rot);
        ctx.globalAlpha = p.life;
        ctx.fillStyle = p.color;
        ctx.fillRect(-p.size / 2, -p.size / 2, p.size, p.size * 0.6);
        ctx.restore();
      }
      if (alive > 0 && frame < 180) {
        raf = requestAnimationFrame(tick);
      } else {
        canvas.remove();
      }
    };
    raf = requestAnimationFrame(tick);
    return () => {
      cancelAnimationFrame(raf);
      canvas.remove();
    };
  }, [active]);

  return null;
}
