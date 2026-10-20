/**
 * Flat, friendly standing characters for the Team lineup, drawn in SVG (original designs). The role picks
 * the outfit and prop; a look (skin, hair, height, clothing colours) is assigned per position in the
 * roster, so the people differ without any extra data. Decorative illustration only: no figures.
 */

export type Kind = "barista" | "roaster" | "baker" | "cashier" | "manager" | "packer" | "tech" | "driver" | "cleaner" | "generic";
type Hair = "short" | "bun" | "long" | "curly" | "bob";

export type Look = { skin: string; hair: string; hairStyle: Hair; height: number; shirt: string; trousers: string; shoes: string; accent: string };

// One consistent palette family; skin tones from light to deep.
export const LOOKS: Look[] = [
  { skin: "#8d5a3b", hair: "#1f1a17", hairStyle: "bun", height: 0.95, shirt: "#3f6b5c", trousers: "#2f3a4f", shoes: "#3b2a20", accent: "#7a4b2a" },
  { skin: "#f1c9a0", hair: "#6b4423", hairStyle: "short", height: 1, shirt: "#b5643c", trousers: "#3b4a5e", shoes: "#2a2a2a", accent: "#2f3a4f" },
  { skin: "#c68b59", hair: "#2b1d14", hairStyle: "long", height: 0.9, shirt: "#e7ebf3", trousers: "#2f3a4f", shoes: "#4a3426", accent: "#2b4bcf" },
  { skin: "#ffdcb8", hair: "#b8612d", hairStyle: "curly", height: 0.97, shirt: "#5b7fa6", trousers: "#3a3f4a", shoes: "#2a2a2a", accent: "#3f4a5a" },
  { skin: "#eec39a", hair: "#1c1c22", hairStyle: "bob", height: 0.86, shirt: "#d9a441", trousers: "#4a5568", shoes: "#3b2a20", accent: "#8a6a3d" },
];
export const HIRE_LOOK: Look = { skin: "#a86b45", hair: "#4a3426", hairStyle: "short", height: 0.93, shirt: "#7c6aa8", trousers: "#2f3a4f", shoes: "#2a2a2a", accent: "#5b4a8a" };

/** "Head roaster" → roaster, "Barista lead" → barista, "Packing and shipping" → packer, "Developer" → tech
 *  (laptop), "Delivery driver" → driver (keys), "Cleaner" → cleaner (apron); anything else → generic. */
export function kindFor(role: string): Kind {
  const r = role.toLowerCase();
  if (/program|develop|software|engineer|\bit\b|tech/.test(r)) return "tech";
  if (/driv|deliver|courier/.test(r)) return "driver";
  if (/clean|janitor|housekeep/.test(r)) return "cleaner";
  if (r.includes("barista")) return "barista";
  if (r.includes("roast")) return "roaster";
  if (r.includes("bak") || r.includes("pastry")) return "baker";
  if (r.includes("cash") || r.includes("till") || r.includes("counter")) return "cashier";
  if (r.includes("manag")) return "manager";
  if (r.includes("pack") || r.includes("ship")) return "packer";
  return "generic";
}

const isLead = (role: string) => /\b(head|lead|senior|chief)\b/i.test(role);
const INK = "#18213a";

function HairBack({ look }: { look: Look }) {
  if (look.hairStyle === "long") return <rect x="37" y="38" width="46" height="50" rx="16" fill={look.hair} />;
  if (look.hairStyle === "bob") return <rect x="37" y="36" width="46" height="34" rx="14" fill={look.hair} />;
  return null;
}

function HairFront({ look, kind }: { look: Look; kind: Kind }) {
  if (kind === "baker") return null; // under the baker's hat
  const cap = <path d="M39.5 50 Q39 29 60 29 Q81 29 80.5 50 Q74 39 60 39 Q46 39 39.5 50 Z" fill={look.hair} />;
  switch (look.hairStyle) {
    case "bun":
      return <>{cap}<circle cx="60" cy="25" r="9" fill={look.hair} /></>;
    case "curly":
      return (
        <g fill={look.hair}>
          {[[43, 42, 8], [50, 34, 9], [60, 30, 9], [70, 33, 9], [77, 41, 8]].map(([x, y, r]) => <circle key={x} cx={x} cy={y} r={r} />)}
        </g>
      );
    default:
      return cap;
  }
}

