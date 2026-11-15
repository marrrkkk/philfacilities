# 08 — Reference Design System: BetterGov Fellowship → shadcn/ui + Tailwind

## 1. Design requirement

**Reference website:** https://fellowship.bettergov.ph/

The PhilFacilities web app must reproduce the reference website's visual design system as closely as technically possible:

- exact font families and available weights;
- typography scale, font sizes, line heights, letter spacing, and text transformations;
- color palette, neutral surfaces, borders, text colors, accent colors, and semantic states;
- navigation/header appearance, sizing, spacing, hover/focus/active states, mobile menu treatment, and CTA styling;
- button shapes, heights, padding, borders, hover/focus states;
- card/surface, divider, icon, radius, shadow, and spacing language;
- responsive typography and navigation behavior.

**Do not copy the reference site's page layout, content sections, fellowship cards, or information architecture.** Create a best-fit data-directory and map application layout as specified in [Web Product and UX](07-WEB-PRODUCT-UX.md).

Do not invent or approximate tokens from memory. Reverse-engineer the live reference first and document measured values.

## 2. What the page inspection already establishes

The live page was opened during planning on 14 November 2026. Its textual navigation structure shows:

- Brand/entry link: “Fellowship”.
- Primary links: “Challenges”, “Who can apply”, “Support”, “Timeline”, and an external “BetterGov.ph” link.
- Actions: “Contribute” and “Apply”.
- A mobile “Menu” control, with an expanded menu containing the main links and action links.

These are the site-specific labels and interaction structure visible in the page. For PhilFacilities, adapt the labels to the product while reproducing the header's visual treatment and responsive behavior. Do not copy fellowship wording or CTA destinations.

Reference URL: https://fellowship.bettergov.ph/

## 3. Mandatory reverse-engineering procedure for the coding agent

Complete this design audit before implementing the production UI.

### Step A — Inspect the live site in a real browser

Use Chromium/Playwright or browser developer tools. Do not rely only on search snippets or a textual page scrape.

Capture the reference at minimum:

- 1440px desktop width;
- 1024px tablet/compact desktop;
- 768px tablet;
- 390px mobile.

Capture at least:

- top of page with full header;
- mobile header before and after opening the menu;
- a representative body section with heading, paragraph, card/list, and buttons;
- footer;
- hover, focus, active, and open states where relevant.

### Step B — Inspect actual styles

Use DevTools computed styles and loaded CSS/font resources to identify:

- `font-family`, actual font file, font weight, font style, and whether variable font;
- body font size, line height, letter spacing;
- heading sizes and line heights at each breakpoint;
- text color and background color in computed RGB/hex/OKLCH;
- border colors, widths, radii, and shadows;
- page/container max width and horizontal padding;
- navigation height, item gap, nav text size, link decoration, CTA height, radius and padding;
- mobile breakpoint and menu animation/state;
- spacing scale and repeated spacing values;
- icon library or SVG source and icon dimensions;
- button variants and disabled/focus states.

Inspect `:root` variables, imported CSS, stylesheet assets, and font network requests. Record exact source values where available. If values are inherited or transformed, record computed values at the element.

### Step C — Produce a measured token inventory

Create `docs/design-audit/reference-measurements.md` with:

| Token | Measured value | Evidence | Implemented token |
|---|---|---|---|
| Display font | exact family/file | computed style + font asset | `--font-display` |
| Body font | exact family/file | computed style + font asset | `--font-sans` |
| Primary text | exact color | computed style | `--foreground` |
| Muted text | exact color | computed style | `--muted-foreground` |
| Main background | exact color | computed style | `--background` |
| Accent | exact color | computed style | `--primary` |
| Border | exact color | computed style | `--border` |
| Heading scale | measured sizes/line heights | computed style by viewport | Tailwind typography tokens |
| Header height | px per breakpoint | element box metrics | header component |
| Content width | px / max-width | layout measurement | container utility |
| Radius | px | computed style | radius tokens |
| Button height | px | element box metrics | button variants |
| Nav gap/padding | px | element box metrics | header CSS |

