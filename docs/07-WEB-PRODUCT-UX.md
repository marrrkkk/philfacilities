# 07 — Web Product and UX Plan

## 1. UX goal

The website should make facility data understandable and actionable without pretending the underlying records are perfect. It should behave like a modern data directory and map application, not a long campaign/marketing landing page.

The BetterGov Fellowship website is the visual reference for the design system, header/navigation treatment, typography, colors, sizing, and UI styling. **Do not copy its page layout or fellowship information architecture.** See [Reference Design System](08-REFERENCE-DESIGN-SYSTEM.md).

## 2. Information architecture

Recommended top-level navigation labels (adapted for PhilFacilities, not copied from the Fellowship page):

- Directory
- Map
- Data & Sources
- API
- About

The logo/wordmark and navigation treatment should follow the audited BetterGov reference. One primary CTA may be “Explore map” or “Browse facilities”; choose the label after visual and product review.

### Routes

| Route | Purpose |
|---|---|
| `/` | Concise product landing/entry point with search and key data-status context |
| `/directory` | Main searchable facility directory |
| `/map` | Full map-first discovery experience |
| `/facilities/[id]` | Canonical facility profile and provenance |
| `/data` | Dataset catalogue and coverage notes |
| `/data/[dataset]` | Dataset schema, source, release history, fields, download availability |
| `/sources` | Agency/source register and acquisition/freshness status |
| `/api` or `/developers` | API overview, docs link, examples, terms/usage |
| `/about` | Mission, governance, contribution, contact/correction routes |
| `/status` | Service and data-ingestion status (only publish operational data actually measured) |

## 3. Directory layout (recommended)

Desktop:

- Reference-styled top navigation.
- Page heading and brief explanation.
- Prominent facility search.
- Filter controls for type, ownership, geography, and data/source quality.
- Results count and active filter chips.
- Main results area with list cards/table rows.
- Optional map preview/toggle; do not force users into map-only navigation.

Suggested desktop split for a combined browsing view: filter/results pane on the left, map on the right. Use responsive proportions after testing real screen sizes; do not hardcode the page into the reference website's editorial single-column layout.

Mobile:

- Search visible near top.
- Filters open in a sheet/drawer.
- Directory list remains the default, with a clear Map toggle.
- Map uses a full-screen or large sheet view with accessible result list fallback.

## 4. Map layout

The `/map` route should be a map-first application view:

- Map canvas fills the content area under the site header.
- Search and filter controls remain easy to reach.
- Markers cluster at low zoom.
- Selected marker opens a facility summary panel.
- Desktop can use a side results panel and map canvas.
- Mobile uses a map with a bottom sheet/list switch.
- Bounds queries must be debounced and capped.
- Unknown/low-precision coordinates should not be displayed as precise building pins. Offer an area-level marker only when the product has a defensible representation, and label it explicitly.
- Keep a text results list available to keyboard and screen-reader users.
- Map attribution must remain visible and correct for the chosen tile provider.

## 5. Facility profile page

Recommended content order:

1. Facility name, category, ownership, and source-reported status (if available).
2. Address and geographic breadcrumb.
3. Location map only if coordinates meet the display threshold.
4. Key domain information (school profile or health profile).
5. Published accreditation/license records with authority and expiry.
6. “Where this information comes from” source list.
7. Data freshness/reference-period labels.
8. Data-quality warnings and unresolved discrepancies.
9. Historical changes and previous source releases.
10. Report a correction / contribute better source evidence.

Do not show a large availability or quality badge if source data does not establish it.

## 6. Dataset and source pages

A dataset page must communicate:

- Agency and official source link.
- Description and intended coverage.
- Source publication/reference period.
- Last successful retrieval.
- Data dictionary and schema version.
- File/API access method.
- Known missing fields and limitations.
- License/terms status and redistribution decision, including `publicly_available_verified` when the basis is verified public availability with no explicit prohibition.
- The publication policy link and the fields withheld for privacy or safety.
- Number of parsed rows and quality metrics, if measured.
- Download/API options only if publication is allowed.

## 7. UI component inventory

Use shadcn/ui components styled through Tailwind and the extracted token system:

- `NavigationMenu` or custom accessible header navigation matching reference behavior.
- `Sheet` / `Drawer` for mobile filters and map result details.
- `Command` or accessible combobox for facility search/autocomplete.
- `Input`, `Select`, `Checkbox`, `Popover`, `Calendar` only where meaningful.
- `Tabs` for overview/history/sources on facility profiles.
- `Table` for datasets and source releases.
- `Badge` for source-derived states, using restrained semantic colors.
- `Card` for facility summaries, where appropriate.
- `Tooltip` for technical field definitions.
- `Skeleton` for loading; explicit empty/error states.
- `Alert` for data-quality and source freshness caveats.
- `Pagination` or cursor-based “Load more” controls.

Do not let default shadcn styling override the visual reference. The reference tokens must be applied through the shadcn CSS variables and Tailwind theme.

## 8. Search and filters

MVP filters:

- facility type;
- ownership;
- region/province/city/municipality/barangay;
- source agency;
- has coordinates;
- location precision;
- source reference period or update date where applicable.

Search by facility name, known source identifier, address, and locality. Do not imply that a result is exhaustive if source data is incomplete.

## 9. Accessibility and responsive design

- WCAG 2.2 AA target.
- Keyboard-operable navigation, filter controls, dialogs, and map alternatives.
- Visible focus indicators consistent with the reference design.
- Contrast tests for text, borders, and map overlays.
- Do not use color alone to indicate source quality.
- Reduced-motion support.
- Meaningful page titles and headings.
- Responsive layouts checked at 390px, 768px, 1024px, 1440px, and a wide desktop viewport.

## 10. Landing page

The homepage should be concise and task-oriented:

- Clear one-sentence purpose.
- Search entry.
- Facility-type entry points (schools, health facilities).
- Measured coverage summary, with date and caveats.
- Featured data/source updates.
- API/developer entry point.
- Link to methods, sources, quality, and contributions.

Do not fabricate coverage numbers. All homepage statistics must be generated from the published dataset and carry an “as of” date.
