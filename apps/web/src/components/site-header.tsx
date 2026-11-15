"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useId, useRef, useState } from "react";
import { ArrowUpRight, Menu, X } from "lucide-react";

import { cn } from "@/lib/utils";
import { buttonVariants } from "@/components/ui/button";

const links = [
  { href: "/directory", label: "Directory" },
  { href: "/map", label: "Map" },
  { href: "/data", label: "Data & Sources" },
  { href: "/api", label: "API" },
  { href: "/about", label: "About" },
];

function BrandMark() {
  return (
    <span className="relative inline-flex size-10 shrink-0 items-center justify-center border border-white/70 bg-white text-[#00226e]">
      <span className="font-display text-[15px] font-extrabold leading-none tracking-tight">PF</span>
      <span aria-hidden="true" className="absolute -right-1 -top-1 size-2 bg-[#fcd116]" />
    </span>
  );
}

export function SiteHeader() {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const panelId = useId();
  const menuButtonRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!open) return;

    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      setOpen(false);
      menuButtonRef.current?.focus();
    };

    document.addEventListener("keydown", closeOnEscape);
    return () => document.removeEventListener("keydown", closeOnEscape);
  }, [open]);

  const isActive = (href: string) =>
    pathname === href || (href !== "/" && pathname.startsWith(`${href}/`));

  return (
    <header className="sticky top-0 z-50 border-b border-white/15 bg-[rgba(0,34,110,0.94)] text-white backdrop-blur-md">
      <div className="container-page flex h-[var(--header-height)] items-center gap-3">
        <Link
          href="/"
          className="flex min-w-0 items-center gap-3 text-white no-underline"
        >
          <BrandMark />
          <span className="hidden items-center gap-3 sm:flex">
            <span aria-hidden="true" className="h-8 w-px bg-white/30" />
            <span className="font-display text-lg font-bold leading-none tracking-tight">
              Phil<span className="text-[#fcd116]">Facilities</span>
            </span>
          </span>
        </Link>

        <nav aria-label="Main navigation" className="ml-6 hidden items-center gap-7 nav:flex">
          {links.map((link) => (
            <Link
              key={link.href}
              href={link.href}
              aria-current={isActive(link.href) ? "page" : undefined}
              className={cn(
                "font-ui text-[15px] font-semibold leading-none text-white/80 no-underline transition-colors hover:text-white",
                isActive(link.href) && "text-white underline decoration-[#fcd116] decoration-2 underline-offset-8",
              )}
            >
              {link.label}
            </Link>
          ))}
        </nav>

        <div className="ml-auto flex items-center gap-2">
          <Link
            href="/directory"
            className={cn(buttonVariants({ variant: "primary" }), "hidden no-underline nav:inline-flex")}
          >
            Browse facilities
          </Link>
          <button
            ref={menuButtonRef}
            type="button"
            className="inline-flex h-10 items-center gap-2 border border-white/40 bg-transparent px-3 font-ui text-[15px] font-bold text-white hover:border-white hover:bg-white/10 nav:hidden"
            aria-expanded={open}
            aria-controls={panelId}
            onClick={() => setOpen((value) => !value)}
          >
            {open ? <X aria-hidden="true" className="size-4" /> : <Menu aria-hidden="true" className="size-4" />}
            {open ? "Close" : "Menu"}
          </button>
        </div>
      </div>

      {open ? (
        <div id={panelId} className="border-t border-white/15 bg-[#00226e] nav:hidden">
          <nav aria-label="Mobile navigation" className="container-page flex flex-col">
            {links.map((link) => (
              <Link
                key={link.href}
                href={link.href}
                aria-current={isActive(link.href) ? "page" : undefined}
                onClick={() => setOpen(false)}
                className="flex min-h-[52px] items-center justify-between border-b border-white/15 font-ui text-[17px] font-semibold text-white no-underline"
              >
                {link.label}
                <ArrowUpRight aria-hidden="true" className="size-4 text-white/60" />
              </Link>
            ))}
            <Link
              href="/directory"
              onClick={() => setOpen(false)}
              className="my-4 inline-flex h-10 items-center justify-center border border-[#fcd116] bg-[#fcd116] px-4 font-ui text-[15px] font-bold text-[#0a0a0a] no-underline"
            >
              Browse facilities
            </Link>
          </nav>
        </div>
      ) : null}
    </header>
  );
}
