# Starter source review — October 10, 2026

This is a technical review of source identity, release evidence, extraction, and
access scope. It is not a claim that every procurement scenario has been approved
by a campus policy owner. SHA-256 pins the exact inspected bytes; filenames alone
never establish the release version.

| Document | Inspected version / provenance | Access decision | Runtime decision |
| --- | --- | --- | --- |
| BUS-43 | Official endpoint currently serves **INTERIM POLICY**, issued/effective January 26, 2026, 49 physical PDF pages | Public: downloadable without credentials through the official policy endpoint | Activate downloaded PDF; archive supplied 2021/2024 bytes |
| SSPR form | Official UCSC Forms Directory links a three-page PDF marked **Revised 12-2025** | Public: official campus directory and PDF are anonymously accessible | Activate exact downloaded PDF; retain supplied DOCX as archived alternate bytes |
| SSPR FAQ | Supplied PDF marked **Updated 4.2021** includes old federal thresholds | Public historical guidance; age does not make it internal | Archive; exclude from current determinations |
| Federal Funds Checklist | Supplied DOCX footer reads **Rev. 11.2025**; filename says 121525 | Retain conservative internal classification; current distribution scope unconfirmed | Keep under review. Official resource endpoint returned HTTP 403; do not infer current release from the filename or activate without verification |

## Provenance

- [Official BUS-43 endpoint](https://policy.ucop.edu/doc/3220485/BFB-BUS-43)
  serves `BUS-43_Interim_2026-01-26.pdf`, SHA-256
  `2ef396ba53f531ce94b90b81b72b3d439dcc3f7fa81deebb9a2c0df8e1206229`.
  The cover and revision-history page identify the interim release. A cookie-aware
  download is needed because the endpoint redirects to itself to establish a session.
- [UCSC Forms Directory](https://financial.ucsc.edu/Pages/Forms_Directory.aspx)
  links the [SSPR PDF](https://financial.ucsc.edu/Financial_Affairs_Forms/Source_Selection_Justification_Form.pdf),
  saved as `SSPR_Official_UCSC_2025-12.pdf`, SHA-256
  `5c09cfef834e37941faf7efd843879b887dd44b807a00199c0e4b3d1f73aef25`.
  All three pages were extracted and visually inspected, including funding columns,
  footnotes, signature fields and revision footers.
- The [UC Procurement BUS-43 update notice](https://procurement.ucop.edu/news/bus-43-live-heres-what-changed)
  documents 2026 changes. Its description is release context, not an additional
  rule or substitute for the policy bytes actually served by UC.
- [UC federal funding resources](https://procurement.ucop.edu/resources/p-policies/staff-resources/federal-funding-resources)
  could not be independently inspected. HTTP 403 alone does not establish the
  document's legal access classification. The checklist remains internal/review
  until a policy owner verifies the latest release and intended distribution.

Original files are preserved. Manifest `archived_sha256` identifies supplied byte
versions that must remain excluded even though a different version of the same
stable document identity has become active. Reference targets prefer non-archived
versions. Neither an explicit citation nor a newer date creates an override edge.

## Reproduce the starter corpus

Raw files and generated databases remain ignored. A teammate can restore the two
public verified PDFs and prepare their own index from the repository root:

```sh
./venv/bin/python -m scripts.download_starter_policies
./venv/bin/python -m scripts.build_policy_graph build
./venv/bin/python -m scripts.evaluate_policy_chat
```

The downloader refuses changed official bytes rather than automatically approving
a replacement, and does not overwrite a locally modified source. Future changes
require repeating the review and updating the hash.
The current runtime has two active public documents; the remaining supplied sources
are archived or need review. The review tool can still inspect all preserved sources.

## Remaining checklist verification

Using authorized UC access, obtain the current checklist linked from the official
resources portal, compare its exact bytes/content and revision marking with the
supplied DOCX, confirm the intended distribution, and record the result in the
manifest. If its bytes differ, preserve the supplied version as archived. Do not use
an older campus mirror merely to make the checklist pass verification.
