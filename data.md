# PhilFacilities source discovery and full-rebuild brief

You are the source-acquisition lead for PhilFacilities, a Philippine facilities data platform.
Build the most complete feasible inventory of **official, publicly downloadable, facility-level
sources**, and prepare every source for a clean re-download and re-ingestion through the current
pipeline.

Every candidate must end in one of two states:

1. **included** — the exact public release was downloaded or inspected, verified, and ingested
   automatically, with checksum, schema, record count, dates, coverage, publisher identity and rights
   evidence recorded. A release does not need an explicit licence or permission: public
   availability, official publisher identity and verification are sufficient when there is no
   explicit prohibition;
2. **skipped** — the exact URL was tested and the source was skipped automatically because it is
   unreachable, needs a login/agreement/FOI/CAPTCHA or other human step, carries an explicit
   restriction, or is otherwise ineligible. The machine-readable reason, alternate official route and
   next automatic retry are recorded. There is no human review or blocked queue.

The default for a public, official, verified release is **include**, not skip. A missing licence,
missing terms page or unstated permission is not an explicit prohibition. Do not claim completeness.
Do not invent sources, URLs, fields, counts, coverage or permissions. The goal is **maximum verified
coverage**, not a claim that every possible source has been found.

## 0. Operating context

Read first:

- [`README.md`](README.md) — current platform state and published-source caveats.
- [`docs/sources.md`](docs/sources.md) — research register and evidence narrative.
- [`data/sources/source-candidates.json`](data/sources/source-candidates.json) — candidate baseline.
- [`docs/ingestion.md`](docs/ingestion.md) — release lifecycle, acquisition, validation and fusion.
- [`docs/adding-a-source.md`](docs/adding-a-source.md) — adapter/connector contract.
- [`docs/data-policy.md`](docs/data-policy.md) — inclusion, rights, privacy and publication rules.
- [`docs/data-model.md`](docs/data-model.md) and
  [`docs/data-dictionary.md`](docs/data-dictionary.md) — canonical fields and null semantics.

The current registry is a **baseline, not a ceiling**. Check actual state:

```bash
uv run philfacilities-ingest source list
uv run philfacilities-ingest status
uv run philfacilities-ingest monitoring
uv run philfacilities-ingest source-candidates --json
uv run philfacilities-ingest source-inventory
```

The platform is preparing a **clean rebuild**: derived records may be deleted, every reachable source
will be re-downloaded from the original publisher, and the data will be re-ingested through the
updated pipeline. Treat the database as disposable, but treat the source register, retained raw
releases, rights decisions and probe evidence as **auditable history that must not be lost**.

The pipeline preserves raw releases by SHA-256, validates fail-closed, matches deterministically
without auto-merging on name similarity, and fuses attributes while retaining every competing claim.
The fusion model means a source that duplicates most facilities is still valuable if it supplies
missing fields, identifiers, coordinates, ownership evidence, service categories, validity dates or
corroboration. **Do not discard a source because another source already covers the same facility.**

The pipeline is **in scope for adjustment**, not a fixed constraint. If a verified, publishable
source cannot be fully retained because an adapter, validator, canonical writer or fusion step loses
usable data, fix the pipeline as part of the rebuild. Optimise for **amount of usable data** while
holding **integrity** and **accuracy** as hard constraints, and produce **clean** canonical values:
traceable to a source record, internally consistent, free of avoidable duplicates, and never silently
contradictory. Do not trade integrity for volume; the guardrails are in section 9.

The rebuild is **fully automated**. A public, official, verified release with no explicit
prohibition is ingested and published without a human approval step. **A missing licence, a missing
terms page or unstated permission is not a prohibition**: if the release is publicly available,
official and verified, include and publish it with attribution, provenance and a takedown route.
A source that requires a login, agreement, FOI request, CAPTCHA or other human action is skipped
automatically with a recorded reason. Do not create manual review, approval or blocked queues.
Automated privacy and explicit-restriction rules still exclude or redact protected fields; they do
not wait for a person.

## 1. Mission

Inventory sources that are:

- published by the **official custodian**, an official inter-agency platform, or an official
  regulator/accreditor directory of private providers;
- available with or without an explicit open licence or permission; public availability, official
  publisher identity and verification are sufficient when no explicit prohibition applies;
- publicly reachable through a **normal unauthenticated public route**;
- downloadable as a file or public API, or inspectable as a structured public directory with named
  facility records;
- usable for a **fresh re-download** and a documented ingestion handoff.

For every source, determine the exact release, publisher authority, record identifiers, unique or
complementary fields, conflicts, re-download route, and rights/privacy status.

**Success is not:** a list of homepages; an agency list without probes; a catalogue entry without a
release; a search snippet; a third-party directory treated as official; a count copied from a blog;
a source omitted because it overlaps another; a skipped site bypassed.

## 2. Non-negotiable rules

1. **Original publisher first.** Start with the agency, GOCC, SUC, LGU or regulator responsible for
   the records. A repost is not the original.
2. **A homepage is not a dataset.** A directory page is not an API. A catalogue entry is not a
   downloadable layer. A published summary is not proof that every requested field was supplied.
3. **Probe the actual URL.** Record HTTP status, final URL, content type, size, retrieval time, and
   whether the result was a file, structured directory, API, GIS service, portal or failure.
4. **Never bypass access controls.** Do not evade Cloudflare, WAFs, CAPTCHAs, logins, paywalls,
   licence gates, download forms or `robots.txt`. Do not use stealth browsers, proxies, VPNs, IP
   rotation, CAPTCHA-solving services, forged cookies, `cf_clearance` tokens or spoofed identities.
5. **No human steps.** Do not submit FOI requests, accept agreements, create accounts, request tokens
   or solve challenges. A source that requires any of these is skipped automatically and retried only
   if a public route appears.
6. **Preserve source truth.** Keep original names, IDs, categories, dates, units and code values. Do
   not translate a source label into an inferred type, owner, operator or status.
7. **Missing is not zero, false, inactive or closed.** Keep null/unknown distinct.
8. **Deduplicate by canonical source, not facility overlap.** Preserve aliases, alternate URLs,
   regional variants and mirrors as separate evidence until the pipeline proves a relationship.
9. **Record coverage honestly.** Use `NATIONAL_OFFICIAL_INVENTORY`, `NATIONAL_PARTIAL`, `REGIONAL`,
   `PARTICIPATING_LGUS`, `SELECTED_LGUS`, `SINGLE_LGU`, `DIRECTORY_SUBSET`, `DISCOVERY_LAYER` or
   `UNKNOWN_COVERAGE`. Never inflate a local directory into a national register.
10. **Rights are separate from access, but silence is not prohibition.** A public URL alone does
    not establish a licence. A public, official, verified release with no explicit prohibition is
    still included and published with attribution, provenance and a takedown route. Only explicit
    restrictions, human-only access conditions and personal/security-sensitive data block or limit
    publication.
11. **Officiality is explicit.** Label every row as official custodian, official inter-agency,
    official mirror, regulator/accreditor directory, community fallback or discovery lead.
12. **Discovery leads are not sources.** Commercial directories, Wikipedia, Google Maps pins,
    social-media pages and news articles may point to an official source; they are never the source
    of record.
13. **No fabrication.** Do not invent a URL, field, count, coordinate, identifier, licence,
    permission or publisher statement. Use `null` or `UNKNOWN`.
14. **Keep negative findings.** A failure, dead URL or “no dataset found” result is evidence.
15. **Be polite.** One normal request per URL per pass, truthful user agent, bounded concurrency,
    per-host rate limits, `robots.txt` respected. Schedule rechecks instead of hammering.
