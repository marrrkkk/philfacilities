# Philippine Geoportal layer inventory

**Evidence date:** 15 November 2026  
**Catalogue response:** `https://geoportal.gov.ph/layers/getlayersbyagency`  
**Acquisition result:** HTTP 200, 1,887,823 bytes  
**Catalogue shape:** 3,532 leaf layer entries, 54 agency nodes, 3490 unique layer names after grouping repeated catalogue entries  
**Machine-readable inventory:** [`expand/data/geoportal-layers.csv`](../data/geoportal-layers.csv)

This inventory records what the public Geoportal catalogue advertises. It is not a
download, a source release, a rights decision, or proof that a layer is current.
The catalogue response itself supplies no layer date, CRS, feature count, schema,
licence, or coverage statement for most entries. Those facts must come from the
originating agency or a permitted layer download.

## Access and rights findings

- The catalogue and public map load, but layer-level WFS requests returned HTTP 401
  in the prior inspection. No authentication or access-control bypass was attempted.
- The Geoportal download guide says only layers enabled in the Download window can be
  downloaded; others require contacting the data owner. The bulk download flow uses a
  name/email form, a human flow that this project does not automate.
- On recheck, `GET /layers/getlayerdetails/{layer}` returned HTTP 404 for
  `bfp_office`, `govoffices`, `marketplace`, `updated_healthfacilities_061826`, and
  `da_fishport`. A prior cached response for `da_fishport` recorded `download: true`.
  The current detail route is therefore not a verified per-layer metadata API.
- A catalogue `download` flag is not a licence. No layer-level explicit reuse terms
  were found. Every candidate remains `REVIEW_REQUIRED`; none is publishable.
- Do not treat the MMDA `landmark_point10k` styles as four independent authoritative
  datasets. They are one layer with different styles/tags.

## Candidate layer matrix

