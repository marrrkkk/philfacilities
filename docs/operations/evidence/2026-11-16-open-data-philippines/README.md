# Open Data Philippines catalogue/API probe — 16 November 2026

## Purpose

Test whether Open Data Philippines (ODPH, `data.gov.ph`) provides a usable facility inventory or only a discovery catalogue, and record the exact API/rights limits for tracker task **AF1-29**.

## Access path

- Public portal: <https://data.gov.ph/> (HTTP 200; Angular single-page application).
- Public catalogue API host: `https://api.data.gov.ph`.
- The SPA calls public endpoints such as `/api/public/open-data/count`, `/api/public/topic/search`, `/api/public/dataset/search`, and `/api/public/dataset/featured`.
- Requests without the SPA's `X-API-KEY` header return HTTP 401:

  ```json
  {"success":false,"message":"API Key not found.","data":"Not authorized to access this resource"}
  ```

- The key is a public client value derived in the SPA bundle; it is not copied into this repository. Queries below were made as the public site does, with that client header.

## Catalogue result

`GET /api/public/open-data/count` returned:

```json
{"resources":2586,"datasets":175,"organizations":17}
```

A paged `POST /api/public/dataset/search` (`{"search":"","limit":1000}`) returned all 175 published dataset records. The extracted names, identifiers, publishers, topics, tags and resource formats are in [`catalogue-summary.json`](catalogue-summary.json).

Publisher distribution (17 organizations):

| Publisher | Datasets |
|---|---:|
| Department of Health | 133 |
| Commission on Higher Education | 6 |
| Department of Transportation | 6 |
| Department of Education | 6 |
| Commission on Filipinos Overseas | 5 |
| Mines and Geosciences Bureau (DENR) | 4 |
| National Commission for Culture and the Arts | 3 |
| Department of Tourism | 2 |
| Technical Education and Skills Development Authority | 2 |
| Employees' Compensation Commission | 1 |
| Department of Energy | 1 |
| Metropolitan Manila Development Authority | 1 |
| Bureau of Jail Management and Penology | 1 |
| Department of Agriculture | 1 |
| Philippine Statistics Authority | 1 |
| PNP Anti-Cybercrime Group | 1 |
| Department of Labor and Employment | 1 |

### Facility-relevant candidates

| Dataset | Publisher | What it actually is | Disposition |
|---|---|---|---|
| SY 2020-2021 Masterlist of Schools | DepEd | Facility-level PDF (“Address only”), 5,893,824 bytes, created 2023-01-03 from the DepEd datasets page | **Not acquired.** Resource download returned HTTP 400 `{"message":"Error on retrieving file"}` / “File not found”; dataset-detail and resource-detail routes returned “Dataset details not found” / “Resource details not found”. The original DepEd datasets page returned HTTP 403 maintenance. |
| CY 2020 Last Mile Schools Program in Public Elementary and Junior High School | DepEd | Project/classroom-construction progress PDF (495,038 bytes) | Not a current facility inventory; not ingested. |
| Historical Enrollment Data; Historical Number of Schools by Level of Education; Historical Number of Teachers (Public) | DepEd | Aggregate statistics | Not facility-level. |
| COVID-19 DOH Data Drop (133 dated datasets) | DOH | Case/health situation data by date | Not a facility inventory. |
| Local Inventory of Cultural Property (PRECUP); Local Inventory of Cultural Property (TALAPAMANA) | NCCA | Potential cultural-property inventories | Candidate follow-up; not inspected or published in this slice. |
| MEIPD directories of operating metallic/non-metallic mines | MGB/DENR | Industrial operating sites | Not a qualifying public-service facility category for this release. |
| Higher Education Statistical Data; TVET statistics; annual reports | CHED/TESDA/other | Aggregate statistics and reports | Not facility-level directories; current CHED HEIDA and PhilHealth releases remain the facility sources of record. |

No dataset in the catalogue is a national barangay-hall, fire-station, police-station, public-market, evacuation-centre, health-facility, library or public-office inventory. The catalogue is therefore **discovery only** and is not the owner of the underlying records.

## Rights and terms

The ODPH site states that, unless otherwise indicated, datasets accessed through the portal are offered free and without restriction, with attribution to the publishing agency; datasets with different governing licences must be used under the licence in their metadata. The catalogue record for the DepEd masterlist says `Open [open]`. This does **not** transfer ownership: DepEd remains the publisher/data owner, and the exact file was unavailable, so no ODPH-sourced release is published.

## Conclusion

- ODPH exposes a working public catalogue API, but it is a discovery layer over agency datasets, not a national facility register.
- 175 datasets / 2,586 resources / 17 organizations were enumerated; the only facility-level school file was not retrievable and the original DepEd page was blocked by maintenance.
- AF1-29 acceptance evidence is met as a documented finding: dataset IDs and original publishers traced, API/authentication/terms tested, and the catalogue was not mistaken for the owner.
- No ODPH record was ingested. Future work should re-test the DepEd masterlist resource and inspect the NCCA cultural-property datasets separately under their own release decisions.
