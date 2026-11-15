import Link from "next/link";

const groups = [
  {
    title: "Product",
    links: [
      { href: "/directory", label: "Facility directory" },
      { href: "/map", label: "Map" },
      { href: "/data", label: "Data & sources" },
      { href: "/status", label: "Status" },
    ],
  },
  {
    title: "Developers",
    links: [
      { href: "/api", label: "API overview" },
      { href: "/api#examples", label: "Request examples" },
      { href: "/data/dictionary", label: "Data dictionary" },
      { href: "/data", label: "Dataset catalogue" },
    ],
  },
  {
    title: "Project",
    links: [
      { href: "/about", label: "About & governance" },
      { href: "/about#corrections", label: "Report a correction" },
      { href: "/about#licensing", label: "Licensing" },
    ],
  },
];

export function SiteFooter() {
  return (
    <footer className="mt-auto border-t border-white/20 bg-[#0a0a0a] text-white">
      <div className="container-page py-12">
        <div className="grid gap-10 lg:grid-cols-[1.6fr_1fr_1fr_1fr]">
          <div>
            <p className="font-display text-2xl font-extrabold tracking-tight">
              Phil<span className="text-[#fcd116]">Facilities</span>
            </p>
            <p className="mt-3 max-w-sm font-sans text-sm leading-relaxed text-white/70">
              An open, source-linked registry of Philippine schools and health facilities.
              Canonical records keep their source evidence, reference periods, and quality
              caveats attached.
            </p>
            <p className="mt-4 border-l-2 border-[#fcd116] pl-3 font-sans text-xs leading-relaxed text-white/60">
              Coverage is partial and source-specific. Check each record&apos;s provenance and
              publication status. A crowd-sourced or generated record is never an official
              government record.
            </p>
          </div>
          {groups.map((group) => (
            <nav key={group.title} aria-label={group.title}>
              <p className="eyebrow text-white/60">{group.title}</p>
              <ul className="mt-4 space-y-2">
                {group.links.map((link) => (
                  <li key={link.href}>
                    <Link
                      href={link.href}
                      className="font-sans text-sm text-white/85 no-underline hover:text-white hover:underline"
                    >
                      {link.label}
                    </Link>
                  </li>
                ))}
              </ul>
            </nav>
          ))}
        </div>
        <div className="mt-10 flex flex-col gap-3 border-t border-white/20 pt-6 font-ui text-xs text-white/55 sm:flex-row sm:items-center sm:justify-between">
          <p>Code licensed Apache-2.0. Data rights vary by source and release.</p>
          <p>Built as reusable public data infrastructure. Independent of any agency.</p>
        </div>
      </div>
    </footer>
  );
}
