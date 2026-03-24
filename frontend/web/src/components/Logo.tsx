interface LogoProps {
  size?: "sm" | "md" | "lg";
  variant?: "default" | "light";
  className?: string;
}

/** Stylized "M" mark for MileMind. */
function LogoMark({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 28 28"
      fill="none"
      className={className}
      aria-hidden="true"
    >
      <rect width="28" height="28" rx="6" fill="currentColor" />
      <path
        d="M7 20V10l4.5 6 3-6 4.5 6V10"
        stroke="white"
        strokeWidth="2.2"
        strokeLinecap="round"
        strokeLinejoin="round"
        fill="none"
      />
    </svg>
  );
}

const SIZES = {
  sm: { icon: "w-6 h-6", text: "text-lg", gap: "gap-1.5" },
  md: { icon: "w-8 h-8", text: "text-xl", gap: "gap-2" },
  lg: { icon: "w-10 h-10", text: "text-3xl", gap: "gap-2.5" },
} as const;

export function Logo({ size = "md", variant = "default", className = "" }: LogoProps) {
  const s = SIZES[size];
  const iconColor = variant === "light" ? "text-blue-300" : "text-blue-600";
  const textColor = variant === "light" ? "text-white" : "";
  const accentColor = variant === "light" ? "text-blue-300" : "text-blue-600";
  return (
    <span className={`inline-flex items-center ${s.gap} ${className}`}>
      <LogoMark className={`${s.icon} ${iconColor}`} />
      <span className={`${s.text} font-bold tracking-tight ${textColor}`}>
        Mile<span className={accentColor}>Mind</span>
      </span>
    </span>
  );
}

export function LogoIcon({ className = "" }: { className?: string }) {
  return <LogoMark className={`text-blue-600 ${className}`} />;
}
