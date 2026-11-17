# Design system

**Reference:** https://fellowship.bettergov.ph/
**Audit evidence:** [`docs/design-audit/reference-measurements.md`](design-audit/reference-measurements.md), `docs/design-audit/reference/`, `docs/design-audit/implementation/`
**Implementation:** `apps/web/src/app/globals.css`, `apps/web/src/components/`

PhilFacilities borrows the reference's **visual language** — type, colour, geometry, header treatment, focus states — and not its page structure, content, campaign graphics, fellowship information architecture, or assets. The product layout is a task-oriented directory, map, and facility profile.

## 1. Mandatory rule

Before production UI work, inspect the live reference in a real browser and record measurements. Do not guess tokens from memory, screenshots, or search snippets.

If the reference cannot be inspected:

- ask for screenshots or a supplied measurement sheet; or
- continue only with a clearly marked temporary neutral theme.

The completed audit measured fonts, colours, type scale, header geometry, button states, movement, and responsive menu behavior. Re-measure before assuming a value is still current.

## 2. Fonts

| Role | Family | Token | Implementation |
|---|---|---|---|
| Display / headings | Inter Tight | `--font-display` | `next/font/google`, self-hosted at build |
| Body / long copy | Archivo | `--font-sans` | `next/font/google`, self-hosted at build |
| UI / labels / buttons | Inter | `--font-ui` | `next/font/google`, self-hosted at build |

All three families are SIL Open Font License. They are loaded through `next/font` with `display: swap`, not hotlinked from the reference.

## 3. Colour tokens

Implemented in `apps/web/src/app/globals.css`.

| Token | Value | Use |
|---|---|---|
| `--background` | `#ffffff` | Page and card paper |
| `--foreground` | `#0a0a0a` | Primary text and ink surfaces |
| `--primary` | `#0038a8` | Primary blue action and links |
| `--primary-hover` | `#002b82` | Hover state |
| `--secondary` / `--muted` | `#f4f7fc` | Wash surfaces |
| `--muted-foreground` | `#5a5a58` | Secondary text |
| `--accent` / `--sun` | `#fcd116` | Primary CTA, tags, emphasis |
| `--border` / `--input` | `#d1d8e6` | Rules, borders, inputs |
| `--ring` | `#ffcf4a` | Focus ring, `3px` offset `3px` |
| `--header-background` | `#00226e` | Sticky header |
| `--destructive` | `#b42318` | Errors and destructive state |
| `--selection` | `#e8f1ff` | Text selection |

The header is rendered at `rgba(0,34,110,0.94)` with a `1px` bottom rule. Ink sections use `#0a0a0a` with white text. Do not introduce a second palette for new components.

## 4. Typography

Measured reference scale (abridged; full viewport table in the audit):

| Element | 1440px | 390px | Notes |
|---|---|---|---|
| Hero `h1` | 151.2 / 130.03, 800 | 52.65 / 45.28, 800 | Reference uses fluid `clamp()`; PhilFacilities caps page titles at 32–56px |
| Section `h2` | 106.56 / 98.04, 800 | 48 / 44.16 | Inter Tight |
| Card `h3` | 23.04 / 24.88, 700 | 20 / 21.6 | Inter Tight |
| Lede | 21.6 / 32.4, 400 | 16 / 24 | Archivo |
| Body | 16 / 24.8, 400 | 16 / 24.8 | Archivo |
| Eyebrow | 12.24 / 14.69, 700 | 11 / 13.2 | Inter, uppercase, rule |
| Nav link | 15 / 15, 600 | 17 / 17 in mobile menu | Inter |
| Button | 15 / 18, 700 | 15 / 18 | Inter |
| Tag | 12.24 / 12.24, 700 | 11 / 11 | Inter |

Implementation rules:

- Headings use `font-display` with tight tracking (`-0.02em`) and balanced wrapping.
- Body copy uses `font-sans`, 16px minimum, 1.55 line height.
- Labels, buttons, and navigation use `font-ui`.
- Muted text `#5a5a58` is for secondary information at ≥16px, not critical text.
- Do not reproduce the reference's 151px editorial hero in a dense directory screen.

## 5. Geometry