16. **Do not destroy evidence.** Do not delete source records, release manifests, raw artifacts,
    rights notes or probe ledgers during a rebuild.
17. **Automate inclusion.** A public, official, verified release with no explicit prohibition is
    ingested and published automatically. A source requiring login, agreement, FOI, CAPTCHA or other
    human action, or carrying an explicit prohibition or personal/security-sensitive data, is handled
    by an automated exclusion or redaction rule and recorded. Do not create a manual approval,
    review or blocked queue. A missing licence or terms page is not an explicit prohibition and
    must not cause a public official release to be skipped.

## 3. Official, verified, current

### 3.1 Officiality tiers

| Tier | Meaning | Source of record? |
|---|---|---|
| `OFFICIAL_CUSTODIAN` | The responsible agency/body publishes on a domain it controls. | **Yes** |
| `OFFICIAL_INTERAGENCY` | An official government platform publishes custodian-supplied data, with the originating agency named. | **Yes**, with origin recorded |
| `OFFICIAL_MIRROR` | A non-custodian reproduces an official release with traceable source metadata. | **Yes, labelled mirror only**; not a substitute for the current official release |
| `REGULATOR_ACCREDITOR` | A government regulator/accreditor lists private providers. | **Yes for identity/status fields**, never proof of government ownership |
| `COMMUNITY_FALLBACK` | Crowd-sourced layer such as OSM/HOT, used to add facilities missing from official coverage or as a labelled fallback where official sources are unavailable or incomplete. | **No**; label as community and never override official values |
| `DISCOVERY_LEAD` | Search result, news item, commercial directory, social media, Wikipedia or map pin. | **No**; use only to find the official source |

An official custodian release is required for a facility to be treated as official. Community data
may be published only as a clearly labelled fallback layer. Report official, mirror,
regulator/accreditor, community and discovery-lead coverage separately; never merge them into one
“official” total.

**A licence is not required for inclusion.** Public availability, official publisher identity and
verification are sufficient when no explicit prohibition applies. Record
`redistribution_status=publicly_available_verified`, publish institutional fields only, keep
attribution and provenance, and provide a takedown route. A release with explicit restrictions, or with personal or
security-sensitive fields, is handled by the automated exclusion/redaction rules in section 6.7.

### 3.2 What “verified” means

A release is verified only when the exact file, API response, directory result set or GIS layer was
acquired or inspected; publisher identity was checked against the official domain and a cross-link;
HTTP status, final URL, content type, size and retrieval time were recorded; the file/API was opened;
schema, original field names and record count were observed; publication date, reference period and
coverage were recorded; checksum and raw-object location were recorded; and terms, rights basis,
personal-data fields and security-sensitive fields were evaluated against the automated rights and
privacy rules.

A homepage returning HTTP 200 is not a release. A sitemap is not a dataset. A search result is not a
live probe. A PDF cover page is not its data.

### 3.3 Current, downloadable, structured

Record the source's publication date and reference period. Flag a release `STALE` when it exceeds
the agency's update cycle, or 24 months when no cycle is stated. A stale release is evidence; it is
not silently replaced by a guess.

`BULK_FILE`, `JSON_API`, `GIS_LAYER`, `HTML_DIRECTORY` and `PAGED_HTML` are valid acquisition methods.
A structured public directory with named facility rows counts as `HTML_DIRECTORY` even without a bulk
export. A page that only lists agency names, programme descriptions or project categories is not a
facility directory.

## 4. Scope

### 4.1 Taxonomy

Cover every category in
[`apps/api/philfacilities_api/taxonomy.py`](apps/api/philfacilities_api/taxonomy.py):

`GOV_ADMIN`, `COMMUNITY`, `EDUCATION`, `HEALTH`, `EMERGENCY_DRM`, `SOCIAL_WELFARE`,
`SPORTS_RECREATION`, `PUBLIC_SPACE`, `CULTURE_KNOWLEDGE`, `PUBLIC_COMMERCE`,
`UTILITIES_SANITATION`, `TRANSPORT`, `ENVIRONMENT_AGRI`, `HOUSING_SETTLEMENT`,
`JUSTICE_CORRECTIONS`, `OTHER_QUALIFYING`.

### 4.2 Geographic universe

Use the latest official PSA PSGC release as the geography of record. The current platform has
**18 regions**, including the Negros Island Region (NIR); do not repeat the outdated “17 regions”
assumption. Preserve leading zeros in every PSGC code. Cover all regions, provinces, cities
(including highly urbanised and independent component cities), municipalities and barangays.

Use the BetterGov PSGC Q2 2024 mirror only as a labelled supplement while the official PSA release is
unavailable. Record the mirror's snapshot date and the PSA release it reproduces.

### 4.3 Facility granularity

Distinguish what the source actually identifies:

| Granularity | Meaning | Example |
|---|---|---|
| `FACILITY` | Named operating facility or service location | Hospital, school, RHU, port |
| `SITE` | Bounded site/compound that may contain multiple facilities | Campus, port complex |
| `BUILDING` | Specific building within a site | City hall building |
| `FACILITY_UNIT` | Service counter/unit hosted inside another facility | PhilHealth Express desk |
| `PROJECT` | Planned, funded or completed construction project | Evacuation-centre project |
| `INFRASTRUCTURE_ASSET` | Road, bridge, network, pump station | Bridge or water main |
| `POLYGON` | Area or boundary, not a point facility | Protected area |

Do not count a project as an operating facility, a host building as the service unit, or a polygon as
a facility point.

### 4.4 Inclusion and ownership

Classify every record under [`docs/data-policy.md`](docs/data-policy.md) as `GOVERNMENT_FACILITY`,
`PRIVATE_PUBLIC_SERVICE_PROVIDER`, `PUBLIC_ACCESS_VENUE` or internal-only `DISCOVERY_CANDIDATE`.
Record owner, operator, manager, host/landlord, funder, regulator, licensor, accreditor, recognition
authority, public-access class, and the evidence for each. A government licence or accreditation
does not make a private provider government-owned. A government service desk inside a private mall is
a host relationship, not a government building.

### 4.5 Out of scope

Do not inventory ordinary shops, restaurants, hotels, malls, offices, factories, warehouses or homes
merely because they are open to the public. Do not treat an organisation, company, programme, route,
licence record without a physical site, or statistical aggregate as a facility. Apply the explicit
exclusions in the data policy.

## 5. Target universe

Search these source families for every category. This is a **minimum universe**, not a closed list.

- National departments, bureaus, attached agencies, commissions, councils, GOCCs, authorities,
  government financial institutions and SUCs.
- Regional field offices, regional development councils and regional service centres.
- Provincial, city, municipal and barangay governments.
- Citizen's Charters, annual reports, accomplishment reports, inventories, transparency-seal pages
  and FOI disclosure libraries.
- Open-data catalogues and APIs, GIS portals, WMS/WFS layers, ArcGIS services and downloadable
  shapefiles.
- Official PDFs, XLSX/CSV/JSON files, sitemaps and public directories/locators.
- Licensed/accredited private-provider registries and officially designated public-access venues.
- Procurement and project portals only as project/asset evidence, not as facility registers.

### Priority sources by category

