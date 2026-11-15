# PhilFacilities — Source Rights and Publication Register

**Purpose:** Track source-specific acquisition, storage, transformation, attribution, privacy, and redistribution decisions. This is an operational register, not legal advice.

## Status definitions

- `UNKNOWN` — no rights review has been completed.
- `REVIEW_REQUIRED` — source/terms are known but a decision is outstanding.
- `PUBLICLY_AVAILABLE_VERIFIED` — exact release verified and publicly available; no explicit licence or permission found; no explicit prohibition applies; only reviewed non-personal fields are published with provenance, attribution, and takedown-on-notice.
- `APPROVED_INTERNAL_USE` — storage/internal processing permitted within documented limits; public release not permitted.
- `APPROVED_DERIVED_ONLY` — approved fields/derived outputs may be published, but original records may not be redistributed.
- `APPROVED_PUBLIC_REDISTRIBUTION` — public distribution permitted under stated conditions.
- `APPROVED_WITH_ATTRIBUTION` — public distribution permitted with specified attribution/terms.
- `RESTRICTED_NON_REDISTRIBUTABLE` — source may be viewed/acquired but cannot be republished.
- `DENIED` — permission denied.
- `EXPIRED` — permission/contract no longer valid.

`PUBLICLY_AVAILABLE_VERIFIED` is not a claim of public domain. It is a documented product decision under the root policy in [`docs/14-DATA-INCLUSION-AND-PUBLICATION-POLICY.md`](../docs/14-DATA-INCLUSION-AND-PUBLICATION-POLICY.md). Explicit restrictions always control.

## Initial register