| Token / element | Value |
|---|---|
| Radius | `0` for buttons, tags, cards, inputs (`--radius-*: 0`) |
| Header height | `68px`; `60px` below 480px |
| Horizontal padding | `clamp(1.25rem, 6vw, 7.5rem)` |
| Button height | `40px` |
| Button padding | `0 16px` |
| Button border | `1px solid` |
| Content max width | `96rem` via `.container-page` |
| Section vertical padding | `60px`; `50.64px` on small screens |
| Mobile menu row | `52px`, ruled |

Keep square corners and 1px rules. Do not round controls into default shadcn pills. Panels use rules, not soft shadows.

## 6. Header and navigation

`apps/web/src/components/site-header.tsx` reproduces the reference header treatment with PhilFacilities labels:

- sticky full-width deep-blue header at 94% opacity with a 1px bottom rule;
- original PF mark and PhilFacilities wordmark — never the BetterGov or Fellowship logo;
- desktop links: Directory, Map, Data & Sources, API, About;
- active link: white text, sun-yellow underline;
- primary “Browse facilities” action in sun yellow;
- desktop links/actions hide at 1024px and below; a 40px ghost Menu button replaces them;
- mobile menu is a full-width panel under the header with 52px ruled rows, 17px labels, trailing arrows, and a primary action;
- Menu changes to Close, `aria-expanded`/`aria-controls` are set, Escape closes and returns focus to the trigger.

Do not replace the global header with a dashboard sidebar. A directory filter sidebar is a page-level control, not global navigation.

## 7. Components

Use shadcn/ui primitives for accessible behavior, then apply the measured visual system. Local primitives live in `apps/web/src/components/ui/`.

| Component | Rule |
|---|---|
| Button | 40px high, square, 1px border, Inter 15/700. Variants: primary sun, blue, outline/ghost, link |
| Input / Select | Square, 1px `#d1d8e6` border, visible `--ring` focus |
| Badge / tag | Square, restrained semantic colour; never use colour alone to convey quality |
| Card | White surface, 1px rule, no drop shadow |
| Alert | Left rule or square border, explicit title and description |
| Table | Wash header, 1px row rules, horizontally scrollable region with keyboard focus |
| Breadcrumbs | Text links, current page not linked |
| Map panel | Map canvas with a separate accessible result list |

Do not use default shadcn styling where it diverges from the reference (especially radius, shadows, and control height).

## 8. Motion

- Easing: `cubic-bezier(.16, 1, .3, 1)`.
- Use only subtle hover/focus transitions; the reference's marketing entrance animations are not part of the product shell.
- `prefers-reduced-motion: reduce` disables animation and transition durations globally.

## 9. Accessibility

- WCAG 2.2 AA target.
- Global focus ring: `3px solid #ffcf4a`, offset `3px`. It must remain visible on both paper and ink surfaces.
- Skip link appears on focus.
- Header and mobile menu are keyboard-operable; Escape closes with focus return.
- Form controls always have labels; icons are `aria-hidden` unless they carry meaning.
- Map results have a text alternative.
- Precision, quality, and status are not conveyed by colour alone.
- Contrast: white on `#00226e`/`#0038a8` and near-black on `#fcd116` pass AA for normal text.

## 10. Deliberate deviations

| Reference | PhilFacilities | Reason |
|---|---|---|
| Editorial full-bleed hero at 151px | Page titles 32–56px, compact hero | Directory/map task must fit above the fold |
| Fellowship labels and CTAs | Directory, Map, Data & Sources, API, About | Product information architecture |
| BetterGov/Fellowship marks | Original PF mark and wordmark | Trademark and asset boundary |
| Long-scroll campaign sections | Application shell, split views, tables | Task-oriented data product |
| Decorative rays/grids | Restrained blue field on hero/map only | Keep data legible |

## 11. Changing the design

1. Re-inspect the reference at 1440, 1024, 768, and 390px if the change depends on a reference value.
2. Record new measurements and evidence in `docs/design-audit/reference-measurements.md`.
3. Change tokens in `apps/web/src/app/globals.css`, not ad hoc component colours.
4. Update the relevant primitive or layout.
5. Run the checks:

```bash
pnpm lint
pnpm typecheck
pnpm build
pnpm --filter @philfacilities/web test:e2e
pnpm --filter @philfacilities/web capture:responsive
pnpm --filter @philfacilities/web check:responsive
```

The E2E suite checks the measured focus ring, header geometry, mobile navigation, accessibility, CSP, and precision labels. A visual change that breaks those assertions is not complete.