| Category | Official sources to exhaust first |
|---|---|
| `GOV_ADMIN` | All national department/agency office locators; BIR RDOs; DTI Negosyo Centers; PHLPost; SSS; GSIS; Pag-IBIG; LTO; DFA; PRC; NBI; PhilHealth offices; PSA; CSC; COA; Ombudsman; CHR; Comelec; DICT/NTC; NEDA; DBM; DOF/BOC; DOLE; DMW; TESDA; DSWD; DILG; DA; DENR; DPWH; DepEd division offices; DOH; DOTr; DHSUD; BARMM ministries; provincial/city/municipal halls; barangay halls |
| `COMMUNITY` | DILG DRRM-PULSE; DILG Subaybayan; LGU barangay/multipurpose-hall directories; community, women's and youth centres; DPWH project records as project evidence |
| `EDUCATION` | DepEd EBEIS masterlist (all regions); DepEd Machine-Ready Files; DepEd regional offices; CHED HEIDA; TESDA TVI and Assessment Centers; SUC campus directories; LGU public-school and ALS directories; DepEd-recognised private schools |
| `HEALTH` | DOH NHFR; DOH HFSRB licensed facilities; DOH hospital directory; PhilHealth provider categories; LGU RHU/BHS directories; DOH regional offices; birthing homes, dialysis, laboratories, TB-DOTS, HIV, cancer and other licensed/accredited providers |
| `EMERGENCY_DRM` | BFP fire stations; PNP stations/precincts; OCD/NDRRMC; DILG DRRM-PULSE; PCG stations; MMDA; LGU DRRM offices; evacuation centres; command centres; warehouses; public-safety training centres |
| `SOCIAL_WELFARE` | DSWD CRCF; DSWD Standards Bureau directories; ECCD Council NCDC/CDC lists; LGU day-care and senior-centre directories; shelters, halfway houses and residential care facilities |
| `SPORTS_RECREATION` | Philippine Sports Commission facilities; LGU sports complexes, stadiums, gymnasiums, covered courts, swimming pools and recreation centres |
| `PUBLIC_SPACE` | LGU parks, plazas and promenades; BMB protected areas and visitor centres; DOT-designated tourism sites; NAMRIA/Geoportal park and public-space layers; public cemeteries and memorial parks with official designation |
| `CULTURE_KNOWLEDGE` | NLP public libraries; National Museum regional/area/site museums; NHCP heritage sites; NCCA cultural centres; National Archives; CCP; KWF; LGU libraries, museums and cultural centres |
| `PUBLIC_COMMERCE` | DTI Negosyo Centers and Shared Service Facilities; LGU public markets, slaughterhouses and economic enterprises; NFA warehouses; PCA facilities; NMIS establishments; PFDA fish ports; DA food terminals |
| `UTILITIES_SANITATION` | DOE power plants; NEA electric cooperatives; LWUA water districts; MWSS; NWRB; LGU water offices; wastewater treatment plants; sanitary landfills and MRFs; EMB air/water monitoring stations; PAGASA AWS; PHIVOLCS monitoring sites |
| `TRANSPORT` | DOTr; PPA ports; CAAP aerodromes; MARINA; LTFRB terminals; PNR stations; LRTA Lines 1–2; MRT-3; LRT-1; MIAA/NAIA; CIAC; SBMA; PEZA; LGU ports and terminals |
| `ENVIRONMENT_AGRI` | DA; BFAR; NFA; PCA; NIA; BAI; PFDA; NMIS; DENR; EMB; BMB; MGB; FMB; NAMRIA; PAGASA; PHIVOLCS; protected-area management centres; hatcheries, nurseries, laboratories and research stations |
| `HOUSING_SETTLEMENT` | NHA landholdings and project locations; SHFC; DHSUD; LGU housing offices; resettlement sites; completed housing projects only where occupancy/facility status is evidenced |
| `JUSTICE_CORRECTIONS` | BJMP jails; BuCor operating prisons and penal farms; DOJ offices; Judiciary courts; NBI offices; Public Attorney's Office; Parole and Probation Administration; LGU jails; only publicly acknowledged, non-sensitive fields |
| `OTHER_QUALIFYING` | Public cemeteries, toilets, terminals, housing offices, barracks/military facilities and other officially designated public-interest facilities; only with official designation and a clear public function |

### Enrichment and context

PSA PSGC/OpenSTAT, BetterGov mirrors, NAMRIA/Geoportal, population, hazard, climate and environmental
layers, official project/procurement records and official maps/locators improve fusion, geography and
verification. Keep enrichment separate from facility claims: a hazard polygon, population table or
project record is not a facility.

## 6. Discovery and acquisition method

### 6.1 Census the official universe

Build an agency census from official sources: national agency directories, GOCC lists, SUC lists, PSA
PSGC, DILG LGU directories, league of cities/municipalities/provinces lists and official regional
office pages. Record every official domain in `agency-domain-census.csv` with agency, level, region,
province, city/municipality, official domain, source of domain, verified date and notes.

For each LGU, find the official domain or official presence, then locate official facility pages. A
social-media page is a discovery lead, not a dataset. Do not assume every LGU has a website; record
“no official website verified” with the search evidence.

### 6.2 Discover machine-readable endpoints

For every official domain, check politely and in this order:

1. `robots.txt` and `sitemap.xml` / `sitemap_index.xml` / `wp-sitemap.xml`;
2. official search pages and directory indexes;
3. links to `/data`, `/downloads`, `/statistics`, `/transparency`, `/foi`, `/citizens-charter`,
   `/directory`, `/facilities`, `/locator`, `/programs`, `/projects`;
4. WordPress REST endpoints only when publicly reachable and not access-controlled;
5. Drupal JSON:API `/jsonapi`;
6. CKAN `/api/3/action/package_search`;
7. ArcGIS REST `/arcgis/rest/services?f=pjson`, then public `FeatureServer`/`MapServer` queries with
   `where=1=1&outFields=*&f=geojson` only where no login or token is required;
8. GeoServer `GetCapabilities` and `GetFeature` for public WFS layers;
9. OGC API `/collections`;
10. documented API pages: `/openapi.json`, `/swagger.json`, `/api-docs`, `/developers`;
11. official GitHub organizations or release pages that publish data files;
12. official object-storage/CDN links referenced by official pages (S3, CloudFront, official Drive
    folders), recording the official page that links them.

Do not scan ports, brute-force paths, enumerate hidden endpoints or use a vulnerability scanner. A
public endpoint that is linked or documented is in scope; a guessed private endpoint is not.

### 6.3 Search wider, then verify directly

Use search engines only to discover candidate URLs. Always probe the live official URL before
recording evidence. Useful patterns:

```text
site:gov.ph "<category>" filetype:xlsx OR filetype:csv OR filetype:pdf
site:gov.ph "list of" "<facility type>"
site:*.gov.ph "<facility type>" directory
"<agency>" "citizen's charter" office directory
site:foi.gov.ph "<agency>" "<facility type>"
site:data.gov.ph "<category>"
site:geoportal.gov.ph "<layer>"
"<agency>" "annual report" "annex" "<facility type>"
"<agency>" "accomplishment report" "<facility type>"
"<agency>" "masterlist" OR "inventory" OR "registry"
<LGU name> "health center" OR "barangay hall" OR "public market" OR "evacuation center"
site:<official-domain> sitemap.xml
intitle:"<facility type>" inurl:directory OR inurl:locator
filetype:json OR filetype:geojson OR filetype:shp OR filetype:zip "<facility type>" site:gov.ph
```

Search English and Filipino terms where useful: `sentro`, `bulwagang barangay`, `paaralan`,
`silid-aklatan`, `palengke`, `istasyon`, `health center`, `lying-in`, `birthing home`, `day care`,
`RHU`, `BHS`, `NCDC`, `CDC`, `covered court`, `gymnasium`, `sports complex`, `plaza`, `park`.