| Source ID | Publisher | Known access terms / issue | Current rights status | Publication status | Required next action |
|---|---|---|---|---|---|
| `psa.psgc` | PSA | Official data file/API; verify PSA data use/redistribution conditions and API terms | REVIEW_REQUIRED | BLOCKED pending decision | Save exact terms/reference and decide field/file redistribution |
| `psa.openstat` | PSA | BetterGov snapshot API may include source-specific PSA tables; each source table may have different rights considerations | REVIEW_REQUIRED | BLOCKED by source-level decision | Review PSA terms and specific table provenance; do not rely on BetterGov software licence |
| `deped.school_masterlist` | DepEd | Official Machine-Ready Files have a human download/terms flow | REVIEW_REQUIRED | BLOCKED | Save terms accepted for exact release; determine transformation and redistribution rights |
| `deped.ebeis_masterlist` | DepEd | Public EBEIS result set; institution-level fields; school-head names are personal data | APPROVED_WITH_ATTRIBUTION | PUBLISHED (current release); canonical rows INTERNAL pending field-level review | Publish institution-level fields with attribution; keep school-head names private; complete field-level mapping/privacy review before canonical rows become public |
| `deped.enrollment` | DepEd | File-specific coverage and release terms require inspection | REVIEW_REQUIRED | BLOCKED | Record exact file, terms, reference year, and fields approved |
| `deped.school_facilities` | DepEd | File-specific terms and reporting year | REVIEW_REQUIRED | BLOCKED | Review terms and field-level use |
| `deped.ict_wash_personnel` | DepEd | Separate file families; exact terms/schema must be checked | REVIEW_REQUIRED | BLOCKED | Review each dataset/release, not one blanket DepEd approval |
| `doh.nhfr` | DOH | FOI disclosures include a signed Agreement for Release and Use of Health Data; source export may be access-blocked | REVIEW_REQUIRED | BLOCKED | Review exact signed agreement and field-level publication rights |
| `doh.licensed_facilities` | DOH/HFSRB | Official directory/list; terms and exact downloadable files require review | REVIEW_REQUIRED | BLOCKED | Capture terms/attribution and current file metadata |
| `philhealth.accredited_hospitals` | PhilHealth | Public dated PDF; parser exists; PhilHealth's public disclaimer permits use/reproduction for educational or informative purposes | APPROVED_WITH_ATTRIBUTION | PUBLISHED | Retain attribution and source dates; re-check each release and category |
| `philhealth.other_categories` | PhilHealth | Separate public provider files; category-specific fields; same public disclaimer | APPROVED_WITH_ATTRIBUTION | PUBLISHED (except the blocked Antenatal release) | Review each category and release; keep the Antenatal release blocked until validated re-ingestion |
| `deped.private_schools` | DepEd | Private-school records may be present in the same official school masterlist as public schools; inclusion does not change ownership. | REVIEW_REQUIRED | BLOCKED | Verify source-level school sector, facility identity and exact file terms; publish private school records as `PRIVATE_PUBLIC_SERVICE_PROVIDER` only where redistribution is permitted. |
| `doh.private_health_facilities` | DOH/HFSRB | DOH/NHFR and licensing lists may include private providers. | REVIEW_REQUIRED | BLOCKED | Review the exact agreement/source fields and permission for private-provider records; retain private ownership and licence scope. |
| `philhealth.private_accredited_providers` | PhilHealth | Accreditation lists include private hospitals and other providers; covered by the same published PhilHealth releases and public disclaimer | APPROVED_WITH_ATTRIBUTION | PUBLISHED with the PhilHealth provider records | Keep private ownership and inclusion class distinct; do not count private providers as government facilities |
| `tesda.private_tvis` | TESDA | Public directory/statistics may include private training institutions; provider-level bulk access remains unverified. | UNKNOWN | BLOCKED | Acquire an authoritative provider-level release and review terms before inclusion. |
| `ched.private_heis` | CHED | HEIDA may list private HEIs alongside public institutions; bulk/API status remains unverified. | UNKNOWN | BLOCKED | Acquire permitted institution/campus-level records and review source terms. |
| `ched.heida` | CHED | Public directory; bulk/API status not verified | UNKNOWN | BLOCKED | Acquire a permitted source before rights review |
| `tesda.providers` | TESDA | Searchable directory; bulk/API status not verified | UNKNOWN | BLOCKED | Acquire a permitted source before rights review |
| `dilg.drrm_pulse` | DILG-NCR | Public map/profile data from participating LGUs; no blanket bulk redistribution terms verified | REVIEW_REQUIRED | BLOCKED pending layer/data terms | Contact DILG-NCR/data owner; inspect public API/export and terms |
| `dilg.lgu_facility_inventory` | LGUs / DILG | Section 524 supports existence of periodic inventories; each LGU dataset and rights may differ | REVIEW_REQUIRED | BLOCKED per-LGU | Record LGU consent/FOI terms and scope for every release |
| `geoportal.facility_layers` | NAMRIA/Geoportal and originating data agencies | Geoportal layer restrictions vary; inventory identifies open, conditional, restricted, and not-indicated layers | REVIEW_REQUIRED | BLOCKED per layer | Create one rights decision per layer/source owner/release |
| `dpwh.ngob_inventory` | DPWH / national agencies | DPWH DO 247 s.2024 describes inventory forms; actual inventory release/terms unverified | UNKNOWN | BLOCKED | Request actual inventory and disclosure terms |
| `dpwh.transparency_projects` | DPWH | Public project/contract transparency portal; project data reuse terms and source attribution need review | REVIEW_REQUIRED | BLOCKED pending terms | Capture terms and distinguish project fields from facility facts |
| `bfp.fire_stations` | BFP | 2025 FOI response linked logistical report and fire stats; attachments and reuse terms require review | REVIEW_REQUIRED | BLOCKED | Acquire original attachment, inspect metadata, ask about reuse/updates |
| `pnp.police_stations` | PNP | No verified national public bulk list; Geoportal layer is candidate discovery source | UNKNOWN | BLOCKED | Obtain authoritative source and disclosure/rights decision |
| `ocd.evacuation_centres` | OCD/NDRRMC/LGUs | Source and national coverage not fully verified | UNKNOWN | BLOCKED | Obtain exact source/custodian and terms |
| `dswd.crcf` | DSWD | Official web directory and dated Standards Bureau directories | APPROVED_WITH_ATTRIBUTION | PUBLISHED (76 facilities) | Publish institutional name, field office and postal address with attribution; do not infer coordinates, admission rules, or operational status |
| `dswd.lgu_accredited_centres` | DSWD / LGUs | Dated accreditation list; distinguish government-operated and accredited providers | REVIEW_REQUIRED | BLOCKED | Review each list's permitted use and ownership status |
| `nlp.public_libraries` | National Library of the Philippines | Official December 2025 PDF; institutional library fields; contains named librarians and personal contact fields | APPROVED_WITH_ATTRIBUTION | PUBLISHED | Publish institution-level fields only; keep personal librarian contacts private; retain attribution |
| `nationalmuseum.museums` | National Museum of the Philippines | Official museum location directory and linked site pages | APPROVED_WITH_ATTRIBUTION | PUBLISHED | Publish institutional museum fields with attribution; verify operator/status of each location; directory subset only |
| `bir.revenue_district_offices` | Bureau of Internal Revenue | RAO 006-2025 lists revenue regions and RDOs; image-only PDF processed with local OCR | APPROVED_WITH_ATTRIBUTION | PUBLISHED | Publish office/jurisdiction fields with attribution; retain OCR evidence; do not infer addresses or coordinates |
| `phlpost.post_offices` | Philippine Postal Corporation | Public locator lists post-office name, province, address and services; page carries a copyright/all-rights-reserved notice | APPROVED_WITH_ATTRIBUTION | PUBLISHED (1,272 facilities); earlier release INTERNAL | Publish only factual locator fields with attribution and takedown-on-notice; record the notice; keep hosted-counter distinctions |
| `dpwh.public_buildings_foi` | DPWH | FOI request listed as pending in research snapshot; no file acquired | UNKNOWN | BLOCKED | Check current request status and terms if data received |
| `nha.maps` | NHA | Public map portal with project/land/occupancy layers; layer-specific terms unverified | REVIEW_REQUIRED | BLOCKED per layer | Inspect metadata/download conditions and public-use scope |
| `doTr.ports_airports` | DOTr/PPA/CAAP | Geoportal lists relevant layers; independent current authority/data access requires validation | UNKNOWN | BLOCKED | Acquire authoritative current source and rights decision |
| `lwua.water_districts` | LWUA | Utility directory may describe entities rather than physical facilities | UNKNOWN | BLOCKED | Determine exact physical facility dataset and terms |
| `denr.facilities` | DENR bureaus | Candidate agency layers; dataset-specific source/rights unknown | UNKNOWN | BLOCKED | Acquire and review each dataset |
| `da_bfar.public_facilities` | DA/BFAR/NMIS/NFA | Discovery target; facility-level source not verified | UNKNOWN | BLOCKED | Find actual official facility list and terms |
| `bjmp_bucor.facilities` | BJMP/BuCor | Discovery target; security disclosure limits apply | UNKNOWN | BLOCKED | Verify public listing and conduct security review |