function Hat({ kind, look }: { kind: Kind; look: Look }) {
  if (kind === "baker") {
    return (
      <g fill="#ffffff" stroke="#d9dee8" strokeWidth="1">
        <rect x="42" y="30" width="36" height="12" rx="3" />
        <circle cx="48" cy="24" r="9" /><circle cx="60" cy="19" r="11" /><circle cx="72" cy="24" r="9" />
      </g>
    );
  }
  if (kind === "roaster" || kind === "packer" || kind === "driver") {
    return (
      <g fill={look.accent}>
        <path d="M39.5 44 Q39 27 60 27 Q81 27 80.5 44 Z" />
        <rect x="58" y="41" width="30" height="5" rx="2.5" />
      </g>
    );
  }
  return null;
}

function Prop({ kind }: { kind: Kind }) {
  switch (kind) {
    case "barista":
      return (
        <g>
          <path d="M56 98 q-3 -5 0 -9 M63 98 q-3 -5 0 -9" stroke="#9aa3b5" strokeWidth="1.6" fill="none" strokeLinecap="round" />
          <path d="M52 102 h16 l-2 17 h-12 z" fill="#ffffff" stroke="#d9dee8" />
          <rect x="52.6" y="107" width="14.8" height="5" fill="#9a5a34" />
        </g>
      );
    case "roaster":
      return (
        <g>
          <path d="M43 106 Q41 140 60 142 Q79 140 77 106 Q70 99 60 101 Q50 99 43 106 Z" fill="#c9a272" stroke="#a9824f" />
          <path d="M53 101 q7 -6 14 0" stroke="#7a5a33" strokeWidth="2.5" fill="none" strokeLinecap="round" />
          <ellipse cx="60" cy="123" rx="6" ry="8" fill="#6b4423" />
          <path d="M60 116 q-3 7 0 14" stroke="#c9a272" strokeWidth="1.5" fill="none" />
        </g>
      );
    case "packer":
      return (
        <g>
          <rect x="43" y="102" width="34" height="26" rx="2" fill="#c9935a" />
          <rect x="58" y="102" width="4" height="26" fill="#e8c79a" />
          <path d="M43 109 h34" stroke="#a87442" strokeWidth="1" />
        </g>
      );
    case "baker":
      return (
        <g>
          <ellipse cx="60" cy="112" rx="15" ry="8" fill="#d9a35b" stroke="#b9823f" />
          <path d="M51 109 l4 5 M58 107 l4 6 M65 108 l4 5" stroke="#f2cf96" strokeWidth="1.6" strokeLinecap="round" />
        </g>
      );
    case "tech":
      return (
        <g>
          <path d="M42 120 h36 l4 6 h-44 z" fill="#9aa3b5" />
          <rect x="45" y="97" width="30" height="23" rx="2" fill="#34405a" />
          <rect x="47.5" y="99.5" width="25" height="18" rx="1" fill="#cfe0ff" />
          <circle cx="60" cy="108.5" r="2.2" fill="#2b4bcf" />
        </g>
      );
    case "driver":
      return (
        <g>
          <circle cx="69" cy="122" r="4.5" fill="none" stroke="#b7791f" strokeWidth="1.8" />
          <path d="M66 126 l-3 9 l3 1 l1 -3 l2 0" fill="none" stroke="#9aa3b5" strokeWidth="2" strokeLinejoin="round" />
          <path d="M72 126 l2 8 l2 -0.5" fill="none" stroke="#c0c7d4" strokeWidth="2" />
        </g>
      );
    case "manager":
      return (
        <g>
          <rect x="50" y="99" width="20" height="27" rx="2" fill="#8b6b4a" />
          <rect x="52.5" y="103" width="15" height="20" fill="#ffffff" />
          <path d="M55 108 h10 M55 112 h10 M55 116 h7" stroke="#9aa3b5" strokeWidth="1.2" />
          <rect x="56" y="97" width="8" height="4" rx="1" fill="#c0c7d4" />
        </g>
      );
    default:
      return null;
  }
}