### 6.4 Sweep LGUs systematically

Use the PSGC hierarchy as the work list: region → province → city/municipality → barangay. For each
province and highly urbanised city, search the official LGU and provincial domains. For each
city/municipality, search official directories for halls, health centres, day-care centres, markets,
terminals, parks, sports facilities, libraries and DRRM facilities. For each barangay, record a
barangay hall or health station only where the LGU publishes it; do not invent a facility from the
barangay name.

Record every LGU in `lgu-search-ledger.csv` with PSGC, LGU name, region, province, official domain,
probe URLs, result, facility types found, last verified and notes. Prioritise NCR and highly
urbanised cities, provincial capitals and first-class municipalities, then the remaining
municipalities and barangays. Do not stop after one LGU per province.

### 6.5 Re-probe the existing baseline

Re-test every source in `data/sources/source-candidates.json` and every registered source. Verify the
URL still resolves; detect changed files, schemas, counts and publication dates; re-check every
previously skipped source because Cloudflare/WAF/TLS/DNS failures are often temporary and public
routes can reappear. Append a dated probe even when the result is unchanged; never overwrite older
probes.

### 6.6 Acquire and inspect

Prefer, in order: public bulk file (CSV/XLSX/JSON/GeoJSON/SHP/Parquet/ZIP); public API (JSON/XML/OGC/
ArcGIS/GeoServer); structured public HTML directory or paged result set; public PDF table or official
report annex; public mirror or repost of an official release (labelled `OFFICIAL_MIRROR` only when
traceable). A route that requires a login, agreement, FOI request, CAPTCHA or other human action is
not an acquisition route: record it as `SKIPPED` with reason `HUMAN_ACCESS_REQUIRED` and continue.

For coverage gaps, compare the approved OSM/HOT and Geofabrik extracts against official records and
use named OSM features with no official counterpart as community fallback candidates under section
10.5. Do not scrape Google Maps, commercial map APIs or third-party copies to fill gaps.

For each acquired artifact record exact URL and final URL, UTC retrieval time, HTTP status, content
type, content length, SHA-256, filename, format, release label, schema, publication date, reference
period, geographic scope, observed record count and raw-object location. If the environment cannot
download a large file, retry with a resumable/range transfer or the automatic bulk-download job. If
the transfer still fails, record URL, size, expected format and the failure; mark it `SKIPPED` with
reason `TRANSFER_FAILED`, not `ACQUIRED`.

Open the actual file/response and inspect sheet names, header rows, merged cells, page ranges,
encodings, delimiters and units. Record original field names exactly; identify stable source
identifiers and crosswalk keys; count rows and unique keys; measure missing rates; check duplicates
and conflicting values; inspect geographic fields and coordinate method; check date formats,
reference periods, leading zeros and code systems; note personal/security-sensitive fields and known
exclusions.

### 6.7 Rights and publication decision (automated)

For every source/release record the licence, terms, copyright notice, FOI condition or agreement and
the date checked; whether an explicit prohibition or restriction applies; personal-data fields and
minimisation decision; security-sensitive fields and exclusion decision; attribution text; takedown
route; redistribution state and the automated publication decision. Access and rights are separate,
but the absence of a licence statement is not a prohibition.

Apply this decision table automatically; never send a source to a human queue:

| Condition | Decision |
|---|---|
| Public, official, verified, no explicit prohibition — including no licence, no terms page or unstated permission | `PUBLISH` institutional fields with `redistribution_status=publicly_available_verified`, `publication_status=published`, attribution, provenance and takedown route |
| Explicit prohibition on redistribution or publication | `SKIPPED`; keep the raw release internally as evidence, publish no facility rows |
| Login, agreement, FOI request, CAPTCHA or other human-only access | `SKIPPED` with `HUMAN_ACCESS_REQUIRED`; record the public alternate route and the next automatic retry |
| Personal-data fields (individual names, contact details, personal identifiers) | Redact or omit the fields; publish the facility record only if it remains meaningful |
| Security-sensitive fields (access codes, guard posts, sensitive exact locations) | Exclude the fields or the facility; record the exclusion rule |
| Licence permits reuse with conditions | `PUBLISH` under those conditions; record attribution and share-alike/notice requirements |
| Unclear or unstated terms with no prohibition | Treat as `publicly_available_verified`; publish institutional fields with a takedown route |

A release that cannot be published remains internal evidence only. The automated decision, its rule
identifier and the supporting evidence are written to the release record; no manual approval is
required.

### 6.8 Hand off to ingestion

For every source to be rebuilt, produce an adapter handoff: source key and dataset slug; acquisition
shape (single file, indexed PDFs, paged HTML, JSON API, CKAN, ArcGIS REST, WFS, sitemap crawl,
resumable bulk transfer); exact URL pattern and parameters; expected file names, sheets and columns; source record key
and uniqueness rule; facility-level fields and granularity; crosswalk keys; validation rules and
acceptance floor; rights/publication decision; personal/security exclusions; expected row count and
coverage; open questions. Do not write source-specific code into `pipeline/`; follow
[`docs/adding-a-source.md`](docs/adding-a-source.md).

## 7. Unavailable-source and skip handling

A failed probe is not a dead end, but it is not permission to bypass an access control. For every
`403`, `429`, `503`, Cloudflare challenge, WAF page, TLS failure or DNS failure, work through the
public routes below, then record an automatic skip if none succeeds:

1. **Record the exact failure.** URL, final URL, HTTP status, content type, size, UTC time,
   `server`/`cf-ray`/`via` headers if present, and whether it is a challenge, login, paywall or
   ordinary error.
2. **Re-test later automatically.** Transient failures may clear. Schedule a later probe; do not
   hammer the host.
3. **Check canonical host variants** only when they resolve to the same publisher (`www` vs non-`www`,
   `http` vs `https`, documented regional subdomain). Record each variant.
4. **Find the direct official file.** Search the official page, source and documented links for an
   object-storage/CDN URL, attachment path or public PDF. The HTML host being unavailable does not
   necessarily mean the official file host is unavailable. Example: DOE grid PDFs were reachable
   through the official CloudFront host while the CMS HTML returned 403.
5. **Use an official alternate route.** Look for the same release on the agency data/statistics/
   transparency page; a regional or field-office page; a public FOI disclosure library; an official
   inter-agency catalogue (`data.gov.ph`, Philippine Geoportal, PSA OpenSTAT); an
   annual/accomplishment report, Citizen's Charter or annex; an official GitHub organization/release;
   or an official GeoServer/WFS/ArcGIS endpoint maintained by the agency or a partner agency.
6. **Use an official mirror only when traceable.** A mirror is acceptable only if it names the
   original agency, release and source URL and, where possible, carries a checksum or dated snapshot.
   Label it `OFFICIAL_MIRROR`. Example: BetterGov PSGC mirror while the PSA workbook is unavailable.
7. **Use an official API behind the public frontend** only when it is reachable without login, token,
   CAPTCHA or challenge. A public JSON endpoint the public page uses is in scope; an authenticated
   admin endpoint is not.
8. **If a login, agreement, FOI request, CAPTCHA or other human step is required,** do not perform it.
   Record `HUMAN_ACCESS_REQUIRED` with the exact route; it is not a block to circumvent.
9. **If still unavailable,** mark `SKIPPED` with a machine-readable reason, add the source to
   `skipped-sources.jsonl`, and record the route tried, the official alternate route, the last failure
   and the next automatic retry. Do not create a manual blocked register or review queue.