## Additional researched resources — review required before use

The following newly identified source IDs do not yet have a completed publication decision in the initial register. A public directory, FOI response, government portal, map layer, or downloadable report is **not** a blanket redistribution licence. It is also not, by itself, a prohibition: a verified, publicly available release may be published under the root policy in [`../docs/14-DATA-INCLUSION-AND-PUBLICATION-POLICY.md`](../docs/14-DATA-INCLUSION-AND-PUBLICATION-POLICY.md) when no explicit restriction applies and only reviewed institutional fields are exposed. The ownership-inclusive product scope makes qualifying private-provider records eligible for inclusion, but never changes the source-rights decision or the provider's private ownership classification. These entries stay blocked until exact source/release terms are reviewed and a decision is recorded.

| Source ID | Publisher / custodian | Resource and rights considerations | Current rights status | Publication status | Required next action |
|---|---|---|---|---|---|
| `dilg.subaybayan_evacuation_projects` | DILG | Project monitoring records for evacuation-centre projects; not an operational-facility masterlist. | REVIEW_REQUIRED | BLOCKED | Review Subaybayan terms and source-field reuse; publish only permitted project facts and keep project/facility entities separate. |
| `dilg.evacuation_ncr_foi` | DILG-NCR | FOI-supplied NCR-only evacuation-centre inventory; attachment terms and personal/security fields need review. | REVIEW_REQUIRED | BLOCKED | Inspect original attachment and FOI conditions; exclude sensitive details and preserve NCR-only coverage. |
| `dilg.barangay_halls` | DILG / LGUs / NAMRIA | FOI response did not provide a national hall inventory; barangay masterlist is not a hall dataset. | UNKNOWN | BLOCKED | Seek an actual source from LGUs/NAMRIA; create a release-specific rights decision only after a concrete dataset is acquired. |
| `dilg.public_markets` | LGUs | DILG says primary records are held locally; no national central list verified. | UNKNOWN | BLOCKED | Review rights separately for each LGU inventory/FOI release. |
| `eccd.ncdc_cdc` | ECCD Council / DSWD / LGUs | NCDC lists, annual-report annexes, CDC profile forms and possible MIS records; ownership/operator varies. | REVIEW_REQUIRED | BLOCKED | Review exact source terms and separate government-operated NCDCs, LGU CDCs, NGO/private/workplace centres. |
| `dswd.private_social_welfare_agencies` | DSWD / private agencies | Private licensed/accredited providers; eligible as `PRIVATE_PUBLIC_SERVICE_PROVIDER` when facility-level identity and public-interest criteria are met; never government-owned by virtue of accreditation. | REVIEW_REQUIRED | BLOCKED | Include as first-class provider records in the same registry when they meet the inclusion policy; classify `PRIVATE_PUBLIC_SERVICE_PROVIDER`, separate their counts from government facilities, and review privacy/republication limits. |
| `dti.negosyo_centers` | Department of Trade and Industry / host LGUs or institutions | Public finder backed by unauthenticated JSON endpoints; 1,427 active center records across 17 regions. Terms permit quoting/reproduction with DTI credit and restrict commercial resale/redistribution/derivative works without consent. Centers may be co-located with LGU/partner hosts; ownership and operator are not stated. | APPROVED_WITH_ATTRIBUTION | PUBLISHED (1,427 active center records) | Publish factual center name, postal address, region/province/city and source active flag with attribution and takedown-on-notice; withhold phone/email; do not infer coordinates, owner, operator, host, hours or access. |
| `dti.shared_service_facilities` | DTI / Geoportal / local partners | Geoportal catalogue candidates for shared-service facilities; funding/support does not establish ownership. | REVIEW_REQUIRED | BLOCKED | Review each layer and facility's owner/operator/host before publication. |
| `prc.offices_and_service_centers` | Professional Regulation Commission | Official office/offsite-centre directory and locator; some service points are hosted in private malls/LGU sites. | REVIEW_REQUIRED | BLOCKED | Review website terms and attribution; distinguish PRC operator from building owner/host. |
| `ppa.ports` | Philippine Ports Authority / port owners and operators | Official port list distinguishes government and private ports; PPA-managed base ports and TMO/OTP entries are government facilities, other government ports have an unstated owner, and private ports are providers without an inferred owner/operator. | APPROVED_WITH_ATTRIBUTION | PUBLISHED (574 rows: 303 government, 271 private) | Publish factual port name, PPA region/PMO hierarchy, group, RORO/NON-RORO marks and remarks with attribution; do not infer coordinates, berth capacity, owner names or operational status. |
| `caap.airports` | Civil Aviation Authority of the Philippines / airport operators | Area-centre and aerodrome directories; CAAP regulatory oversight does not prove ownership/operation. | REVIEW_REQUIRED | BLOCKED | Review AIP/directory conditions; validate operator and current status per airport. |
| `pfda.fish_ports` | Philippine Fisheries Development Authority / LGUs | Regional fish ports and municipal fish-port programme; some sites transferred to or co-managed with LGUs. | REVIEW_REQUIRED | BLOCKED | Obtain current inventory and terms; record turnover and co-management arrangements. |
| `nmis.meat_establishments` | National Meat Inspection Service / regulated establishments | NARIS and licensed-establishment lists include private companies; eligible facility-level establishments may be provider records, not government facilities. | APPROVED_WITH_ATTRIBUTION | PUBLISHED (357 establishments) | Publish factual establishment name, LTO number, type and postal address; classify operators as `PRIVATE_PUBLIC_SERVICE_PROVIDER` where applicable; never count as government-owned |
| `emb.air_quality_stations` | DENR Environmental Management Bureau | Station directories and monitoring reports; measurement data may have separate terms from station metadata. | REVIEW_REQUIRED | BLOCKED | Review station metadata and observation-feed terms separately; minimize sensitive details. |
| `bmb.protected_areas` | DENR Biodiversity Management Bureau | Protected-area boundaries/dashboard are areas, not facility records; source may contain caveats and restrictions. | REVIEW_REQUIRED | BLOCKED | Review GIS layer licence/attribution and use only as contextual spatial data. |
| `open_data_philippines` | DICT / Open Data Philippines and contributing agencies | Catalogue/discovery portal; underlying dataset licences belong to original publishers. | REVIEW_REQUIRED | BLOCKED | Trace every dataset to its original agency and record source-level rights; do not treat portal visibility as permission. |
| `namria.base_maps_and_boundaries` | NAMRIA | Official geospatial data and map products with product-specific terms and possible access controls. | REVIEW_REQUIRED | BLOCKED | Review exact dataset licence, attribution, scale and redistribution terms. |

