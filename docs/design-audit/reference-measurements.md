# BetterGov Fellowship — measured reference tokens

**Reference:** https://fellowship.bettergov.ph/  
**Inspected:** 14 November 2026, real Chromium session via Playwright 1.65.1 (headless, deviceScaleFactor 1).  
**Evidence:** `docs/design-audit/reference/computed-styles.json`, screenshots in the same directory.  
**Purpose:** extract the *visual system* (fonts, colours, geometry, states), not the Fellowship layout or content.

> The PhilFacilities application uses these values as its design language. It does **not** copy the Fellowship
> page structure, campaign sections, copy, logo, or information architecture. See `docs/08-REFERENCE-DESIGN-SYSTEM.md`.

## 1. Font loading and evidence

The reference loads three Google Fonts families in a single stylesheet request:

```
https://fonts.googleapis.com/css2?family=Archivo:wdth,wght@75..125,400..900
  &family=Inter:wght@400..900
  &family=Inter+Tight:wght@400..900&display=swap
```

Observed font network requests (woff2, variable subsets):

- `https://fonts.gstatic.com/s/archivo/v25/k3kQo8UDI-1M0wlSfdnoLg.woff2`
- `https://fonts.gstatic.com/s/inter/v20/UcC73FwrK3iLTeHuS_nVMrMxCp50SjIa1ZL7.woff2`
- `https://fonts.gstatic.com/s/intertight/v9/NGSwv5HMAFg6IuGlBNMjxLsH8ag.woff2`
- `https://fonts.gstatic.com/s/intertight/v9/NGSwv5HMAFg6IuGlBNMjxLsJ8ah8QA.woff2`

Computed families:

| Role | Reference value | Evidence | PhilFacilities token |
|---|---|---|---|
| Display / headings | `"Inter Tight", Arial, sans-serif` | `h1`–`h3`, brand product, `.fs-title` | `--font-display` |
| Body / long copy | `Archivo, Arial, sans-serif` | `body`, `.fs-lede`, sections | `--font-sans` |
| UI / labels / buttons | `"Inter", Arial, sans-serif` | nav links, buttons, eyebrows, tags | `--font-ui` |

Google Fonts hosts these families under the SIL Open Font License; the app loads the same families through
`next/font` (self-hosted at build time) so there is no runtime hotlink to the reference site.

## 2. Colours (computed / CSS custom properties)

| Token | Measured value | Evidence | Implemented token |
|---|---|---|---|
| Ink / primary background | `#0a0a0a` | body background, `.fs` background | `--foreground`, `--ink` |
| Paper | `#ffffff` | `.t-paper --bg`, text on ink surfaces | `--background`, `--card` |
| Wash | `#f4f7fc` | `.t-wash --bg` | `--secondary`, `--muted` |
| Muted text | `#5a5a58` | `.fs --muted` | `--muted-foreground` |
| Muted light | `#6e6e6b` | `.fs --muted-light` | `--muted-foreground` (secondary) |
| Rule on paper | `#d1d8e6` | `.fs --rule-paper` | `--border`, `--input` |
| Blue | `#0038a8` | `.fs --blue`, `.t-blue` background | `--primary` |
| Blue dark | `#002b82` | `.fs --blue-dark` | `--primary-hover` |
| Blue deep / header | `#00226e` | `theme-color`, header background at 94% opacity | `--header-background` |
| Blue glow | `#0b4fd1` | `.fs --blue-glow` | accent support |
| Blue bright | `#0096ff` | `.t-ink --accent`, inline links on ink | `--accent` |
| Sun | `#fcd116` | `.fs --sun`, primary CTA, eyebrow accents | `--primary-cta`, `--ring` |
| Sun light | `#ffe066` | `.fs --sun-light` | `--accent-foreground` highlight |
| Focus outline | `#ffcf4a` | `a:focus-visible` rule | `--focus-ring` |
| Selection | `#e8f1ff` | `::selection` rule | `--selection` |