Skip reasons are machine-readable: `HTTP_403`, `HTTP_404`, `HTTP_429`, `HTTP_5XX`, `WAF_CHALLENGE`,
`LOGIN_REQUIRED`, `AGREEMENT_REQUIRED`, `FOI_REQUIRED`, `CAPTCHA_REQUIRED`, `HUMAN_ACCESS_REQUIRED`,
`TLS_FAILURE`, `DNS_FAILURE`, `TRANSFER_FAILED`, `EXPLICIT_RESTRICTION`, `PRIVACY_RESTRICTION`,
`NO_PUBLIC_RELEASE`, `UNVERIFIED_PUBLISHER`. Every skip records the reason family, detail, route
tried, alternate route and next retry. The source is retried automatically and returns to the pipeline
if a public release appears. Define this vocabulary once in the ingest package and import it
everywhere; do not copy the list into adapters, CLI modules or reports.

**Never do this:** stealth/anti-detect browsers; proxy, VPN, Tor or IP rotation; CAPTCHA-solving
services; forged `User-Agent`, `Referer`, cookies or `cf_clearance`; scraping logged-in, paywalled or
agreement-gated pages; reconstructing an unavailable dataset from a third-party copy and calling it
official; using an Internet Archive or search-engine cache as the current source of record.

A normal browser render is acceptable only for an ordinary public page that needs JavaScript. It must
not solve a challenge, log in or evade an access control.

### Known recovery patterns

| Failure pattern | Official-alternate pattern to try |
|---|---|
| Cloudflare 403 on agency HTML | Direct PDF/XLSX on the official CDN/object store; regional page; public FOI disclosure attachment |
| DOH NHFR export unavailable | NHA GeoServer `DOH HF` layer as a partial official alternate; public DOH annual reports/annexes; PhilHealth provider categories as separate accreditation evidence |
| PSA PSGC workbook unavailable | PSA classification API; PSA OpenSTAT; BetterGov PSGC mirror as a labelled supplement |
| DepEd Machine-Ready Files unavailable | DepEd EBEIS public result sets; regional office pages; public statistics pages; official downloadable annex |
| TESDA TVI directory challenged | TESDA Assessment Centers; regional office pages; Geoportal TVET layer; official statistics as context only |
| PNP/BFP/OCD/BJMP unavailable | Public FOI disclosure attachments; LGU DRRM-PULSE participating-LGU layers; Geoportal layers; annual reports |
| LWUA/MWSS/NWRB/NEA unavailable | Agency annual reports; DOE/NEA PDFs; LGU water-office directories; official regional pages |
| TLS or DNS failure | Retry later; use the publisher's documented alternate host; record the failure if unresolved |
| HTML directory, no bulk export | Public paged HTML extraction; official JSON endpoint used by the public page; official downloadable annex |

## 8. Rebuild protocol

### 8.1 Pre-flight: preserve the evidence

Before deleting the database, derived records or raw artifacts:

1. Export the source/dataset/release inventory:
   ```bash
   uv run philfacilities-ingest source list
   uv run philfacilities-ingest status
   uv run philfacilities-ingest monitoring
   uv run philfacilities-ingest release-manifest
   ```
2. Snapshot the database, or export source, dataset, release, rights, source-check, match and fusion
   tables.
3. Verify the raw store is intact and record every object's SHA-256.
4. Record current rights decisions, publication decisions, match decisions and fusion state.
5. Store the snapshot outside the database and container volume.
6. Confirm the restore path before deleting anything.

If the database is already reset, reconstruct the baseline from the retained raw store, source
register, release manifests and probe evidence. Do not invent old counts.

Do not delete the raw store prematurely. It is the release of record. Keep it until a replacement
release has been acquired, verified and published; archive it separately if storage must be cleaned.
Never delete the only copy of an official release.

### 8.2 Rebuild order

Rebuild dependencies first: PSGC geography and administrative units; population/geographic
enrichment; national facility registries; regional offices and releases; LGU and barangay releases;
regulated private-provider and public-access-venue registries; community fallback layers only where
needed and clearly labelled; attribute fusion, matching and quality reports; API, web and exports;
final reconciliation and the automatic publication decision.

### 8.3 Fresh acquisition and failure handling

Re-download every reachable source; do not reuse an old file merely because it is on disk. If a
source is unchanged, record the new retrieval and the same checksum; the pipeline may treat it as a
duplicate release. If changed, preserve the new release and keep the old one for comparison. If
unreachable, preserve the last verified artifact as the release of record, mark the source `STALE` or
`SKIPPED` with a failure reason, and record the failed probe. Do not substitute a third-party copy
silently. Do not mix old and new release metadata; each release needs its own retrieval time,
checksum, parser version and schema version.

Parse and validate before canonical writes. Fail closed on missing required columns, empty parses,
implausible row-count changes and acceptance-rate drops. Quarantine failed releases; the previous
published release stays public. Do not delete a previously published release because a new download
failed. Record the failure, retained release and next action. If the source is valid but the pipeline
cannot retain its usable fields, apply the pipeline-adjustment mandate in section 9 before declaring
the source incomplete.

### 8.4 Post-rebuild reconciliation

Produce a delta report comparing old and new state: source/dataset/release counts; parsed/accepted/
rejected counts per source; unique facility count by category, region and inclusion class; coordinate
coverage and method; PSGC match rate; duplicates and match candidates; fusion status; newly covered,
lost, stale and skipped sources; schema and field changes; publication-decision changes. Use
`compare-releases` where applicable. Never hide a coverage regression. A smaller verified dataset is
better than a larger unverified one.

## 9. Pipeline adjustment mandate

The rebuild is allowed to change `apps/ingest/` — adapters, validators, canonical writes, matching,
fusion, reports and CLI — when the current implementation cannot retain valid source data. Make the
smallest change that recovers the data without weakening provenance, rights or identity guarantees.
Structural refactoring is also in scope under section 9.4; it must preserve behavior.

### 9.1 Adjustments to make when needed

- **Persist address-only and PSGC-only locations.** A source that publishes a postal address, PSGC
  code or service area but no coordinate still supplies usable location evidence. Store it as the
  current `FacilityLocation` with null geometry/coordinates, expose it in search and the facility
  profile, and never invent a point. Only treat a location as absent when the source supplies no
  location evidence at all.
- **Separate fatal row errors from field-level defects.** A missing or malformed optional field must
  produce a warning and a null/omitted value, not reject the whole facility row. Reserve row
  rejection for missing identity or critical fields, duplicate source keys, or values that would
  corrupt the canonical record.
- **Retain rejected rows as evidence.** Every parsed row must remain in staging with its validation
  status and issues even when it cannot be applied. Report rejected rows by code and source; never
  silently drop them from the run report.
- **Normalize without erasing source truth.** Trim and collapse whitespace, normalize code case and
  separators only where the source system defines them, preserve leading zeros, and keep the original
  value in `raw_payload` and the attribute assertion. Never title-case an official name, translate a
  source category, or replace a source label with an inferred one.
- **Apply values by authority, not arrival order.** A lower-authority, internal-only or older release
  must not overwrite a higher-authority current value. Equal-authority disagreements remain conflicts
  with every alternative retained; recency is a tie-breaker, not an authority.
