import * as React from "react";

import { cn } from "@/lib/utils";

const styles = {
  default: "border-[#0038a8] bg-[#0038a8] text-white",
  sun: "border-[#fcd116] bg-[#fcd116] text-[#00226e]",
  outline: "border-[#d1d8e6] bg-white text-[#0a0a0a]",
  muted: "border-[#d1d8e6] bg-[#f4f7fc] text-[#5a5a58]",
  success: "border-[#1f6b3a] bg-[#eaf5ee] text-[#1f6b3a]",
  warning: "border-[#9a6700] bg-[#fff8e1] text-[#6b4a00]",
  danger: "border-[#b42318] bg-[#fdf0ef] text-[#8f1c13]",
  ink: "border-[#0a0a0a] bg-[#0a0a0a] text-white",
} as const;

export function Badge({
  className,
  tone = "default",
  ...props
}: React.HTMLAttributes<HTMLSpanElement> & { tone?: keyof typeof styles }) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 border px-2 py-1 font-ui text-[11px] font-bold uppercase leading-none tracking-wide",
        styles[tone],
        className,
      )}
      {...props}
    />
  );
}