Computed header background: `rgba(0, 34, 110, 0.94)` with a `1px` bottom border.
Computed body text on ink surfaces: `#ffffff`; secondary on ink: `rgb(255 255 255 / 66–82%)`.

## 3. Typography scale

Measured at 1440px / 1024px / 768px / 390px. The reference uses fluid `clamp()` display type.

| Element | 1440px | 1024px | 768px | 390px | Notes |
|---|---|---|---|---|---|
| Hero `h1` | 151.2px / 130.03px, weight 800 | 107.52 / 92.47 | 80.64 / 69.35 | 52.65 / 45.28 | `Inter Tight`, tight leading (0.86) |
| Section `h2` | 106.56 / 98.04, weight 800 | 75.78 / 69.71 | 56.83 / 52.29 | 48 / 44.16 | `Inter Tight` |
| Card `h3` | 23.04 / 24.88, weight 700 | 20 / 21.6 | 20 / 21.6 | 20 / 21.6 | `Inter Tight` |
| Lede | 21.6 / 32.4, weight 400 | 16 / 24 | 16 / 24 | 16 / 24 | `Archivo` |
| Body | 16 / 24.8, weight 400 | 16 / 24.8 | 16 / 24.8 | 16 / 24.8 | `Archivo` |
| Eyebrow / label | 12.24 / 14.69, weight 700 | 11 / 13.2 | 11 / 13.2 | 11 / 13.2 | `Inter`, uppercase with rule |
| Nav link | 15 / 15, weight 600 | 15 / 15 | 15 / 15 | 17 / 17 (mobile menu) | `Inter` |
| Button | 15 / 18, weight 700 | 15 / 18 | 15 / 18 | 15 / 18 | `Inter` |
| Tag | 12.24 / 12.24, weight 700 | 11 / 11 | 11 / 11 | 11 / 11 | `Inter` |

Measured CSS custom properties: `--fs-label: clamp(.6875rem, .85vw, .875rem)`,
`--fs-lede: clamp(1.0625rem, 1.5vw, 1.4375rem)`.

## 4. Layout and geometry

| Token | 1440px | 1024px | 768px | 390px | Implemented token |
|---|---|---|---|---|---|
| Header height | 68px | 68px | 68px | 60px | `--header-height` (68px; 60px < 480px) |
| Horizontal padding | 86.4px | 61.44px | 46.08px | 23.4px | `clamp(1.25rem, 6vw, 7.5rem)` |
| Nav gap | 28.8px | 20.48px | 15.36px | 8px | `--nav-gap` |
| Brand logo height | 40px | 40px | 40px | 26px | header component |
| Brand product gap | 16px | 12.29px | 9.6px | 9.6px | header component |
| Brand product size | 18.72px / 700 | 16 / 700 | 16 / 700 | 15 / 700 | header component |
| Button height | 40px | 40px | 40px | 40px | `Button size=sm/default` |
| Button padding | 0 16px | 0 16px | 0 16px | 0 16px | `--button-px` |
| Button border | 1px solid | 1px solid | 1px solid | 1px solid | `--button-border` |
| Radius | 0px (all buttons, tags, cards, inputs) | 0 | 0 | 0 | `--radius: 0` |
| Section vertical padding | 60px top | 60px | 60px | 50.64px | `--section-py` |
| Menu link height | — | — | — | 52px | mobile menu |

The reference deliberately uses **square corners** for buttons, tags, and boxes. Do not round them into
default shadcn pills. Panels may use `1px` rules instead of shadows.

## 5. Component measurements and states

### Header / navigation

- Sticky header, full width, deep blue at 94% opacity, `1px` bottom rule, height 68px (60px mobile).
- Wordmark at left: white BetterGov logomark + `Fellowship` product label in sun yellow, separated by a
  `1px` vertical rule and 16px gap. **PhilFacilities will use its own original wordmark and product label.**