- **Fill gaps from complementary sources.** After ingestion, run deterministic matching, merge only
  duplicates that pass the documented identity test (exact stable ID, or exact normalized name plus
  PSGC and address/coordinate evidence), and fuse safe fields so a second source can fill a missing
  subtype, ownership, operator, access class, status, stable identifier, address, PSGC code or
  coordinate. When the facility has no point at all, an OSM-derived `map_geocoded` point may fill the
  map gap under section 10.6. Everything less certain remains an unmerged candidate, is excluded
  from canonical application, and is retried automatically when new evidence or a newer release
  arrives. Every filled value must name the source record it came from.
- **Retire blocked and manual states.** Replace `ACCESS_BLOCKED`, `HUMAN_DOWNLOAD_REQUIRED`,
  `FOI_REQUIRED`, `approved`/`manual`/`blocked` source groups and manual match review with `SKIPPED`
  plus a machine-readable reason, or an automated publication state. Matching, fusion,
  rights/publication and skip decisions run as deterministic, auditable functions. A candidate that
  is not deterministic stays unmerged and is retried automatically; it is never assigned to a person.
- **Keep reprocessing cheap, deterministic and idempotent.** Batch writes, avoid per-row queries,
  bump `parser_version` when parsing changes, reprocess the preserved release automatically, and make
  repeated runs converge to the same canonical state.
- **Prefer structured extraction over text loss.** Where an official PDF or HTML directory contains
  stable fields, parse them instead of storing only a title and URL. Keep the original page, row or
  section reference for every extracted record.
- **Measure retention, not just ingestion.** Every adapter and pipeline change reports parsed,
  accepted, rejected, applied and skipped counts, plus address, coordinate, PSGC, identifier and
  fusion coverage. A change that raises raw row count while losing provenance or creating unresolved
  duplicates is a regression.

### 9.2 Guardrails that may not be relaxed

- No relaxation of the no-bypass, rights, privacy, publication-decision or no-fabrication rules in
  section 2.
- No auto-merge on name similarity, a shared address alone, or a single matching field.
- No filling a missing value with a guess, average, majority vote or another source's inferred value.
- No deleting raw releases, source records, assertions or rejected-row evidence to make counts look
  cleaner.
- No lowering a release acceptance floor to make a dirty snapshot pass. Raise coverage by recovering
  valid rows and adding sources, not by accepting corrupt ones.
- No silent schema coercion: a renamed or missing required column fails the release.

### 9.3 Verification for every pipeline change

Run the relevant checks and record before/after measurements:

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run philfacilities-ingest source validate <key> --fixture <preserved-artifact>
uv run philfacilities-ingest source run <key> --dry-run
uv run philfacilities-ingest fuse-attributes --apply
uv run philfacilities-ingest fusion-report --json
```

Document the change, the source that exposed it, the affected adapter/stage, before/after retention
counts, tests added and the rollback path. A pipeline change is complete only when the preserved raw
release still reprocesses to the same or better verified output.

### 9.4 Refactor ingestion code and file layout

Treat the rebuild as a cleanup pass as well. Refactor `apps/ingest/` so each module has one
responsibility, files stay reviewable, and no source-specific logic leaks into the shared pipeline.
Prefer moving code over rewriting behavior; a pure refactor must not change parser output, canonical
data, CLI commands or API contracts.

Suggested target boundaries (adapt names to the codebase, but keep the separation):

```text
apps/ingest/philfacilities_ingest/
  pipeline/
    runner.py          # release lifecycle and stage orchestration only
    acceptance.py      # validation result -> publish/quarantine decision
    canonical/
      identity.py      # facility create/link/slug
      locations.py     # current location, precision and provenance
      assertions.py    # source field claims
      profiles.py      # school/health child rows
      changes.py       # change events and quality issues
    reporting.py       # run reports, stats aggregation
  matching/
    candidates.py      # candidate generation
    scoring.py         # evidence and confidence
    decisions.py       # automated accept/reject/merge/undo
  fusion/
    claims.py          # claim collection and authority
    selection.py       # deterministic value selection
    apply.py           # safe allowlisted application
    reports.py         # fusion status and samples
  sources/
    common.py          # shared text, code, address and PSGC helpers
    <source>.py        # one adapter per source
    connectors/        # acquisition shapes only
  cli/
    source.py
    fusion.py
    matching.py
    reports.py
    demo.py
```

Rules:

- Split by responsibility, not by arbitrary line count. A file that mixes orchestration,
  validation, canonical writes and reporting must be split even if it is small.
- Use a review trigger rather than a hard cap: any Python module above roughly 800 lines or any
  function above roughly 80 lines must be justified in the refactor note or split. The goal is
  comprehension and testability, not a line-count contest.
- Keep one adapter per source and one connector per acquisition shape. Move duplicated parsing,
  address, name and code helpers into `sources/common.py` or a small shared package.
- Keep `pipeline/` source-agnostic: no `if source == ...` branches, no source column names and no
  source-specific policy. Add an adapter capability or connector instead.
- Keep `cli.py` thin. Command modules own argument parsing and call services; business logic stays
  in the pipeline, matching, fusion or source modules. Remove reviewer-only commands or flags from
  the routine path: matching, fusion and publication run unattended and idempotently. Any remaining
  operator command is for investigation, not a required approval.
- **No duplicate code, files or definitions.** One implementation per concern: text cleaning, PSGC
  normalization, coordinate validation, acceptance decisions, matching scores, fusion ranking and
  report formatting each live in one place. Before adding a helper, search for an existing one and
  extend it; update every call site and delete the old copy in the same slice.
- **Move, do not copy.** Do not leave a forwarding module, a second adapter, a parallel pipeline
  path or a duplicate test that asserts the same behavior. Consolidate duplicate modules and remove
  the losing copy. Keep one source catalogue, one pipeline entry point and one set of taxonomy,
  rights and API-type definitions.
- Delete dead code and unused modules. Do not add compatibility shims unless an external consumer
  needs them; if a public import path or CLI command must stay stable, update all call sites in the
  same change.
- Use package `__init__.py` files for a clear public boundary, not giant re-export barrels that hide
  coupling.
- Refactor in small, reviewable slices with tests. Do not combine a pure move/split with a behavior
  change or a data migration.
- Update [`docs/ingestion.md`](docs/ingestion.md) and any module map or import references after a
  move.

Behavior-preservation evidence for every refactor slice:

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run philfacilities-ingest source replay <manifest>
uv run pytest apps/ingest/tests/test_golden_replay.py
```

The refactor is complete only when the golden replay, parser fingerprints, CLI tests and API contract
tests pass unchanged, and the diff is a move/split rather than a semantic rewrite.

## 10. Fusion readiness

The fusion model can combine duplicate facilities and fill missing fields from complementary
sources. Give it the evidence it needs.

### 10.1 Field-level semantics

For every source record the original field name, normalized field name, description, data type, unit,
allowed values, geographic level, temporal validity/reference period, whether the value is a source
claim/derived value/inference, authority tier, and personal-data/security-sensitive flag.

### 10.2 Crosswalk keys

Look for stable official identifiers: PSGC codes (preserve leading zeros); DepEd school ID; CHED HEI
code; TESDA provider/centre code; DOH facility code; PhilHealth provider/accreditation number; DSWD
centre code; NMIS LTO number; PPA port code, CAAP airport code, MARINA identifier; LGU office/barangay
code; licence/registration/accreditation numbers; official station/branch codes; normalized address
components and coordinates with method/precision.

Record whether each key is stable, reused, optional or absent. Never invent a crosswalk. A name match
is a candidate, not an identity.

### 10.3 Overlap and complementarity

For each source estimate which facility categories and regions it covers; which fields are likely
duplicated; which fields are unique or rarely available; which records are likely new; which are
likely to conflict with stronger sources; whether it can corroborate existing claims; and whether it
has enough identifiers for deterministic matching. A source with low unique-facility value but high
unique-field value is still high priority.

