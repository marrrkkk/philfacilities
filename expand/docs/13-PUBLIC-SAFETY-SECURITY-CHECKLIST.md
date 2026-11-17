# Public-safety and source security review checklist

Status: active checklist for emergency, justice, utility and critical-infrastructure
sources. It supplements the inclusion/publication policy and does not replace a
source-specific rights decision.

## 1. Before acquisition

- [ ] Identify the official custodian and the exact public route (directory, file, API,
      FOI release or agreement). Do not use third-party station lists as authority.
- [ ] Confirm that the route is public and that no CAPTCHA, WAF challenge, login,
      agreement prompt or download restriction will be bypassed.
- [ ] Record the source URL, retrieval method, access date, terms/rights basis and any
      explicit prohibition.
- [ ] Classify the source scope (national, regional, participating-LGU, selected-LGU,
      single-LGU or unknown) and the reference date.
- [ ] Decide whether the record is a public-facing facility, a security-sensitive
      operational site, or only an aggregate/project record.

## 2. Field-level minimization

Never publish, and do not place in normalized payloads:

- [ ] personal names of station commanders, officers, guards, social workers or
      household members;
- [ ] personal mobile numbers, private e-mail addresses, home addresses or IDs;
- [ ] troop strength, staffing rosters, shift patterns, response times, patrol routes,
      radio frequencies, access codes, key locations or alarm/CCTV details;
- [ ] cell/block/building locations inside prisons, jails, detention centres or
      residential-care facilities;
- [ ] weapon, ammunition, vehicle or equipment inventories;
- [ ] operational capacity, occupancy or evacuation-status values that could create a
      safety risk during an emergency;
- [ ] exact coordinates of sensitive sites where the source or custodian says the
      location should not be published.

Institutional fields that may be published after review: official facility name,
public service type, published office address or general service area, region/LGU,
public opening hours, official switchboard/institutional contact channel and
operator/owner type.

## 3. Publication decision

- [ ] The exact release is acquired and its schema/content inspected.
- [ ] No explicit restriction prohibits the intended reuse.
- [ ] Only reviewed institutional fields are exposed by the public API, map, search,
      statistics and exports.
- [ ] Provenance, attribution, publication basis and a takedown-on-notice route are
      recorded.
- [ ] Coordinates are labelled by method/precision; no building-level precision is
      implied for a centroid or geocoded point.
- [ ] A licence/accreditation is not presented as proof of current operation.
- [ ] The source-level rights gate remains enforced; excluding a sensitive record does
      not imply that the facility does not exist.

## 4. Current evidence

| Source | Decision | Evidence |
|---|---|---|
| NBI regional/district offices | Publish office name, region and printed location; withhold personal names, phone and protected e-mail; map-embed points labelled `map_geocoded` | `apps/ingest/philfacilities_ingest/sources/nbi.py`; release `NBI-OFFICES-2026-11-15` |
| PAGASA automated weather stations | Publish station identity only; live readings stay in a private dated artifact and are not exposed as current weather | `sources/pagasa_aws.py`; release `PAGASA-AWS-2026-11-15` |
| SSS branches | Publish branch name, postal address and region; withhold contact-person, e-mail and telephone/fax | `sources/sss_branch.py`; release `SSS-BRANCHES-2026-11-15` |
| PPA ports | Publish port identity, hierarchy and RORO marks; no coordinates, security detail or operational status inferred | `sources/ppa.py`; release `PPA-PORT-LIST-2026-11-15` |
| PNP stations, jails, BFP operational data | Not published; source acquisition/security review remains outstanding | AF5-03, AF5-04 and tracker blockers |

## 5. Incident handling

- [ ] If a published field is found to create a safety risk, unpublish the record or
      field at the source/release gate first, then record the change and notify the
      custodian/takedown contact.
- [ ] Do not delete historical source evidence; restrict it.
- [ ] Re-run the public API/export checks after any field removal.