/** One standing person, feet on y=214 of a 120×220 box; `height` scales them from the floor. */
export function Figure({ look, kind, lead }: { look: Look; kind: Kind; lead?: boolean }) {
  const holds = kind !== "cashier" && kind !== "generic" && kind !== "cleaner";
  const apron = kind === "barista" || kind === "baker" || kind === "cleaner" || (kind === "roaster" && lead);
  const apronColor = kind === "baker" ? "#ffffff" : look.accent;
  const top = kind === "manager" ? "#34405a" : kind === "cashier" ? look.accent : look.shirt;
  return (
    <g transform={`translate(60 214) scale(${look.height}) translate(-60 -214)`}>
      <HairBack look={look} />
      {/* legs and shoes */}
      <rect x="46" y="140" width="12.5" height="68" rx="5" fill={look.trousers} />
      <rect x="61.5" y="140" width="12.5" height="68" rx="5" fill={look.trousers} />
      <rect x="42" y="203" width="18" height="9" rx="4.5" fill={look.shoes} />
      <rect x="60" y="203" width="18" height="9" rx="4.5" fill={look.shoes} />
      {/* body */}
      <rect x="55" y="68" width="10" height="16" rx="3" fill={look.skin} />
      <rect x="39" y="80" width="42" height="66" rx="15" fill={top} />
      {kind === "cashier" && <rect x="48" y="80" width="24" height="40" rx="6" fill={look.shirt} />}
      {kind === "manager" && (
        <g>
          <path d="M53 81 L60 100 L67 81 Z" fill="#ffffff" />
          <path d="M58.5 86 h3 l1 10 l-2.5 3 l-2.5 -3 z" fill={look.accent} />
        </g>
      )}
      {apron && (
        <g>
          <path d="M47 92 L73 92 L76 150 Q60 155 44 150 Z" fill={apronColor} stroke={kind === "baker" ? "#d9dee8" : "none"} />
          <path d="M49 92 Q60 80 71 92" stroke={apronColor} strokeWidth="2.5" fill="none" />
          <rect x="54" y="130" width="12" height="8" rx="2" fill="#000000" fillOpacity="0.12" />
        </g>
      )}
      {(lead || kind === "cashier") && <circle cx="72" cy="96" r="3.6" fill="#b7791f" stroke="#ffffff" strokeWidth="1.2" />}
      {/* arms: down at the sides, or bent to hold the prop in front */}
      {holds ? (
        <g stroke={top} strokeWidth="10.5" strokeLinecap="round" fill="none">
          <path d="M43 88 L37 110 L51 116" />
          <path d="M77 88 L83 110 L69 116" />
        </g>
      ) : (
        <g stroke={top} strokeWidth="10.5" strokeLinecap="round" fill="none">
          <path d="M43 88 L37 132" />
          <path d="M77 88 L83 132" />
        </g>
      )}
      {holds && <Prop kind={kind} />}
      <g fill={look.skin}>
        {holds ? <><circle cx="51" cy="116" r="5" /><circle cx="69" cy="116" r="5" /></> : <><circle cx="37" cy="135" r="5" /><circle cx="83" cy="135" r="5" /></>}
      </g>
      {/* head */}
      <circle cx="40.5" cy="54" r="4" fill={look.skin} />
      <circle cx="79.5" cy="54" r="4" fill={look.skin} />
      <circle cx="60" cy="52" r="20" fill={look.skin} />
      <HairFront look={look} kind={kind} />
      <Hat kind={kind} look={look} />
      <circle cx="53" cy="54" r="2.1" fill={INK} />
      <circle cx="67" cy="54" r="2.1" fill={INK} />
      <circle cx="49" cy="60" r="3" fill="#e8846f" fillOpacity="0.3" />
      <circle cx="71" cy="60" r="3" fill="#e8846f" fillOpacity="0.3" />
      <path d="M55 61.5 Q60 66 65 61.5" stroke={INK} strokeWidth="1.8" fill="none" strokeLinecap="round" />
    </g>
  );
}

/** A labelled standing character ("Illustration of Tom, barista"), `width` px wide; `crop="head"` gives a
 *  square head-and-shoulders avatar (the crop follows the character's height). */
export function Character({ look, role, label, width, crop }: { look: Look; role: string; label: string; width: number; crop?: "head" }) {
  if (crop === "head") {
    const headY = 214 - (214 - 52) * look.height; // the head centre after scaling from the floor
    return (
      <svg viewBox={`16 ${headY - 40} 88 88`} width={width} height={width} role="img" aria-label={label}>
        <Figure look={look} kind={kindFor(role)} lead={isLead(role)} />
      </svg>
    );
  }
  return (
    <svg viewBox="0 0 120 220" width={width} height={(width * 220) / 120} role="img" aria-label={label}>
      <ellipse cx="60" cy="214" rx="27" ry="4" fill={INK} fillOpacity="0.08" />
      <Figure look={look} kind={kindFor(role)} lead={isLead(role)} />
    </svg>
  );
}

/** The empty spot at the end of the row: a dashed outline of a person. */
export function Silhouette({ width }: { width: number }) {
  return (
    <svg viewBox="0 0 120 220" width={width} height={(width * 220) / 120} aria-hidden>
      <g fill="none" stroke="#9aa3b5" strokeWidth="2" strokeDasharray="5 4" transform="translate(60 214) scale(0.93) translate(-60 -214)">
        <circle cx="60" cy="52" r="20" />
        <rect x="39" y="80" width="42" height="66" rx="15" />
        <rect x="46" y="146" width="12.5" height="62" rx="5" />
        <rect x="61.5" y="146" width="12.5" height="62" rx="5" />
      </g>
    </svg>
  );
}