### 10.4 Preserve conflicts and avoid premature merging

Do not average, majority-vote or silently prefer the larger source. Record every competing value,
its source and release, authority tier, reference period, expected resolution rule, and whether the
conflict should remain visible. Official values outrank community values. Two official sources with
equal authority remain a conflict unless a documented rule resolves them.

Do not merge facilities at the discovery stage. Keep source records separate; the pipeline's matching
and fusion stages decide identity and derived values with recorded evidence.

### 10.5 OpenStreetMap for facilities missing from official coverage

OpenStreetMap, HOT and the Geofabrik Philippines extract are the approved **community fallback**
layer. Use them to add facilities that are absent from every official source, especially in
categories and regions where the official register is unavailable, incomplete or stale. Do not use
OSM as the source of record for an official facility.

- Ingest named, qualifying OSM features as `COMMUNITY_FALLBACK` with `authority_level=community`,
  ODbL attribution, the original OSM id/type/tags and `record_status=unknown`. Never count them in
  official coverage totals.
- If an OSM feature matches an official facility, keep both records and let the official claim win.
  OSM may supply a coordinate, address or crosswalk candidate as a labelled `map_geocoded`
  alternative, never as an overwrite of an official name, type, owner, operator or status.
- If no official counterpart exists, publish the OSM feature as a visibly labelled community
  facility, or keep it internal where rights or identity evidence is insufficient, so it can be
  found and later reconciled automatically when an official release covers it.
- Use deterministic matching only: exact OSM id, a shared official identifier, or normalized name
  plus PSGC/administrative area plus coordinate proximity. Everything else remains an unmerged
  candidate and is retried automatically; a name match alone is not identity.
- Preserve coordinate method and precision. OSM bounding-box centres and way centroids are not
  building pins; label them `map_geocoded`, never `surveyed`.
- Do not infer ownership, operator, public access, licensing, opening or operational status from an
  OSM tag or from map presence.
- Skip unnamed features, ordinary commercial/residential features and tags outside the approved
  facility taxonomy.
- When an official release later covers the same facility, merge the OSM evidence into the official
  record, keep the OSM source link and attribution, and retire the duplicate rather than deleting
  history.
- Report OSM-derived facilities, OSM-only fields and OSM-assisted coordinates separately from
  official counts, and list the categories and regions where OSM is currently the only coverage.

### 10.6 OSM-derived coordinates for unlocated facilities

When a facility has no coordinate from its own source or from a stronger official source, use the
approved OSM/HOT/Geofabrik extract to find a map point instead of leaving it unmapped. This is a
coordinate gap-fill, not a promotion of OSM to the facility's source of record.

1. Build the list of facilities with no current point: no `FacilityLocation` with latitude and
   longitude, or only an address/PSGC claim.
2. Search the approved OSM snapshot by normalized facility name within the same PSGC or
   city/municipality. Use alternate names only when the source record or OSM tags explicitly link
   them. Never run a national name-only search.
3. Accept a match only when the evidence is deterministic: same normalized name, same PSGC or
   city/municipality, compatible facility category, and either a shared official identifier, an
   address token match, or a point within the documented proximity threshold of the official
   address/barangay centroid. If more than one OSM feature passes, record the candidates and leave
   the facility unmapped; retry automatically when a stronger signal or a newer OSM snapshot arrives.
4. Store the accepted point as the facility's current location with `precision="map_geocoded"`,
   `method="openstreetmap_match"`, the OSM feature id and snapshot date, ODbL attribution, and
   `review_status="community_fallback"`. Keep the original address-only/PSGC location claim and its
   provenance; do not delete it. If the OSM feature already exists as a separate community
   facility, merge its evidence into the official facility under the deterministic identity
   process; do not leave two map points for one facility.
5. Never overwrite an existing official coordinate, even a coarse one, with an OSM point. If the
   official coordinate is wrong, record the conflict and keep the official claim current until a
   stronger official release or a deterministic rule resolves it.
6. If no OSM feature passes, leave the facility unmapped. Do not geocode from a guessed address, a
   barangay centroid presented as a facility pin, or a third-party map service.
7. On the map, render OSM-derived points as a distinct community/map-geocoded layer, with OSM
   attribution and a “community map location” label. Never present them as surveyed or
   building-level pins. The address-only list remains available when tiles or the point layer fail.
8. Report the number of facilities geolocated from OSM, the match method, the unresolved/ambiguous
   count and the remaining unlocated count by category and region.

## 11. Deliverables and schema

Write generated reports under `var/reports/rebuild/`, not `docs/`. Keep the canonical filenames used
by existing tooling at the output root; generate or refresh the core reports with:

```bash
uv run philfacilities-ingest source-candidates --json
uv run philfacilities-ingest source-inventory \
  --json-output var/reports/rebuild/source-inventory.json \
  --csv-output var/reports/rebuild/source-inventory.csv
uv run philfacilities-ingest source-report --output-dir var/reports/rebuild
```

### 11.1 Files

| File | Contents |
|---|---|
| `source-inventory.json` | One row per source, core schema plus extended fields. |
| `source-inventory.csv` | Flat CSV of the same inventory. |
| `probe-ledger.jsonl` | One row per tested URL, including every failure, skip and negative result. |
| `gap-report.md` | Category × region matrix, searched/not searched, positive/negative findings. |
| `skipped-sources.jsonl` | Skipped sources with machine-readable reason, route tried, official alternate route and next automatic retry. |
| `acquisition-plan.md` | Ranked automatic acquisition list by coverage, record count, access, rights clarity and public-interest value. |
| `download-manifest.jsonl` | Every acquired artifact: URL, final URL, timestamp, status, content type, size, SHA-256, filename, format, source/release. |
| `schema-observations.csv` | Per-release fields, types, units, null tokens, unique keys, row counts, geographic levels, coordinate method. |
| `rights-register.csv` | Licence/terms URL, date checked, restrictions, personal/security fields, attribution, takedown route, automated publication decision and rule identifier. |
| `rebuild-plan.md` | Pre-flight backup, dependency order, acquisition order, expected commands, rollback plan. |
| `pipeline-adjustments.md` | Every pipeline/adaptor change made or required, the source that exposed it, before/after retention metrics, tests and rollback path. |
| `ingestion-refactor.md` | Before/after module tree, file-size table, moved/split symbols, duplicate code removed, unchanged behavior evidence and follow-ups. |
| `rebuild-delta.md` | Old-vs-new counts, coverage changes, schema changes, lost/skipped/stale sources, publication-decision changes. |
| `adapter-handoff.md` | Per-source acquisition shape, parser requirements, keys, validation rules and open questions. |
| `field-matrix.csv` | Source × facility field coverage, with authority tier and reference period. |
| `crosswalk-candidates.csv` | Candidate official identifiers and join keys per source; never an asserted merge. |
| `community-fallback-register.csv` | OSM-derived facilities filling an official coverage gap, with OSM id, category, region, match state and attribution. |
| `osm-location-fills.csv` | Facilities geolocated from an OSM match: facility, OSM id, match evidence, precision/method, snapshot date and match state. |
| `overlap-and-unique-value.md` | Duplicate risk, unique fields, complementary records, conflict potential. |
| `agency-domain-census.csv` | Official domains and publisher-identity evidence. |
| `lgu-search-ledger.csv` | Every LGU searched, URLs probed, facility types found, result and date. |
| `region-search-ledger.json` | Machine-readable regional probe ledger compatible with `source-report`. |
| `unresolved.md` | Candidate sources that could not be verified, with the automatic skip reason and next retry. |

