"use client";

import { useEffect } from "react";
import {
  motion,
  useMotionTemplate,
  useMotionValue,
  useSpring,
} from "motion/react";

export function Scene() {
  const mouseX = useMotionValue(0);
  const mouseY = useMotionValue(0);
  const springX = useSpring(mouseX, { stiffness: 60, damping: 20 });
  const springY = useSpring(mouseY, { stiffness: 60, damping: 20 });

  const spotlight = useMotionTemplate`radial-gradient(600px circle at ${springX}px ${springY}px, var(--beam), transparent 65%)`;

  useEffect(() => {
    let raf = 0;
    let last = 0;
    function onMove(e: MouseEvent) {
      const now = performance.now();
      if (now - last < 32) return;
      last = now;
      cancelAnimationFrame(raf);
      raf = requestAnimationFrame(() => {
        mouseX.set(e.clientX);
        mouseY.set(e.clientY);
      });
    }
    window.addEventListener("mousemove", onMove, { passive: true });
    return () => {
      window.removeEventListener("mousemove", onMove);
      cancelAnimationFrame(raf);
    };
  }, [mouseX, mouseY]);

  return (
    <>
      <div className="scanlines" aria-hidden />

      {/* Base void */}
      <div className="fixed inset-0 z-0 bg-bg" aria-hidden />

      {/* Cursor spotlight */}
      <motion.div
        className="fixed inset-0 z-0 pointer-events-none"
        style={{ background: spotlight }}
        aria-hidden
      />

      {/* Ambient orbs */}
      <div className="fixed inset-0 z-0 overflow-hidden pointer-events-none" aria-hidden>
        <motion.div
          className="absolute -top-[20%] -left-[10%] w-[60vw] h-[60vw] rounded-full opacity-40"
          style={{
            background: "radial-gradient(circle, var(--glow) 0%, transparent 70%)",
          }}
          animate={{ x: [0, 30, 0], y: [0, 20, 0] }}
          transition={{ duration: 12, repeat: Infinity, ease: "easeInOut" }}
        />
        <motion.div
          className="absolute -bottom-[15%] -right-[5%] w-[50vw] h-[50vw] rounded-full opacity-30"
          style={{
            background: "radial-gradient(circle, var(--glow-accent) 0%, transparent 70%)",
          }}
          animate={{ x: [0, -25, 0], y: [0, -15, 0] }}
          transition={{ duration: 15, repeat: Infinity, ease: "easeInOut" }}
        />
        <motion.div
          className="absolute top-[40%] left-[60%] w-[30vw] h-[30vw] rounded-full opacity-20"
          style={{
            background: "radial-gradient(circle, var(--beam-alt) 0%, transparent 70%)",
          }}
          animate={{ scale: [1, 1.1, 1] }}
          transition={{ duration: 8, repeat: Infinity, ease: "easeInOut" }}
        />
      </div>

      {/* Perspective grid floor */}
      <div
        className="fixed inset-0 z-0 pointer-events-none opacity-[0.06]"
        aria-hidden
        style={{
          backgroundImage: `
            linear-gradient(var(--border-bright) 1px, transparent 1px),
            linear-gradient(90deg, var(--border-bright) 1px, transparent 1px)
          `,
          backgroundSize: "64px 64px",
          maskImage: "radial-gradient(ellipse 90% 60% at 50% 30%, black, transparent)",
        }}
      />
    </>
  );
}
