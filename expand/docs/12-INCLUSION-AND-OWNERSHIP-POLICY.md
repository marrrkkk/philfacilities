# 12 — Inclusion and Ownership Policy

**Status:** Binding product policy for PhilFacilities v3.0 and later.  
**Applies to:** Source discovery, ingestion, canonical identity, API, directory, map, statistics, exports and public claims.

## 1. The decision

PhilFacilities is a **single registry of all qualifying facilities in the Philippines, regardless of ownership or operator**. It includes:

1. government facilities;
2. private and non-government facilities that provide a meaningful public/essential service and are identified by authoritative records;
3. public-access civic, community, cultural, recreation, market, transport or other venues with an authoritative public function/designation.

This is not a registry of every physical building, parcel, company, store, restaurant, mall, factory, warehouse, home or point of interest. The project must be comprehensive across qualifying facility *types*, not indiscriminate about every structure.

## 2. One canonical registry, separate inclusion classes

All publishable records belong to the same canonical facility registry, search experience, map and public API. Do not create a disconnected “government database” and “private database”. Use a required inclusion-class field:

| Value | Meaning | Public? |
|---|---|---|
| `GOVERNMENT_FACILITY` | Facility owned, operated, maintained, or officially designated as a government/public facility by a public body | Yes, when source rights and safety permit |
| `PRIVATE_PUBLIC_SERVICE_PROVIDER` | Private, NGO, non-profit, cooperative, religious/non-profit or mixed facility providing a qualifying public/essential/regulated service | Yes, when inclusion criteria and source rights permit |
| `PUBLIC_ACCESS_VENUE` | Civic/community/cultural/recreation/market/transport venue with documented public access/function | Yes, when inclusion criteria and source rights permit |
| `DISCOVERY_CANDIDATE` | Unverified lead awaiting evidence, source, rights or safety review | No; internal only |

The API and UI must support filters by inclusion class, ownership, operator, category, subtype, geography, access class and verification state. Government facilities, private providers and public-access venues must be separately counted. A combined total must be labelled “all qualifying PhilFacilities records” or equivalent, never “government facilities”.

## 3. Mandatory inclusion test

A candidate must meet every applicable test below:

### 3.1 It is a physical facility or service location

The source must identify a physical place, site, campus, compound, building, branch, service counter, station, centre, venue or other locatable facility unit. An organization, company, agency, route, project, licence record without a physical location, geographic area, or general statistical count is not itself a facility.

### 3.2 It has a qualifying public-interest function

At least one must apply:

- government administration or public-facing government service;
- education, learning or training;
- healthcare or regulated health services;
- social welfare, residential care or protective services;
- emergency response, disaster preparedness or officially designated evacuation use;
- community, civic, sports, recreation or public-space function;
- public library, museum, archive, cultural or heritage function;
- public market, public-service commerce, food-safety or regulated supply-chain function;
- transportation, port, airport, terminal or mobility service;
- water, energy, waste, sanitation or other essential utility service;
- environmental, agricultural, fisheries or public-resource service;
- justice, correctional or legal public service, subject to security limits;
- another documented public, community, institutional or essential service approved under the taxonomy.

### 3.3 It has authoritative facility-level evidence

Examples of qualifying evidence:

- official government facility inventory;
- official public directory listing individual facility locations;
- official licence, registration, accreditation or recognized-provider directory that identifies a physical site;
- official LGU inventory or ordinance/designation;
- authoritative GIS layer with usable facility features and metadata;
- official FOI response supplying a specific facility dataset;
- official institutional directory with facility-level address/site information;
- documented data-sharing release from a responsible public body.

A company registration, an unrelated business permit, a generic map listing, a user submission, or a list of organizations without physical facility identities is not sufficient by itself.

### 3.4 Rights, privacy and safety permit publication

Acquisition, storage, transformation, derived outputs and public redistribution must be reviewed separately. If an explicit restriction applies or no publication decision has been recorded, keep the records internal or quarantined. A verified, publicly available source with no explicit prohibition may be published under the root [data inclusion and publication policy](../../docs/14-DATA-INCLUSION-AND-PUBLICATION-POLICY.md). Sensitive facilities/attributes may be excluded or generalized.

## 4. Facility categories and private inclusion examples