### 11.2 Required fields

Keep the existing 25-field core schema exactly. Append extended fields as additional columns/keys;
never remove or rename a core field.

**Core fields:** `source_id`, `custodian`, `agency_level`, `category`, `title`, `description`,
`official_urls`, `alternate_urls`, `access_method`, `format`, `coverage_scope`, `geographic_scope`,
`evidence_state`, `access_state`, `rights_state`, `publication_state`, `probe_status`, `probe_date`,
`probe_notes`, `data_fields_observed`, `record_count_observed`, `ownership_semantics`,
`tracker_ids`, `next_action`, `notes`.

`access_state` is `OPEN` or `SKIPPED`; a skipped source always carries `skip_reason`, `skip_detail`,
`alternate_route` and `next_retry_at` in the extended fields. Do not keep a blocked access state.
`rights_state` and `publication_state` use the controlled values in
[`apps/api/philfacilities_api/rights.py`](apps/api/philfacilities_api/rights.py); do not invent a new
rights or publication state in reports.

**Extended fields (include when known; never invent):**

- identity/provenance: `source_key`, `dataset_slug`, `publisher`, `publisher_type`,
  `publisher_domain`, `officiality_tier`, `authority_level` (`official`/`community`/`synthetic`/
  `unknown`), `parent_source_id`, `mirror_of`, `release_label`, `release_date`, `reference_period`,
  `retrieval_time`, `final_url`, `http_status`, `content_type`, `content_length`, `checksum_sha256`,
  `schema_version`, `parser_version`;
- schema/keys: `original_fields`, `field_definitions`, `source_record_key`, `crosswalk_keys`,
  `geographic_granularity`, `coordinate_method`, `facility_granularity`, `update_frequency`,
  `last_verified`;
- rights/safety: `rights_url`, `rights_basis`, `attribution_text`, `takedown_route`,
  `personal_data_fields`, `security_sensitive_fields`;
- access/skip: `skip_reason`, `skip_detail`, `alternate_route`, `next_retry_at`,
  `challenge_detected`, `robots_allowed`;
- fusion/rebuild: `overlap_estimate`, `unique_value_notes`, `conflict_notes`, `adapter_shape`,
  `ingest_priority`, `can_rebuild`, `expected_row_count`, `known_exclusions`, `open_questions`.

A public official release with no explicit prohibition is not `UNKNOWN` rights for inclusion
purposes: record `rights_state=publicly_available_verified`, `publication_state=published`,
attribution and the takedown route. `UNKNOWN` rights alone must not cause a skip.

Use `null`, `UNKNOWN` or `NOT_VERIFIED` when a value cannot be verified. Do not fill a gap with a
plausible guess. A partial, honest inventory is valid; a complete-looking invented one is not.

## 12. Quality gates and acceptance

A pass is complete only when all of these are true:

1. Every taxonomy category has been searched and reported, including explicit negative results.
2. All 18 regions have at least one regional or LGU search attempt, or a documented reason why not.
3. Every province and highly urbanised city has at least one official-domain probe or a documented
   negative result.
4. Every source in the existing candidate register has been re-probed and has a fresh dated result.
5. Every source row has an official URL, probe date, publisher identity and officiality tier.
6. Every acquired artifact has a checksum, content type, size, schema, record count and dates.
7. Every public, official, verified release with no explicit prohibition is included and published
   automatically, including releases with no licence, no terms page or unstated permission.
8. Every skipped source has the exact machine-readable reason, official alternate route and next
   automatic retry.
9. Every public downloadable source is acquired automatically; every unavailable source has a
   recorded skip reason and retry.
10. No duplicate canonical source URLs; aliases and mirrors are linked, not collapsed.
11. No mirror, community layer or discovery lead is labelled as an official custodian source.
12. No record count, field, coordinate or permission is invented.
13. No FOI request, agreement, account, token or CAPTCHA was submitted, created or solved.
14. No access control, CAPTCHA, WAF or `robots.txt` was bypassed.
15. No personal or security-sensitive field is published; the automated privacy rule redacts or
    excludes it while the remaining institutional fields are published.
16. Every source has documented crosswalk keys or an explicit “no stable key” finding.
17. Every redundant source is retained if it adds fields, identifiers, coverage or corroboration.
18. Every stale or lost source is recorded; none is silently dropped.
19. Every pipeline limitation that hides valid source data is fixed or documented with the exact
    affected source, stage and retention loss; no integrity guardrail in section 9.2 was relaxed.
20. Every OSM-derived facility is labelled community fallback, excluded from official coverage
    totals, and never overwrites an official claim; OSM-assisted coordinates remain `map_geocoded`.
21. Every OSM-derived coordinate is used only to fill a missing point, carries OSM id/snapshot
    provenance, is labelled `map_geocoded`, and never replaces an official coordinate.
22. The ingestion refactor leaves one implementation per shared concern, no copied/forwarding
    modules, no parallel pipeline paths and no duplicate taxonomy/rights/API-type definitions; each
    module has one responsibility and the golden replay passes unchanged.
23. The rebuild pack, fusion pack, pipeline-adjustment pack, refactor pack, community-fallback pack,
    map-location pack and coverage pack are complete, internally consistent and reproducible.

## 13. Final report and priorities

End with: what was newly discovered and acquired; what changed since the previous baseline; the
highest-value skipped sources and their official alternate routes; how many public official releases
had no explicit licence or terms page and were still published under
`publicly_available_verified`; the largest remaining gaps by category and region; the facilities
added only from OSM and the categories/regions where it is the only current coverage; how many
facilities were geolocated from OSM and how many remain unlocated; what was refactored, which
duplicate helpers/modules were removed and which large modules remain; sources skipped for
human-only access or explicit restrictions; stale, lost or technically failing sources; and the next
10 highest-impact rebuild actions.

The biggest immediate wins are not more homepage probes:

1. DOH NHFR/HFSRB through a public route plus the NHA DOH HF layer as a partial alternate.
2. DepEd Machine-Ready Files and all EBEIS regional result sets.
3. CHED HEIDA and TESDA TVI/assessment-centre directories.
4. Every PhilHealth provider category and the current DOH licensing lists.
5. DSWD CRCF/Standards Bureau and ECCD NCDC/CDC sources.
6. BFP, PNP, OCD/NDRRMC, BJMP, BuCor and DILG/LGU evacuation-centre sources.
7. PPA, CAAP, MARINA, DOTr, PNR, LRTA, MRT-3 and LTFRB transport facilities.
8. LWUA, MWSS, NWRB, DOE and NEA utility facilities.
9. DA, BFAR, NFA, PCA, NIA, BAI, PFDA and NMIS agriculture/fisheries facilities.
10. DENR/EMB/BMB/MGB/NAMRIA environment and geospatial layers.
11. NHA, SHFC and DHSUD housing/settlement facilities.
12. NLP, National Museum, NHCP and NCCA cultural facilities.
13. PSA PSGC/OpenSTAT, Open Data Philippines and BetterGov mirrors as geography/context.
14. Every national agency office locator and Citizen's Charter directory.
15. A systematic provincial, city and municipal LGU sweep.
16. OSM/HOT as a labelled community layer for facilities missing from official coverage, including
    coordinate gap-fill for unlocated facilities; never the official source of record.

Do not claim the result is the complete set of all Philippine facility data sources. Claim only what
was verified, acquired, skipped and left unknown.
