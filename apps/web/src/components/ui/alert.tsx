import * as React from "react";

import { cn } from "@/lib/utils";

export function Alert({
  className,
  tone = "info",
  ...props
}: React.HTMLAttributes<HTMLDivElement> & { tone?: "info" | "warning" | "danger" | "success" }) {
  const tones = {
    info: "border-[#0038a8] bg-[#f4f7fc] text-[#0a0a0a]",
    warning: "border-[#9a6700] bg-[#fff8e1] text-[#3d2b00]",
    danger: "border-[#b42318] bg-[#fdf0ef] text-[#5c110b]",
    success: "border-[#1f6b3a] bg-[#eaf5ee] text-[#123d22]",
  } as const;
  return <div role="note" className={cn("border-l-4 p-4", tones[tone], className)} {...props} />;
}

export function AlertTitle({ className, ...props }: React.HTMLAttributes<HTMLHeadingElement>) {
  return <p className={cn("mb-1 font-ui text-sm font-bold", className)} {...props} />;
}

export function AlertDescription({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("font-sans text-sm leading-relaxed", className)} {...props} />;
}
