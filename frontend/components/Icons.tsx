import { memo } from "react";

/* The little icon set from the prototype, drawn once and reused with <Icon id="..." />. */

export const IconSprite = memo(function IconSprite() {
  return (
    <svg width="0" height="0" style={{ position: "absolute" }} aria-hidden="true">
      <defs>
        <symbol id="i-book" viewBox="0 0 24 24"><path d="M3 5.5c3-1 6-.8 9 1v12.5c-3-1.8-6-2-9-1z" /><path d="M21 5.5c-3-1-6-.8-9 1v12.5c3-1.8 6-2 9-1z" /></symbol>
        <symbol id="i-spark" viewBox="0 0 24 24"><path d="M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8z" /><path d="M19 16v4M17 18h4" /></symbol>
        <symbol id="i-bulb" viewBox="0 0 24 24"><path d="M9 18h6M10 21h4" /><path d="M12 3a6 6 0 0 0-3.5 10.9c.6.5 1 1.2 1 2.1h5c0-.9.4-1.6 1-2.1A6 6 0 0 0 12 3z" /></symbol>
        <symbol id="i-mountain" viewBox="0 0 24 24"><path d="M2.5 19.5 9.5 7l4.2 7 2.3-3.5 5.5 9z" /><path d="M9.5 7V3.5l3.2 1.2-3.2 1.1" /></symbol>
        <symbol id="i-bolt" viewBox="0 0 24 24"><path d="M13 3 5 13.5h6L10 21l9-11h-6z" /></symbol>
        <symbol id="i-pencil" viewBox="0 0 24 24"><path d="M4 20l1-4L16.5 4.5l3 3L8 19z" /><path d="M14.5 6.5l3 3" /></symbol>
        <symbol id="i-check" viewBox="0 0 24 24"><path d="M5 12.5l4.5 4.5L19 7" /></symbol>
        <symbol id="i-info" viewBox="0 0 24 24"><circle cx="12" cy="12" r="8.5" /><path d="M12 11v5.5M12 7.8v.2" /></symbol>
        <symbol id="i-lock" viewBox="0 0 24 24"><rect x="5.5" y="10.5" width="13" height="9.5" rx="2" /><path d="M8.5 10.5V8a3.5 3.5 0 0 1 7 0v2.5" /></symbol>
        <symbol id="i-chart" viewBox="0 0 24 24"><path d="M5 20V11M12 20V5M19 20v-6" /></symbol>
        <symbol id="i-arrow" viewBox="0 0 24 24"><path d="M5 12h14M13 6l6 6-6 6" /></symbol>
        <symbol id="i-wave" viewBox="0 0 24 24"><path d="M3 15c3 0 3.5-7 8-7s4.5 9 10 6" /><circle cx="11" cy="8" r="1.6" /></symbol>
        <symbol id="i-flame" viewBox="0 0 24 24"><path d="M12 3c1 4 5 5.500 5 10.500a5 5 0 0 1-10 0c0-2.500 1.200-3.800 2.200-5C9.600 10 10.500 10 11 11c.8-2 .8-4.500 1-8z" /></symbol>
        <symbol id="i-close" viewBox="0 0 24 24"><path d="M6 6l12 12M18 6 6 18" /></symbol>
        <symbol id="i-undo" viewBox="0 0 24 24"><path d="M9 7 4.500 11.500 9 16" /><path d="M5 11.500h9a5 5 0 0 1 0 10h-3" /></symbol>
        <symbol id="i-nodes" viewBox="0 0 24 24"><circle cx="12" cy="6" r="2.4" /><circle cx="6" cy="17" r="2.4" /><circle cx="18" cy="17" r="2.4" /><path d="M10.800 8.200 7.200 14.800M13.200 8.200l3.600 6.600M8.400 17h7.200" /></symbol>
      </defs>
    </svg>
  );
});

export type IconId =
  | "i-book" | "i-spark" | "i-bulb" | "i-mountain" | "i-bolt" | "i-pencil" | "i-check" | "i-info"
  | "i-lock" | "i-chart" | "i-arrow" | "i-wave" | "i-flame" | "i-close" | "i-undo" | "i-nodes";

export const Icon = memo(function Icon({ id, className = "", style }: { id: IconId; className?: string; style?: React.CSSProperties }) {
  return (
    <svg className={`i ${className}`.trim()} style={style} aria-hidden="true">
      <use href={`#${id}`} />
    </svg>
  );
});