| Category | Government examples | Private/non-government examples that may qualify |
|---|---|---|
| Government administration | Barangay halls, city/municipal halls, agency offices, public service centres | Private host site containing an identifiable government service unit; the host building is not automatically included |
| Community/civic | Multipurpose halls, civic centres, barangay centres | Non-profit or privately operated community centre with official public-service designation |
| Education | Public schools, SUCs, LUCs, public training centres | DepEd-recognized private schools, CHED-listed private HEIs, TESDA-registered private TVIs |
| Healthcare | Public hospitals, RHUs, BHS, government clinics | DOH-licensed private hospitals/clinics, PhilHealth-accredited private providers, licensed laboratories/dialysis/birthing facilities |
| Emergency/DRRM | BFP/PNP stations, LGU evacuation centres, DRRM centres | Private site officially designated/contracted as an evacuation or response facility, subject to disclosure rules |
| Social welfare | DSWD/LGU CRCFs and centres | DSWD-accredited/licensed private, NGO, non-profit or faith-based residential/social-welfare facilities |
| Sports/recreation | Public courts, gyms, parks and sports complexes | Private/non-profit venue with authoritative public-access or community-service status; not every commercial gym |
| Public spaces | Public parks, plazas, playgrounds | Private property formally designated/maintained for public access or a documented civic purpose |
| Culture/knowledge | Public libraries, museums, archives | Private/non-profit library, museum, archive or cultural venue in an authoritative public directory and genuinely open to the public under stated conditions |
| Public commerce/food | LGU markets, public abattoirs, public trading facilities | Private licensed meat/food facilities only where facility-level identity and public-interest purpose justify inclusion; not every restaurant or shop |
| Utilities/sanitation | Government water/wastewater/waste facilities | Private regulated water, power, wastewater, waste-treatment and sanitation facilities with authoritative facility-level records |
| Transport | Government ports, airports, terminals | Private ports, airports, terminals and regulated transport facilities identified by authoritative sources |
| Environment/agriculture | Public nurseries, fisheries stations, research farms, protected-area facilities | Private regulated agricultural/fisheries service facilities only where the public-interest role and facility identity are documented |
| Housing/settlements | NHA/DHSUD/LGU service centres and resettlement community facilities | Non-profit community-housing service locations where officially recognized |
| Justice/corrections | Courts, public legal centres, jails | Private legal-aid/non-profit service centres when officially recognized and appropriate for public listing |

## 5. Explicit exclusions

Exclude by default:

- ordinary shops, restaurants, cafes, hotels, resorts, malls, supermarkets, cinemas and entertainment businesses solely because they are open to customers;
- ordinary offices, office towers, coworking spaces, factories, industrial buildings, warehouses and commercial premises;
- private residential buildings, houses, gated subdivisions and private property;
- a company, organization, school operator, hospital corporation, agency or programme without a physical facility record;
- places of worship solely because people can enter to worship. A specific officially designated evacuation/community service function may be represented as a dated function if supported by a source;
- roads, bridges, drainage networks, power lines, water distribution networks and other linear/network assets in the facility registry (use the related infrastructure-asset model);
- planned projects as operating facilities without completion/commissioning/operation evidence;
- records where publishing the location or attributes creates unacceptable privacy, safety or security risk.

### Host-site rule

A private mall, university campus, office building or other host property may contain a qualifying service unit. Represent the service unit as the facility and link it to the host/site when evidence supports that relationship. Do not add the whole host property automatically.

## 6. Required ownership and relationship fields

Ownership is not the same as inclusion class. For every record, capture these fields separately when known:

- `inclusion_class`;
- `ownership_type` and owner entity;
- `operator_type` and operator entity;
- manager/maintainer;
- host/landlord/site owner;
- funder/project sponsor;
- regulator/licensor;
- accreditor/recognition authority;
- licence/registration/accreditation type, scope, status and validity;
- `public_access_class` and conditions;
- source assertion/evidence for each relationship.

Suggested ownership values:

- national government;
- local government;
- GOCC;
- public educational institution;
- other public body;
- private corporate;
- private individual/partnership;
- NGO/non-profit;
- cooperative;
- religious/faith-based organization;
- public-private joint;
- unknown.

Suggested access values:

- public/free;
- public/paid or conditional;
- service-users only;
- appointment only;
- members/students only;
- staff only;
- restricted;
- unknown.

Do not infer owner/operator from regulator, source publisher, funder, accreditor, or host. If the source does not establish it, store `UNKNOWN`.

## 7. Public listing and user experience

