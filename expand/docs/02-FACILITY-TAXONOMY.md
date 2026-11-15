# 02 — Facility Taxonomy and Classification Rules

## 1. Design requirement

The taxonomy must cover qualifying facilities across government, private, non-profit, cooperative and mixed ownership/operator arrangements. It must not turn every asset, agency, business, project or building into a facility.

Use stable internal codes. Keep original agency category names/codes alongside the normalized taxonomy. Taxonomy is based primarily on the facility's function/type, while ownership, operator and access are independent dimensions.

## 2. Inclusion classes (orthogonal to facility category)

Every publishable facility receives one explicit inclusion class:

| Code | Meaning | Example |
|---|---|---|
| `GOVERNMENT_FACILITY` | Government-owned, government-operated, government-maintained, or officially designated government/public facility | Barangay hall, public hospital, public school |
| `PRIVATE_PUBLIC_SERVICE_PROVIDER` | Private/non-government facility in an authoritative regulated, licensed, accredited, registered or contracted public-service network | Private hospital, private school, accredited social-welfare centre |
| `PUBLIC_ACCESS_VENUE` | Public-serving civic, community, cultural, recreation, market or transport venue with authoritative evidence of that role | Publicly accessible privately operated market or designated civic venue |
| `DISCOVERY_CANDIDATE` | Internal-only candidate pending evidence, classification, rights or safety review | Geoportal candidate layer with unknown age/owner |

These are not separate products or disconnected databases. They are filterable classes within the same canonical registry and API. `DISCOVERY_CANDIDATE` must never appear as a verified public facility.

## 3. Top-level facility categories

| Code | Category | Government examples | Private/non-government examples when they meet inclusion rules | Typical sources |
|---|---|---|---|---|
| `GOV_ADMIN` | Government administration and public-facing offices | Barangay hall, municipal/city hall, capitol, agency regional office, government service centre | Government service unit hosted in a private site; the host remains separately classified | DILG, LGUs, national agencies, GOCCs, PRC, BIR, DTI, PHLPost |
| `COMMUNITY` | Community and civic facilities | Multipurpose hall, civic/community centre, assembly hall, barangay centre | Non-profit/community-operated centres with official public-service role | LGUs, DILG, DRRM-PULSE, NGOs where authoritative |
| `EDUCATION` | Education and learning | Public school, SUC, LUC, public college, public training centre, ALS centre | Private basic school, private HEI, private registered TVET provider | DepEd, CHED, TESDA, LGUs |
| `HEALTH` | Health and medical services | Public hospital, infirmary, RHU, barangay health station, government clinic | Private hospital, clinic, laboratory, dialysis centre, birthing facility, accredited provider | DOH, HFSRB, PhilHealth, LGUs |
| `EMERGENCY_DRM` | Emergency response and disaster-risk management | Fire station, police station, evacuation centre, DRRM centre, emergency warehouse, rescue station | Contracted/non-government response facility or officially designated private evacuation site where disclosure is appropriate | BFP, PNP, OCD/NDRRMC, DILG, LGUs |
| `SOCIAL_WELFARE` | Social welfare and protective services | DSWD/LGU residential care centre, senior citizens centre, women/children shelter, rehabilitation centre | Licensed/accredited private, NGO, religious/non-profit or workplace social-welfare provider when in official directories | DSWD, LGUs, licensing/accrediting agencies |
| `SPORTS_RECREATION` | Sports and recreation | Public covered court, gymnasium, sports complex, swimming pool, recreation centre | Publicly accessible private/non-profit sports or recreation facility with reliable public-service/venue evidence | LGUs, PSC, agencies, recognized associations where authoritative |
| `PUBLIC_SPACE` | Public outdoor spaces | Public park, plaza, playground, garden, open space | Privately owned space formally designated or maintained for public access/service | LGUs, DENR, other public bodies |
| `CULTURE_KNOWLEDGE` | Culture, knowledge and heritage | Public library, museum, archive, cultural centre, heritage visitor centre | Private/non-profit museum, library, archive or cultural centre included in an authoritative public directory and meaningfully open to the public | National Library, National Museum, NHCP, NCCA, LGUs |
| `PUBLIC_COMMERCE` | Markets and public-interest commercial facilities | LGU public market, bagsakan/trading post, public abattoir | Authoritatively licensed/accredited private meat/food-market facility when a facility-level public-interest use case is approved; do not classify as government-owned | LGUs, DA, NMIS, other agencies |
| `UTILITIES_SANITATION` | Water, energy, waste and sanitation facilities | Government water-treatment plant, pumping station, wastewater facility, MRF, sanitary landfill | Private regulated utility, water/wastewater operator, waste-treatment facility where authoritative sources identify the facility and service role | LWUA, MWSS, NWRB, DENR, EMB, utilities, LGUs |
| `TRANSPORT` | Transport and mobility facilities | Government airport/port/terminal, public transport hub, ferry terminal | Private airport, port, terminal or regulated transport facility when officially listed and facility-level identity is verifiable | DOTr, PPA, CAAP, MARINA, LTFRB, LGUs |
| `ENVIRONMENT_AGRI` | Environment, agriculture and fisheries service facilities | Government nursery, protected-area office, research farm, fisheries station, public hatchery, extension centre | Private regulated/agriculture/fisheries facility only when it meets an approved public-service or regulated-provider inclusion case | DENR, DA, BFAR, PFDA, BMB, FMB, NMIS, LGUs |
| `HOUSING_SETTLEMENT` | Housing and settlement service facilities | NHA/DHSUD housing office, resettlement community centre, public common-service facility | Recognized non-profit/community housing service centre where source-backed | NHA, DHSUD, LGUs |
| `JUSTICE_CORRECTIONS` | Justice and corrections | Public courthouse, legal aid centre, jail, correctional institution | Private legal-aid/service facility only when officially recognized and suitable for public listing | Judiciary, DOJ, BJMP, BuCor, LGUs |
| `OTHER_QUALIFYING` | Other qualifying facilities | A public or private facility with a supported public-service/community/institutional role not yet mapped | Same, subject to inclusion criteria | Relevant authoritative source |

