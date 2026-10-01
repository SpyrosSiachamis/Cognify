"use client";

import { useEffect, useRef } from "react";
import { prefersReducedMotion } from "@/lib/fx";

/* "Hints needed over time": a small line chart. With `animate` the line draws itself. */
export function Spark({ vals, labels, animate }: { vals: number[]; labels: string[]; animate: boolean }) {
  const W = 320, H = 132, pl = 26, pr = 36, pt = 16, pb = 28, n = vals.length, ymax = 4;
  const xs = (i: number) => pl + (n === 1 ? 0 : (i * (W - pl - pr)) / (n - 1));
  const ys = (v: number) => pt + (1 - v / ymax) * (H - pt - pb);
  const pts = vals.map((v, i) => `${xs(i).toFixed(1)},${ys(v).toFixed(1)}`).join(" ");
  const area = `M${xs(0)},${H - pb} ` + vals.map((v, i) => `L${xs(i).toFixed(1)},${ys(v).toFixed(1)}`).join(" ") + ` L${xs(n - 1)},${H - pb} Z`;
  const last = n - 1;
  const line = useRef<SVGPolylineElement>(null);

  useEffect(() => {
    const pl = line.current;
    if (!animate || prefersReducedMotion() || !pl?.getTotalLength) return;
    const len = pl.getTotalLength();
    pl.style.strokeDasharray = String(len);
    pl.style.strokeDashoffset = String(len);
    pl.getBoundingClientRect();
    pl.style.transition = "stroke-dashoffset 1.6s cubic-bezier(.4,0,.2,1) .3s";
    pl.style.strokeDashoffset = "0";
  }, [animate, vals]);

  return (
    <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`Hints needed per session: ${vals.join(", ")}`}>
      {[0, 2, 4].map((v) => (
        <g key={v}>
          <line className="grid" x1={pl} x2={W - pl} y1={ys(v)} y2={ys(v)} />
          <text x={pl - 8} y={ys(v) + 3} textAnchor="end">{v}</text>
        </g>
      ))}
      <path className="area" d={area} />
      <polyline className="ln" points={pts} ref={line} />
      {vals.map((v, i) => (
        <circle key={i} className={`pt${i === last ? " last" : ""}`} cx={xs(i)} cy={ys(v)} r={i === last ? 6 : 2.8} />
      ))}
      <text className="lastv" x={xs(last)} y={ys(vals[last]) - 12} textAnchor="middle">{vals[last]}</text>
      {labels.map((m, i) => (
        <text key={i} x={xs(i)} y={H - 8} textAnchor="middle">{m}</text>
      ))}
    </svg>
  );
}