| Layer | Agency | Catalogue title / tags | Download flag | Assessment | Decision |
|---|---|---|---|---|---|
| `airportcontrolstation_20220513 — Airport Control Station (Airport, Control Station, CAAP)` | CAAP | Airport Control Station | False | Airport control stations are operational/security-sensitive and not equivalent to public airport facilities. | **SECURITY REVIEW; DO NOT PUBLISH COORDINATES** |
| `bfp_office — BFP Regional/Provincial Office` | BFP | BFP Regional/Provincial Office | False | Official-sounding BFP office layer, but no date, schema, feature count, or rights metadata. The catalogue marks download false. | **DISCOVERY_ONLY** |
| `da_fishport — Fish port (Fish port)` | DA | Fish port | True | Fish port layer; catalogue marks download true and a prior detail response recorded download true. PFDA/DA facility status and rights still need review. | **HUMAN DOWNLOAD / RIGHTS REVIEW** |
| `dotc_nationalairports — National Airport` | DOTr | National Airport | None | National airport layer; no date/schema/rights. CAAP is the operator/oversight source and direct access is restricted. | **DISCOVERY ONLY** |
| `dpwh_nauticalport — Nautical Port` | DOTr | Nautical Port | False | Nautical port layer; no date/schema/rights. PPA port list is the better identity source already published. | **DISCOVERY ONLY** |
| `dti_ncr_offices — DTI NCR Office` | DTI | DTI NCR Office | False | NCR-only DTI office layer; no date/schema/rights. | **DISCOVERY ONLY; REGIONAL** |
| `dti_offices — Department of Trade and Industry Offices` | DTI | Department of Trade and Industry Offices | False | DTI office layer; no date/schema/rights. The DTI directory is the better source. | **DISCOVERY ONLY** |
| `dtssfp_v1_20201120 — Shared Service Facility by Province (DTI, Shared Service Facilities)` | DTI | Shared Service Facility by Province | False | Shared Service Facility by province; same ownership/operator ambiguity. | **REVIEW** |
| `firehydrants — Fire Hydrants (2003) (Fire Hydrants, MMIERS, MMDA)` | MMDA | Fire Hydrants (2003) | False | 2003 MMDA hydrant points. Hydrants are infrastructure assets, not public-service facilities, and the layer is old. | **REJECT AS FACILITY; CONTEXT ONLY** |
| `govoffices — Government Offices (2003) (MMIERS, Government offices, MMDA)` | MMDA | Government Offices (2003) | False | 2003 MMDA government-office points. Too old to present as current and lacks a rights/schema basis. | **STALE; DISCOVERY ONLY** |
| `landmark_point10k — Fire station / Place of Worship / Police precinct/station / Public Office (Fire Station / Place of Worship / Police precinct/station)` | MMDA | Fire station / Place of Worship / Police precinct/station / Public Office | False | One MMDA layer reused with Fire Station, Police Precinct/Station, Public Office and Place of Worship styles. It cannot establish separate authoritative facility registers. | **DISCOVERY ONLY; DO NOT SPLIT** |
| `marketplace — Market Place (2003) (MMIERS, MMDA, Market Place)` | MMDA | Market Place (2003) | False | 2003 MMDA market points. Too old to present as current; LGU source is required. | **STALE; DISCOVERY ONLY** |
| `negosyocenter — Negosyo Center (DTI, Negosyo Center Facilities.)` | DTI | Negosyo Center | False | DTI Negosyo Center layer. The live DTI JSON directory is already published; this layer could test co-location but is not needed for identity. | **ENRICHMENT CANDIDATE ONLY** |
| `philippine_ports — Philippine Ports Authority (Base Ports and Terminal Ports) (PPA, Ports, Philippine Ports)` | PPA | Philippine Ports Authority (Base Ports and Terminal Ports) | False | PPA base and terminal ports. The official PPA PDF list is already published; this layer could add geometry only after rights and identity matching. | **ENRICHMENT CANDIDATE ONLY** |
| `pnrstation_20210201 — PNR Station (PNR Station, PNR)` | PNR | PNR Station | False | PNR station layer dated 2021-02-01 in the layer name; no current status, schema, or rights evidence. | **DISCOVERY ONLY; CHECK CURRENTNESS** |
| `ssfr_20201120 — Shared Service Facilities by Region (DTI, Shared Service Facilities, Region)` | DTI | Shared Service Facilities by Region | False | Shared Service Facilities by region; ownership/operator/host semantics are not established and funding does not prove government ownership. | **REVIEW** |
| `supermarket — Supermarket (2003) (MMIERS, MMDA, Supermarket)` | MMDA | Supermarket (2003) | False | 2003 MMDA supermarket points. Ordinary retail is outside the inclusion policy. | **EXCLUDE** |
| `tesda_office_2016 — TESDA Office (TESDA)` | TESDA | TESDA Office | False | 2016 TESDA office layer; stale and lacks rights/schema evidence. | **STALE; DISCOVERY ONLY** |
| `tesda_tti_20220210 — TESDA-registered TechVoc Courses/Programs and TVET Providers/Institutions - NCR (techvoc, tvet, tesda, national certificate, nc, tech voc)` | TESDA | TESDA-registered TechVoc Courses/Programs and TVET Providers/Institutions - NCR | True | TESDA-registered TVET providers, NCR only. Catalogue marks download true, but the download form and reuse terms still require a human decision; TESDA direct provider access is also blocked. | **HUMAN DOWNLOAD / RIGHTS REVIEW** |
| `updated_healthfacilities_061826 — Hospital and Health Facilities (hospital, doh, health facilities)` | NAMRIA | Hospital and Health Facilities | False | Hospital/health-facility layer with a DOH tag, but no date, owner, schema, feature count, or rights evidence. Possible duplicate of DOH/PhilHealth records. | **REVIEW BEFORE ANY USE** |

## Why no layer was ingested

1. The catalogue does not expose a date, CRS, feature count, schema, or licence for
   these entries. A title and a map style are not a source release.
2. WFS feature access returned 401; the permitted bulk-download route requires a
   human form/contact. Automating around either would violate the project's access
   rules.
3. The layers most likely to be useful are either old (2003, 2016, 2021), regional
   (NCR), derivative/undated (`updated_healthfacilities_061826`), or shared-style
   layers (`landmark_point10k`).
4. Several candidate categories already have a stronger official identity source
   published: DTI Negosyo Centers, PPA ports, PhilHealth facilities, and CHED HEIs.

## Next actions

- Request layer metadata and written reuse terms from the named originating agency
  for `bfp_office`, `updated_healthfacilities_061826`, `pnrstation_20210201`,
  `dotc_nationalairports`, and `da_fishport`.
- If a permitted download is obtained, treat it as a new source release with a
  checksum, parser, schema tests, feature count, dated reference period, and a
  layer-specific publication decision.
- Compare any health layer against DOH/PhilHealth identities before enrichment; do
  not create duplicate facilities from a derived layer.
- Keep `landmark_point10k` as one MMDA layer, not four registers.

## Tracker evidence

- AF1-06: catalogue inventory acquired and normalized.
- AF1-07: no layer-level reuse permission found; all candidates remain review-required.
- AF1-28: candidate layers assessed individually in the matrix above.
- AF3-01: layer metadata inventory built; date/CRS/feature metadata remains missing.
- AF3-02 to AF3-08: no vector data acquired; each remains blocked on permitted access
  and rights.