The directory and map must present government and private qualifying facilities in one experience while making their status unambiguous.

Required filters/labels:

- Government facility;
- Private public-service provider;
- Public-access venue;
- Ownership;
- Operator;
- Facility category/subtype;
- Public-access conditions;
- Licence/accreditation status where source-backed;
- Source and reference date;
- Verification/location quality.

A private provider's accreditation must not be worded as a government endorsement, guarantee of quality, guarantee of current operation, or confirmation that a particular service is available right now.

## 8. API and statistics contract

The same facility endpoints return all approved classes. Require or support explicit filters such as:

- `inclusion_class=GOVERNMENT_FACILITY`
- `inclusion_class=PRIVATE_PUBLIC_SERVICE_PROVIDER`
- `inclusion_class=PUBLIC_ACCESS_VENUE`
- `ownership_type=PRIVATE_CORPORATE`
- `operator_type=LOCAL_GOVERNMENT`
- `public_access_class=PUBLIC_FREE`

Statistics must include separate values for each inclusion class and ownership type. Do not present private-provider or public-access-venue counts as government facility counts. Avoid a single “total facilities in the Philippines” claim unless the coverage denominator and inclusion method are clear.

## 9. Source discovery obligations

The agent must keep researching additional official government and authoritative regulator/provider resources. For each source, establish exact facility-level records, source ownership, actual fields, access/reachability, coverage, release dates, update patterns, licensing/accreditation semantics and the publication basis.

Prioritize source families likely to list private facilities:

- DepEd-recognized public and private schools;
- CHED public and private HEIs/campuses;
- DOH-licensed public and private health facilities;
- PhilHealth-accredited providers by benefit package;
- TESDA-registered public and private TVIs/assessment centres;
- DSWD-operated, LGU-accredited and private/NGO social-welfare centres;
- NMIS-licensed meat establishments and other eligible regulated food facilities;
- private ports, airports, terminals and utilities in authoritative agency directories;
- private/non-profit public-access cultural, library, recreation and community venues where official evidence exists.

A resource is not verified because its homepage loads. Inspect actual records or files, record exact evidence, and do not invent schema or coverage. Keep access evidence and the publication decision as separate statuses. The absence of an explicit licence is not automatically a prohibition; a verified public release can be published with reviewed institutional fields when the root-policy checklist is met.

## 10. Decision examples

| Candidate | Decision | Inclusion class / reason |
|---|---|---|
| Public elementary school | Include | `GOVERNMENT_FACILITY` |
| Private DepEd-recognized school with physical campus record | Include | `PRIVATE_PUBLIC_SERVICE_PROVIDER` |
| Public hospital | Include | `GOVERNMENT_FACILITY` |
| PhilHealth-accredited private hospital with identifiable site | Include | `PRIVATE_PUBLIC_SERVICE_PROVIDER`; accreditation is not ownership |
| Barangay multipurpose hall officially listed by LGU | Include | `GOVERNMENT_FACILITY` or `PUBLIC_ACCESS_VENUE` depending on evidence/ownership |
| Private mall hosting PRC service centre | Include PRC service unit, link private host | Government-operated service unit + private host relationship |
| Ordinary shopping mall | Exclude by default | Retail property alone does not satisfy inclusion test |
| Private licensed meat establishment | Conditional include | `PRIVATE_PUBLIC_SERVICE_PROVIDER` only with facility-level evidence, purpose and a publication decision |
| Private public library in official library directory | Include if public access and rights support it | `PUBLIC_ACCESS_VENUE` or provider class |
| Ordinary restaurant | Exclude | Customer-facing business alone is insufficient |
| Church officially designated as evacuation centre | Include dated evacuation function if safe and source-backed | Facility/venue with a verified public designation; ownership remains religious/private |
| Road or bridge | Separate related asset | Not a facility record |
| Proposed evacuation-centre construction contract | Project candidate only | Does not prove a completed facility exists |

## 11. Governance of policy changes

Any proposed expansion to a new private-sector facility class must document:

1. public-interest reason for inclusion;
2. why the source is authoritative for the facility;
3. facility-level identity evidence;
4. boundaries between facility, provider organization, site and host;
5. public-access and ownership semantics;
6. privacy, safety and licensing risks;
7. rights to publish source and derived fields;
8. effect on category counts and existing API clients.

Update this policy, taxonomy, source register, rights register and tracker together. This policy is binding when older documents use “government facilities” as shorthand.
