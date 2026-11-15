# PhilFacilities implementation screenshots

**Captured:** 15 November 2026  
**Build:** local production build (`pnpm --filter @philfacilities/web build && pnpm --filter @philfacilities/web start`)  
**URL:** `http://127.0.0.1:3000`  
**Data at capture time:** deterministic synthetic demo (22 published facilities; 15 with coordinates). The screenshots are a historical layout record; the current working database serves real data with recorded publication decisions (61,806 public facilities as of 15 November 2026).  
**Commands:**

```bash
pnpm --filter @philfacilities/web capture:responsive
pnpm --filter @philfacilities/web check:responsive
```

The capture script uses Playwright at a 1× device scale with reduced motion. It waits for headings and network idle on content pages, and for the map canvas plus the bounded viewport query on `/map`. The check script opens every public page at 390, 768, 1024, and 1440px and fails if the document is wider than the viewport. Its full output, screenshot dimensions, and SHA-256 values are recorded in `docs/operations/evidence/2026-11-15-responsive/audit.txt`.

| File | Viewport | Purpose |
|---|---|---|
| `home-390x844.png` | 390 × 844 | mobile header (60px), menu trigger, stacked hero, search |
| `home-768x1024.png` | 768 × 1024 | tablet header, mobile menu trigger, stacked sections |
| `home-1024x768.png` | 1024 × 768 | reference breakpoint: mobile menu, no desktop nav or header CTA |
| `home-1440x900.png` | 1440 × 900 | desktop header, directory/map/data product entry points |
| `home-1920x1080.png` | 1920 × 1080 | wide desktop measure and capped content width |
| `directory-390x844.png` | 390 × 844 | filters before results, single-column result list |
| `directory-1440x900.png` | 1440 × 900 | filter sidebar plus desktop result list |
| `map-390x844.png` | 390 × 844 | map-first mobile view, Map/List tabs, text-result access |
| `map-1440x900.png` | 1440 × 900 | split map and always-available text result list |

## Review notes

- The measured type pairing is visible: Inter Tight display headings, Archivo body copy, Inter UI labels. Controls use square corners, 40px heights, and the audited blue/sun palette.
- The header is 60px below 480px and 68px at wider sizes. At 1024px and below it shows the ghost **Menu** trigger and hides the desktop nav and **Browse facilities** CTA; keyboard users can open the panel, tab through 52px rows, and close it with Escape. At 1025px and above the desktop nav and CTA appear.
- The mobile menu closes with Escape and returns focus to its trigger. The skip link moves focus to `#main-content`; the measured 3px `#ffcf4a` focus ring is asserted by Playwright.
- Public pages keep the document inside the viewport at 390, 768, 1024, and 1440px. Wide source tables scroll inside their own labelled regions instead of expanding the page.
- The directory remains a text-first product on mobile: filters are shown before results and the result list precedes the footer. The map retains a text result list through the Map/List tabs and shows the precision caveat.
- The map screenshots show loaded viewport results and the text result list. The e2e suite also asserts the OpenStreetMap demo attribution and the same-origin MapLibre worker. The basemap is still a demo dependency, not a production tile-provider decision.

These are implementation views, not copies of the reference site's layout or assets. The intentional product deviations are recorded in [reference measurements](../reference-measurements.md#8-deliberate-philfacilities-deviations) and [the reference design system](../../08-REFERENCE-DESIGN-SYSTEM.md).