## 4. Subtype, function and service are different

Use four concepts:

- **Category:** broad domain, e.g. `COMMUNITY`.
- **Subtype:** kind of physical/institutional facility, e.g. `MULTIPURPOSE_HALL`.
- **Function:** what the place is designated or used to do, e.g. `EVACUATION`.
- **Service:** a specific service delivered, e.g. `BARANGAY_ASSEMBLY`, `RELIEF_DISTRIBUTION`, or `PRIMARY_HEALTH_CARE`.

Example: a privately owned building may host a government PRC service unit. The PRC unit is a `GOV_ADMIN` facility unit; the building owner/host is private; the two must not be conflated. A barangay multipurpose hall used as an evacuation centre remains one physical facility with multiple sourced functions.

## 5. Ownership, operator, manager, host and access

Never represent these with a single `public/private` boolean.

### Ownership type

- `NATIONAL_GOVERNMENT`
- `LOCAL_GOVERNMENT`
- `GOCC`
- `PUBLIC_EDUCATIONAL_INSTITUTION`
- `OTHER_PUBLIC_BODY`
- `PRIVATE_CORPORATE`
- `PRIVATE_INDIVIDUAL_OR_PARTNERSHIP`
- `NGO_NONPROFIT`
- `COOPERATIVE`
- `RELIGIOUS_OR_FAITH_BASED_ORGANIZATION`
- `PUBLIC_PRIVATE_JOINT`
- `UNKNOWN`

### Operator/manager/host roles

Represent each as a dated relationship to an organization/entity. Owner, operator, manager/maintainer, host/landlord, funder, regulator and accreditor may all differ.

### Access class

- `PUBLIC_FREE`
- `PUBLIC_PAID_OR_CONDITIONAL`
- `SERVICE_USERS_ONLY`
- `APPOINTMENT_ONLY`
- `MEMBERS_OR_STUDENTS_ONLY`
- `STAFF_ONLY`
- `RESTRICTED`
- `UNKNOWN`

Do not infer public access from a facility being privately owned, publicly funded, licensed, or government-listed.

## 6. Facility hierarchy

Use the hierarchy when source evidence supports it:

`Facility Network / Campus / Compound → Site → Building → Facility Unit`

Examples:

- City Hall Complex → City Hall Building → Civil Registry Office.
- School Campus → School Buildings → School facility record.
- Barangay Compound → Barangay Hall, Covered Court, Daycare Centre and Health Station.
- Private Mall Site → PRC Offsite Service Centre (facility unit); the whole mall is not automatically a facility record.
- Hospital Complex → Hospital, Annex, Dialysis Unit, when separately identified.

Do not invent child buildings or sub-facilities when the source only identifies an institution/site.

## 7. Facility lifecycle and regulatory status

Keep physical lifecycle/operational status separate from licence, registration and accreditation status.

Lifecycle states may include:

- `PLANNED`
- `UNDER_CONSTRUCTION`
- `COMMISSIONED`
- `OPERATING`
- `TEMPORARILY_CLOSED`
- `UNDER_REPAIR`
- `INACTIVE`
- `CLOSED`
- `DEMOLISHED`
- `TRANSFERRED`
- `UNKNOWN`

Regulatory relationships must separately record issuer, licence/registration/accreditation type, source status, effective dates, expiry and scope/package. An expired accreditation does not prove the physical facility has closed.

## 8. Related but separate infrastructure assets

Roads, bridges, drainage systems, flood-control structures, dams, networks, power lines and other non-facility assets belong in a related infrastructure-asset model. A facility may link to them through `served_by`, `accessed_by`, `protected_by`, `project_delivered`, `located_within`, or `part_of_network` relationships.

## 9. Inclusion and exclusion examples

| Candidate | Decision | Reason |
|---|---|---|
| Public elementary school | Include: government facility | Official education facility |
| Private DepEd-recognized school | Include: private public-service provider | Education service with official source |
| Public hospital | Include: government facility | Public healthcare facility |
| PhilHealth-accredited private hospital | Include: private public-service provider | Authoritative provider listing; never count as government-owned |
| Barangay multipurpose hall | Include: government/community facility | Local public facility |
| Private mall hosting a PRC service centre | Include PRC service unit; mall only as host unless separately qualified | Distinguish service unit from host building |
| Private licensed meat establishment | Conditional include as regulated provider | Requires facility-level source, public-interest justification and rights review |
| Ordinary restaurant or retail shop | Exclude | No qualifying facility role merely by being open to customers |
| Private office building | Exclude | Ordinary commercial property |
| Church used as an officially designated evacuation centre | Include the sourced evacuation function with dates; do not infer government ownership | Verified public designation |
| Road or bridge | Related asset, not facility | Infrastructure network/asset model |
| Proposed evacuation-centre construction project | Project candidate only | Project does not prove completed/operational facility |

## 10. Taxonomy governance

Every new subtype requires:

1. definition and public-interest rationale;
2. inclusion/exclusion examples, including private/public cases;
3. source category mappings;
4. owner/operator/host/access semantics;
5. API code and display label;
6. migration/backward-compatibility assessment;
7. documentation and tracker update.

Do not create a new subtype for every source label. Map synonyms to a stable subtype while preserving original source terminology.
