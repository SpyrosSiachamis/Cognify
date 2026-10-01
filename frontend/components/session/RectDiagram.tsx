/* The live rectangle. Stage 0: width x, length unknown. Stage 1: length is x + 2. Stage 2: solved, 6 m by 8 m. */
export function RectDiagram({ stage }: { stage: 0 | 1 | 2 }) {
  const built = stage > 0;
  return (
    <div className="dg">
      <svg className="rect-svg" viewBox="0 0 250 236" role="img" aria-label="Rectangle with area 48 square metres">
        <rect
          className="rr"
          x="30"
          y="18"
          height="150"
          rx="5"
          style={{ width: built ? 118 : 150, fill: "var(--teach-tint)", stroke: "var(--teach)", strokeWidth: 2.2, transition: "width .7s cubic-bezier(.2,.8,.2,1)" }}
        />
        <text x={built ? 89 : 105} y="102" textAnchor="middle" fontSize="25" style={{ fill: "var(--teach)" }}>
          48 m²
        </text>
        <line x1="30" y1="190" x2="180" y2="190" style={{ stroke: "var(--ink-faint)" }} strokeDasharray="3 4" />
        <line x1="204" y1="18" x2="204" y2="168" style={{ stroke: "var(--ink-faint)" }} strokeDasharray="3 4" />
        <text x={built ? 89 : 105} y="218" textAnchor="middle" fontSize="22" style={{ fill: "var(--ink)" }}>
          {stage === 2 ? "x = 6 m" : "x"}
        </text>
        <text
          x="228"
          y="101"
          textAnchor="middle"
          fontSize="22"
          style={{ fill: built ? "var(--teach)" : "var(--bad)" }}
          transform={built ? "rotate(90 228 101)" : undefined}
        >
          {stage === 2 ? "8 m" : built ? "x + 2" : "?"}
        </text>
      </svg>
    </div>
  );
}
