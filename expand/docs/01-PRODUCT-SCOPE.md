# 01 — Product Scope and Principles

## 1. Product definition

**PhilFacilities is a nationwide, source-linked registry of qualifying facilities in the Philippines, regardless of ownership or operator.** It brings together fragmented government, local-government, public-institution, regulated-provider, and other authoritative facility records into one normalized, versioned, searchable dataset with a public directory, map, API, and bulk downloads where source rights permit.

PhilFacilities is intended to help users answer:

- What facilities and public-service locations are recorded in a specific area?
- What is each facility called in its original source?
- What kind of facility is it, and which functions or services are documented?
- Who owns it, operates it, manages it, hosts it, funds it, regulates it, or accredits it?
- Is it government-owned, privately owned, jointly owned, NGO-operated, or unknown?
- Is it open to the public, conditionally accessible, appointment-based, or restricted?
- Where is it, and how precise is the location?
- Which source, release, and field-level evidence support each attribute?
- When was the underlying information reported, published, acquired, validated, and last changed?
- What changed between historical source releases?

## 2. Scope: all qualifying facilities, irrespective of ownership

PhilFacilities is **not limited to government-owned or government-operated facilities**. It includes qualifying government and private facilities when they have a public-service, community, institutional, essential-service, or regulated-provider role supported by an authoritative source.

The project is comprehensive in the *types of qualifying facilities it can represent*. It is not a census of every building, property, business, or physical structure in the Philippines.

A record may be included when at least one of the following conditions is met:

1. It is owned, operated, or maintained by a national government agency, LGU, GOCC, public university/college, or other public body.
2. It is officially designated, maintained, funded for public use, or recorded as a public/community facility by an appropriate authority.
3. It is a private or non-government facility providing a meaningful public, essential, educational, healthcare, social-welfare, transportation, utility, environmental, cultural, or other regulated service, and its existence/type/status is supported by an authoritative government or recognized public-interest source.
4. It is part of a government-recognized or regulated facility network (for example, licensed health establishments, accredited healthcare providers, registered schools, registered training providers, public-service ports/airports, or accredited social-welfare providers), subject to source terms and a clear public-interest reason for inclusion.
5. It is a publicly accessible civic, recreational, cultural, commercial-public-service, or community venue with authoritative evidence of its public function or designation.

The fact that a private facility is licensed, accredited, regulated, subsidized, funded, or listed by government does **not** make it government-owned. It may still qualify as a private public-service facility in the same registry, with its classification and regulatory relationship clearly represented.

Inclusion in the product scope is separate from the right to publish a particular record. Source rights are decided per dataset and release under the root [data inclusion and publication policy](../../docs/14-DATA-INCLUSION-AND-PUBLICATION-POLICY.md). A verified, publicly available release with no explicit prohibition may be published with reviewed institutional fields; explicit restrictions, agreements, and personal or sensitive data still control.

## 3. Three inclusion classes in one registry

Do not build unrelated databases or separate products for government and private facilities. Use one canonical facility registry and make the inclusion class explicit.

### 3.1 `GOVERNMENT_FACILITY`

Facilities owned, operated, maintained, or officially designated as government/public facilities by a national agency, LGU, GOCC, public university/college, or other public body.

Examples:

- barangay halls, city/municipal halls, provincial capitols, national/local government offices;
- government multipurpose halls, civic centres, covered courts, parks, plazas, playgrounds;
- public schools, SUCs, LUCs, public colleges, government training centres;
- public hospitals, RHUs, barangay health stations, government clinics;
- fire stations, police stations, evacuation centres, DRRM centres and public emergency warehouses;
- DSWD/LGU-operated social welfare and residential-care centres;
- public libraries, museums, archives and cultural centres;
- LGU public markets, public slaughterhouses, public terminals;
- government-operated utility, sanitation, water, wastewater and solid-waste facilities;
- government-owned/operated ports, airports, fisheries/agriculture facilities and environmental field facilities;
- public courthouses, jails and correctional institutions, subject to safety/disclosure limits.

### 3.2 `PRIVATE_PUBLIC_SERVICE_PROVIDER`

Privately owned, privately operated, NGO-operated, cooperative, religious/non-profit, or mixed facilities that provide a relevant public or essential service and are supported by a credible government or authoritative directory, licence, registration, accreditation, contract, or equivalent source.

Examples:

- private basic-education schools and private HEIs;
- private hospitals, clinics, laboratories, dialysis centres, birthing facilities and other licensed/accredited healthcare providers;
- private TESDA-registered training providers and assessment centres;
- private licensed/accredited social-welfare and residential-care providers;
- private ports, airports, terminals, utilities or other regulated public-service facilities where an authoritative source identifies the facility and public-service role;
- regulated food, meat, agricultural or fisheries establishments when their facility-level public-interest role is clear and the source supports inclusion;
- NGOs, non-profits or cooperatives operating recognized community or public-service facilities.

Private-provider records are first-class searchable facility records and may appear on the same map and API. They must be filterable and separately counted from government facilities. Accreditation or regulation must never be represented as government ownership, endorsement of service quality, or real-time availability.

### 3.3 `PUBLIC_ACCESS_VENUE`

A government or private physical venue that serves a broader civic, cultural, community, recreation, transport, market, or other public-access function, even if its operator is not a government agency.

Examples may include publicly accessible private markets, certain community sports facilities, public-service counters hosted inside malls, or privately operated cultural/community venues when an authoritative source establishes the public-service role.

Access conditions, charges, hours, operator and host must be shown when documented. A place being open to customers or visitors does not automatically qualify it for this class.