Record confidence and viewport for every responsive measurement.

### Step D — Implement the measured system in shadcn/ui and Tailwind

1. Initialize shadcn/ui in `apps/web` using its Tailwind-compatible setup.
2. Define the measured visual values as CSS custom properties in the app's global stylesheet.
3. Map those values to shadcn semantic variables (background, foreground, card, popover, primary, secondary, muted, accent, destructive, border, input, ring, radius, chart colors as needed).
4. Configure Tailwind theme tokens to reference those variables; avoid duplicate hardcoded colors in components.
5. Create reference-matched typography utilities and button variants.
6. Implement a custom header/nav component reproducing the observed reference geometry and states while using PhilFacilities navigation labels.
7. Use shadcn primitives for accessible behavior, then override visual styling to match the reference.
8. Avoid default shadcn appearance where it diverges from the source.

### Step E — Visual regression

Use Playwright screenshots for the PhilFacilities web app at the same viewports. Compare:

- font appearance and wrapping;
- header height/alignment and link spacing;
- button dimensions and border/radius;
- color values and contrast;
- focus/hover states;
- responsive menu behavior.

Create screenshots or visual notes under `docs/design-audit/` (do not commit proprietary reference assets unless permitted). Record material deviations and why they are necessary for map/list usability or accessibility.

## 4. Navigation implementation requirements

Replicate the reference site's navigation treatment and behavior, not its fellowship-specific labels.

Suggested PhilFacilities items:

- Directory
- Map
- Data & Sources
- API
- About

Use the reference's brand/wordmark placement, nav typography, horizontal rhythm, CTA styling, mobile menu trigger, menu panel spacing, and interaction states. Adapt the mobile menu contents to PhilFacilities. Do not invent a new unrelated dashboard-style sidebar as the global site navigation.

The directory page may have its own contextual filter sidebar; that is part of the application layout, not a replacement for the global site header.

## 5. Layout is intentionally different

The BetterGov Fellowship page uses an editorial/fellowship landing-page structure. Do not reproduce its long numbered content sections, challenge cards, or fellowship timeline.

PhilFacilities needs product layouts:

- searchable directory with filter/results panel;
- split-view map and result list;
- map-first discovery view;
- dense but readable facility profile;
- dataset/source tables;
- developer/API documentation entry points.

The visual language is borrowed; the information architecture is designed for PhilFacilities.

## 6. Asset and trademark boundaries

- Do not copy the BetterGov logo, Fellowship logo, text, pitch images, or branded campaign assets into PhilFacilities.
- Do not hotlink reference-site assets.
- Identify font licensing and use the same font files only if their license/hosting terms allow that use. If a font is externally hosted, verify whether self-hosting is permitted.
- Recreate visual tokens and interaction patterns in original PhilFacilities components.
- The PhilFacilities wordmark and icon must be original.

## 7. Completion gate

Do not mark design implementation complete until:

- [x] Real browser inspection completed (M0-07; screenshots in `docs/design-audit/reference/`).
- [x] Measurements and evidence recorded in `reference-measurements.md`.
- [x] Font assets and licenses checked (Inter Tight, Archivo, and Inter are SIL Open Font License families; self-hosted through `next/font`).
- [x] Colors and typography mapped to shadcn/Tailwind tokens (`apps/web/src/app/globals.css`).
- [x] Header desktop and mobile states visually compared (`docs/design-audit/implementation/`).
- [x] Product-specific directory/map layouts implemented.
- [x] Keyboard/focus states work (Playwright: skip link, nav focus ring, keyboard search, Escape-to-close, focus return).
- [x] Responsive screenshots reviewed at 390, 768, 1024, 1440, and 1920px.
- [x] Deviations from the reference documented (section 8 above and the implementation notes).

**If the reference site cannot be inspected in a real browser, do not guess the fonts, colors, or sizes. Ask for supplied screenshots or continue only with a clearly marked temporary neutral theme.**
