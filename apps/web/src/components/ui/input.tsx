import * as React from "react";

import { cn } from "@/lib/utils";

export const Input = React.forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(
  ({ className, type = "text", ...props }, ref) => (
    <input
      ref={ref}
      type={type}
      className={cn(
        "flex h-10 w-full border border-[#d1d8e6] bg-white px-3 font-sans text-base text-[#0a0a0a] placeholder:text-[#6e6e6b] focus-visible:border-[#0038a8] disabled:cursor-not-allowed disabled:opacity-50",
        className,
      )}
      {...props}
    />
  ),
);
Input.displayName = "Input";

export const Select = React.forwardRef<
  HTMLSelectElement,
  React.SelectHTMLAttributes<HTMLSelectElement>
>(({ className, children, ...props }, ref) => (
  <select
    ref={ref}
    className={cn(
      "flex h-10 w-full appearance-none border border-[#d1d8e6] bg-white bg-[linear-gradient(45deg,transparent_50%,#0a0a0a_50%),linear-gradient(135deg,#0a0a0a_50%,transparent_50%)] bg-[length:5px_5px,5px_5px] bg-[position:calc(100%-18px)_17px,calc(100%-13px)_17px] bg-no-repeat px-3 pr-9 font-sans text-base text-[#0a0a0a] focus-visible:border-[#0038a8] disabled:cursor-not-allowed disabled:opacity-50",
      className,
    )}
    {...props}
  >
    {children}
  </select>
));
Select.displayName = "Select";

export function Label({ className, ...props }: React.LabelHTMLAttributes<HTMLLabelElement>) {
  return (
    <label
      className={cn(
        "mb-1.5 block font-ui text-[12px] font-bold uppercase tracking-[0.08em] text-[#0a0a0a]",
        className,
      )}
      {...props}
    />
  );
}
