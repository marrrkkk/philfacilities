import { cva, type VariantProps } from "class-variance-authority";
import * as React from "react";

import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "inline-flex h-10 items-center justify-center gap-2 whitespace-nowrap border px-4 font-ui text-[15px] font-bold leading-[18px] transition-colors disabled:pointer-events-none disabled:opacity-50 [&_svg]:size-4 [&_svg]:shrink-0",
  {
    variants: {
      variant: {
        primary: "border-[#fcd116] bg-[#fcd116] text-[#0a0a0a] hover:bg-[#ffe066]",
        blue: "border-[#0038a8] bg-[#0038a8] text-white hover:bg-[#002b82]",
        outline: "border-[#d1d8e6] bg-white text-[#0a0a0a] hover:border-[#0038a8] hover:text-[#0038a8]",
        ghost: "border-transparent bg-transparent text-current hover:bg-black/5",
        light: "border-white bg-white text-[#00226e] hover:bg-[#f4f7fc]",
        headerGhost: "border-white/40 bg-transparent text-white hover:border-white hover:bg-white/10",
        destructive: "border-[#b42318] bg-[#b42318] text-white hover:bg-[#8f1c13]",
        link: "h-auto border-transparent bg-transparent p-0 font-sans text-[#0038a8] underline underline-offset-4 hover:text-[#002b82]",
      },
      size: {
        default: "h-10 px-4",
        sm: "h-9 px-3 text-sm",
        lg: "h-12 px-6 text-base",
        icon: "size-10 px-0",
      },
    },
    defaultVariants: {
      variant: "primary",
      size: "default",
    },
  },
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, type = "button", ...props }, ref) => (
    <button
      ref={ref}
      type={type}
      className={cn(buttonVariants({ variant, size }), className)}
      {...props}
    />
  ),
);
Button.displayName = "Button";

export { buttonVariants };