- Desktop nav starts after the brand: five uppercase-free text links, `Inter 15px/600`, colour
  `rgb(255 255 255 / 78%)`; 28.8px gap at 1440px.
- Secondary action: 40px-high ghost button, transparent background, white text, `1px` white border,
  `Inter 15px/700`, 16px horizontal padding.
- Primary action: 40px-high sun-yellow button, near-black text, `1px` border, same padding.
- Hover link colour: white; focus-visible: `3px solid #ffcf4a`, `outline-offset: 3px`.
- Breakpoint: desktop links/actions hidden at 1024px and below; a 40px-high ghost “Menu” button appears.
  At 390px the open menu is a 393px-tall full-width panel under a 60px header, with 52px-high ruled rows,
  `Inter 17px/600` labels, and a trailing arrow. The trigger label changes to “Close”.

### Buttons

| Variant | Background | Text | Border | Height | Radius |
|---|---|---|---|---|---|
| Sun / primary | `#fcd116` | `#0a0a0a` | `1px solid` (same hue) | 40px | 0 |
| Ghost / secondary | transparent | `#ffffff` | `1px solid rgb(255 255 255 / 40%)` | 40px | 0 |
| Light (on blue) | `#ffffff` | `#00226e` | `1px solid #ffffff` | 40px | 0 |

### Tags / chips

- Sun background `#fcd116`, blue text `#0038a8`, `Inter 11px/700`, square, padding ~4px 8px.
- Used sparingly for status/freshness, never as a substitute for a quality explanation.

### Rules and surfaces

- Paper sections: white background, `#d1d8e6` 1px rules, dark text.
- Ink sections: `#0a0a0a` background, white text, 22% white rules, blue-bright accent.
- Wash sections: `#f4f7fc` background.
- No soft drop shadows or glassmorphism in the measured system.

## 6. Motion

- Easing token: `cubic-bezier(.16, 1, .3, 1)` (measured `--ease-out`).
- Reference entrance animations are marketing motion; PhilFacilities uses only subtle hover/focus transitions.
- `prefers-reduced-motion: reduce` disables animation/transition durations globally in the reference;
  PhilFacilities implements the same media query.

## 7. Accessibility observations

- Global focus ring: `3px solid #ffcf4a`, offset `3px`; visible on dark and light surfaces.
- Skip link: fixed top-left, sun-yellow background, 2px dark border, appears on focus.
- `prefers-reduced-motion` support.
- Contrast: white on `#00226e` / `#0038a8` and near-black on `#fcd116` pass WCAG AA for normal text.
  Muted text `#5a5a58` on white passes AA at normal sizes; use it only at ≥16px / non-critical text.
- The reference’s huge display type is not appropriate for dense directory data; PhilFacilities caps
  page-title sizes for legibility while keeping the same family, weight, and square/rule language.

## 8. Deliberate PhilFacilities deviations

| Reference | PhilFacilities | Reason |
|---|---|---|
| Editorial full-bleed hero at 151px | Page titles 32–56px, compact hero | Directory/map application must fit above the fold |
| Fellowship nav labels and CTAs | Directory, Map, Data & Sources, API, About + “Explore map” | Product IA, not campaign IA |
| BetterGov logomark | Original PhilFacilities mark | Trademark and asset boundary |
| Long-scroll marketing sections | Application shell, split views, dense tables | Task-oriented data product |
| Large decorative rays/grids | Restrained blue field on map/hero only | Keep data legible |

## 9. Implementation mapping

- CSS variables live in `apps/web/src/app/globals.css`; Tailwind v4 `@theme inline` maps them to utilities.
- shadcn/ui primitives live in `apps/web/src/components/ui`; visual overrides preserve 0 radius, 1px rules,
  40px controls, and the measured focus ring.
- `Header` component implements 68px/60px geometry, desktop link row, ghost/primary actions, and a
  full-width mobile menu panel with 52px rows.
- Fonts are loaded with `next/font/google` for Inter Tight, Archivo, and Inter, with `display: swap`.
