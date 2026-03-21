const VARIANTS = {
  approved: "bg-green-100 text-green-800",
  unapproved: "bg-yellow-100 text-yellow-800",
  active: "bg-blue-100 text-blue-800",
  archived: "bg-gray-100 text-gray-600",
  rejected: "bg-yellow-100 text-yellow-800",
  error: "bg-red-100 text-red-800",
} as const;

type StatusVariant = keyof typeof VARIANTS;

interface StatusBadgeProps {
  variant: StatusVariant;
  label?: string;
  pill?: boolean;
}

export function StatusBadge({ variant, label, pill }: StatusBadgeProps) {
  const classes = VARIANTS[variant];
  const shape = pill ? "rounded-full px-3 py-1" : "rounded px-2 py-0.5";
  const displayLabel = label ?? variant;

  return (
    <span className={`inline-block text-xs font-medium ${shape} ${classes}`}>
      {displayLabel}
    </span>
  );
}