## 4. Inclusion test: what qualifies?

Before ingesting a facility, apply all of these questions:

1. **Physical place:** Is this a real facility, site, venue, service location, or identifiable facility unit rather than only an organization, project, route, asset network, or statistical count?
2. **Public-interest function:** Does it perform a public, community, educational, healthcare, social, cultural, emergency, transport, utility, environmental, institutional, or other qualifying service/function?
3. **Evidence:** Is there an authoritative, attributable source that identifies the facility or provides defensible evidence of its existence and role?
4. **Classification:** Can ownership, operator, manager, access class, regulatory relationship, or unknown values be represented honestly?
5. **Rights and safety:** Can the relevant attributes be lawfully stored, processed, and published without violating source terms, privacy, or security restrictions?

If a record fails the evidence or rights test, it may remain in an internal discovery queue, but it must not be published as a verified facility.

## 5. Exclusions and boundaries

PhilFacilities does not aim to list every physical building or every business.

Exclude by default:

- ordinary retail shops, restaurants, hotels, offices, malls, warehouses, factories and commercial buildings solely because they exist or admit customers;
- private homes, residential buildings, gated subdivisions and other private residential property;
- a company, school operator, hospital corporation, government agency, programme or legal entity without an identifiable physical facility;
- ordinary places of worship solely because they are open to worshippers; include only when an independently documented qualifying public-service function exists (for example, an officially designated evacuation centre), and represent that function without misclassifying the venue;
- roads, bridges, drainage lines, flood-control structures, power lines, utility networks and other infrastructure assets as facility records; these belong in a related asset model and can be linked to facilities;
- proposed or funded projects that do not yet establish a completed/commissioned facility;
- sensitive military, intelligence, critical-infrastructure, correctional, law-enforcement, or emergency operational details where disclosure creates safety/security risk.

A commercial property may host a qualifying facility unit, such as a PRC offsite service centre or government service counter. Record the service unit and its host/site relationship; do not automatically list the entire mall or building as a PhilFacilities public-service facility.

## 6. Ownership, operation, management, host and public access are separate

Never collapse these into a single `public/private` boolean.

Track independently, with source evidence and effective dates where available:

- legal/property owner;
- facility operator;
- managing/maintaining entity;
- host or landlord/site owner;
- funder or project sponsor;
- regulator/licensor;
- accreditor;
- public-access class;
- inclusion class (`GOVERNMENT_FACILITY`, `PRIVATE_PUBLIC_SERVICE_PROVIDER`, `PUBLIC_ACCESS_VENUE`, or internal `DISCOVERY_CANDIDATE`).

Use `UNKNOWN` rather than inferring an owner or operator from the agency that publishes a directory. A regulator is not automatically the owner or operator.

## 7. One physical place, multiple records, functions and services

### 7.1 One place, multiple source records

A hospital may appear in DOH NHFR, a PhilHealth accreditation list, a local-government inventory and a Geoportal layer. Preserve each source record and link them to one canonical facility only when identity evidence is sufficient.

### 7.2 One place, multiple functions

A barangay multipurpose hall may also be a covered court, community assembly site and designated evacuation centre. Represent one physical facility with multiple dated functions/designations instead of duplicate pins.

### 7.3 One site, multiple units

A mall or government compound can host a government service counter, clinic, library branch, or multiple independent facilities. Model a site/host and separate facility units when source evidence supports that distinction.

### 7.4 Site, building and infrastructure asset are distinct

A government or private campus may contain several buildings. A public market may occupy a compound. A service counter may exist inside a private host building. Do not invent structure-level detail that the source does not identify.

## 8. Status and evidence principles

- Facility existence is not proof of current operation.
- A licence or accreditation is not proof of real-time service availability.
- Public access is not the same as government ownership.
- Government funding is not ownership.
- A private provider's accreditation is not a government endorsement.
- A new download date does not make an old source reference period current.
- Missing from a new source release does not automatically mean closed or demolished.
- Missing coordinates do not mean the facility is outside a geographic boundary.
- User-submitted corrections are proposals until reviewed and supported.

## 9. Coverage and counting principles

Publish separate counts and coverage for:

- government facilities;
- private public-service providers;
- public-access venues;
- facilities with unknown ownership;
- source/agency and category;
- geographic coverage and source reference period.

A combined registry total may be shown only with a clear explanation of the included classes. Never call the combined total “government facilities”.

Do not claim national completeness without a defined facility universe, a defensible denominator, source evidence, and known treatment of missing/non-reporting areas.

## 10. Product outcomes

1. One searchable national registry and map for all qualifying facility classes, regardless of ownership.
2. A versioned, machine-readable dataset with government/private/access distinctions.
3. A documented public API and bulk exports for fields whose source rights permit publication.
4. Source provenance, rights, coverage and data-quality reporting.
5. Historical facility and source-release changes.
6. A repeatable contribution/onboarding path for agencies, LGUs, private regulated providers and recognized organizations.

## 11. Non-goals

- A census of every building, business, property or point of interest.
- Real-time opening hours, bed availability, staffing, occupancy, appointments or service queues unless an authoritative live source exists.
- Automatically accepting every private provider listed by any third-party directory.
- Treating accreditation as quality ranking or service guarantee.
- A crowdsourced map where submissions automatically become verified.
- Predicting safety, quality, or service availability from facility category alone.
- Full infrastructure-network mapping inside the facility registry.
- Rebuilding the completed website, API, database infrastructure, map, design system or deployment architecture.