### Important rights interpretation

- `FILE/DOCUMENT VERIFIED`, `DIRECTORY CONTENT VERIFIED`, `FOI ACCESS CONFIRMED`, and `OFFICIAL PORTAL VERIFIED` are evidence labels, not legal approvals.
- A government agency's ability to publish a record does not automatically grant PhilFacilities the right to mirror it. Equally, the absence of an explicit licence does not by itself bar publication of factual institutional fields under the root policy.
- A directory may contain personal contact information; collect only what is necessary for the public facility purpose.
- A licensed/accredited private provider may be included as a first-class `PRIVATE_PUBLIC_SERVICE_PROVIDER`, but remains private unless authoritative evidence establishes government ownership. Keep inclusion class and ownership separate.
- A project, GIS polygon, landholding, protected area, or monitoring feed is not automatically a facility record.
- Where an explicit restriction, agreement, or FOI condition applies, keep the dataset internal/quarantined and follow that condition. Where the position is simply unclear, verify the exact release and record a publication decision rather than treating silence as permission or as a permanent bar.

## Decision record template

For every source/release, record:

- source ID and source release ID;
- original publisher and data owner;
- official URL and acquisition method;
- exact licence, terms, agreement, circular, or FOI response URL;
- if no explicit licence exists: the exact public route used, the verified release, and evidence that no explicit prohibition applies;
- date terms were checked;
- reviewer/approver;
- permitted purpose(s);
- storage/retention limits;
- transformation/derived-data rights;
- redistribution/public API rights;
- required attribution;
- fields excluded or redacted;
- personal/sensitive data review;
- expiry/review date;
- decision and rationale.

Do not mark a dataset `APPROVED` because its source page is public. A source can be visible while an explicit agreement or other restriction still controls. Equally, do not treat the absence of a licence as an automatic refusal: record the verified public route and the basis for a `PUBLICLY_AVAILABLE_VERIFIED` decision when the root-policy checklist is met.


## v3.0 ownership-inclusive publication rule

A qualifying private facility may be published in the same PhilFacilities registry/API as government facilities, provided its exact source/release/fields are approved for publication (including under the verified-public-availability policy) and it meets `docs/12-INCLUSION-AND-OWNERSHIP-POLICY.md`. This does not make it government-owned or government-operated. Keep separate inclusion class, ownership, operator, regulator/accreditor, access conditions and count metrics.

Review rights for private providers at least as carefully as government source records. A regulator's authority to publish a list does not automatically authorize PhilFacilities to republish all fields. Some fields may be publishable while personal contacts, detailed coordinates, or other attributes remain excluded.
