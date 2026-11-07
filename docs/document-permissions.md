# Proposed document permissions for the CruzBuy extension

Updated October 26, 2026. The companion `document-permissions.csv` inventories
all **34 top-level PDF/DOCX files** in `data/raw_policies`, the input directory
scanned by `scripts/ingest_policies.py`. It is a proposed access matrix for the
project, not an institution-approved distribution policy. Everyone in this design
already has school-authorized CruzBuy access. Permissions distinguish purchasing
responsibilities and assigned review duties, not school users from the public.
No runtime permissions,
Firestore profiles, ingestion code, or RAG code were changed.

## Five proposed roles

| Role ID | Intended user | Scope |
| --- | --- | --- |
| `cruzbuy_requester` | School-authorized user who shops and submits requisitions, such as a lab administrator or authorized student worker | Shared purchasing policies and released blank forms needed to prepare a purchase |
| `department_approver` | Assigned PI, budget approver, or department financial approver | Shared library plus approved operational review guidance for assigned purchases, including federal-funding checks |
| `procurement_buyer` | Central Procurement buyer reviewing restricted purchases and finalizing purchases/contracts | Shared library plus approved internal procurement and contract-review material |
| `risk_compliance_officer` | Verified UC employee assigned risk, privacy, security, or compliance review | Public material and internal documents needed for assigned reviews |
| `legal_counsel` | Verified UC Legal staff member assigned to the matter | Public material and specifically authorized internal/legal material |

Requester and approver responsibilities are described in UCSC's
[CruzBuy account guide](https://financial.ucsc.edu/Pages/Systems_CruzBuyGuide.aspx).
The [CruzBuy manual](https://financial.ucsc.edu/Pages/PS_CruzBuy_User_Manual_Guide.aspx)
also describes Procurement buyers. The risk/compliance and legal roles are proposed
extension roles, not claims that CruzBuy provides those exact account types.

These roles are proposed identifiers, not existing Firebase grants. Users may hold
multiple roles. Roles are not a clearance ladder. Application administrators do not
automatically receive document access. Authority to approve a purchase does not
automatically confer access to every internal or privileged source.

The extension must obtain roles and scope from a trusted school source or an
administrator-managed mapping. Google/Firebase sign-in alone does not establish
CruzBuy authorization or purchasing authority. The current project has no verified
automatic synchronization of CruzBuy roles. Browser page content and user-supplied
role claims must not become access grants.

## Reading the CSV

- `document` contains the exact source filename. `allowed_roles` lists proposed
  eligible roles separated by semicolons; the five yes/no columns show the same
  information in a filterable matrix.
- **A yes means role eligibility, not an unconditional grant.** Every row's
  `additional_access_conditions` and `recommended_retrieval_action` also apply.
  A hold blocks retrieval for every role until the specified owner approves it.
- `proposed_access_label`, `review_status`, `decision_basis`, and `evidence_location`
  distinguish an explicit source marking from a project recommendation or an
  unresolved release/distribution question.
- `sha256` identifies the exact reviewed bytes. New versions and completed forms
  require a new review; never transfer a blank template's public label to a filled
  copy automatically.
- `local_versioned_index_chunks` is a read-only count from the local versioned
  collection, not proof of availability to the current chat endpoint.

## Examples for the CruzBuy use case

These are proposed role differences **after the relevant owner approves access**.
All existing holds still apply. Specialist eligibility is not an unconditional
grant to view a document or send it to Qwen.

| Document | Proposed eligible roles | No default access | Why |
| --- | --- | --- | --- |
| BUS-63 Risk Matrix | Procurement buyer and assigned risk/compliance or legal reviewer | Routine requester or department approver without specialist duties | Explicitly marked internal. Proposed specialist scope supports contract-risk evaluation; owner must confirm this narrower mapping. |
| Procurement Conflict of Interest Training | Specifically authorized Procurement buyer or legal reviewer | Requester, department approver, and risk reviewer without separate authorization | Explicitly marked Attorney-Client Privileged. UC Legal must authorize the audience and AI use. |
| Federal Funds Checklist | Approver assigned federal purchases, Procurement buyer, assigned risk/legal reviewer | Routine requester by default in this proposal | Provisional workflow choice for checking funded purchases. No explicit marking proves requesters must be excluded; Procurement could authorize the released blank checklist for everyone. |
| Draft UK GDPR Addendum C | Procurement buyer and assigned privacy/risk/legal reviewer | Routine requester and department approver without draft-review duties | Unreleased working copy marked DRAFT. Keep out of operative-policy answers for all roles pending release. |
| Reviewed BUS-43 and blank SSPR form | All five roles | None on a role basis | Requesters and approvers both need the rules and blank forms. Access does not authorize purchases or expose completed supplier bids. |

The revised matrix proposes 30 eligible documents for requesters, 31 for department
approvers, 34 for Procurement buyers, 33 for risk/compliance reviewers, and 34 for
legal reviewers. These counts include held documents and historical copies;
they are **not counts of documents currently authorized for model retrieval**.

Do not hide general IS-3 security policy, BUS-50 controlled-substance policy, or
blank BAA/GDPR templates merely because their subject is sensitive. Restricted
purchasing authority and restricted policy visibility are different controls.

For a demonstration, a requester and an assigned risk reviewer illustrate the
proposed Risk Matrix boundary. Use synthetic content unless the owner authorizes
the AI use and presentation audience. Do not demonstrate leakage with the
privileged training deck.

## Decisions that matter

The Risk Matrix is explicitly marked **Confidential - Internal UC use only** in
the footer on all four pages. Its UC-internal restriction is supported by the
source. The revised proposal makes Procurement buyers and assigned risk/legal
reviewers eligible for this specialist review aid, subject to verified affiliation,
duties, and the Risk Management owner's approval. The source marking itself does
not exclude all requesters or approvers; this narrower role mapping needs owner
confirmation. An approver assigned risk-review duties could also hold a specialist
role rather than receiving blanket access through budget-approval authority.

The procurement conflict-of-interest training cover is marked **Attorney-Client
Privileged**. Keep it out of ordinary retrieval pending UC Legal's authorization
of the audience and the LLM use. Procurement buyers and legal counsel are listed
as potential recipients, not automatically authorized recipients. Use fictional
material for a public demonstration of this boundary.

The Federal Funds Checklist is a blank operational checklist whose intended
distribution and released version remain unconfirmed. Its provisional internal
handling carries forward the unresolved source review; it is not evidence that
the institution classified the template as confidential.

The UK GDPR Addendum C contains **DRAFT** in its first-page header. Limit the
unreleased copy to approved internal reviewers while release status is checked.
Draft status alone does not establish confidentiality.

Most other files contain general policies, standard contract language, or blank
forms. The proposed matrix allows all five roles to view those generic materials
after source verification. Security policy, controlled-substance policy, and
privacy templates are not classified as restricted merely because they discuss
sensitive subjects. A confidentiality clause describes how later information is
handled; it does not necessarily classify the template containing the clause.

The contracting-for-services PDF includes a blank notice with an internal UCOP
routing instruction on physical page 9. That instruction is not sufficient evidence
to restrict the whole general guideline. Confirm the form's distribution; completed
notices, employment-impact analyses, and attachments need separate classification.

The older BUS-43 copy and SSPR FAQ should be excluded from current determinations
because of version concerns, not hidden as confidential. Prefer the reviewed SSPR
PDF over the alternate DOCX. Those decisions are separate from who may view the
historical source.

## Corpus and runtime findings

The local Chroma database inspected on this date contains only
`uc_policies_945a4b6e903a4496`: 213 chunks for the reviewed BUS-43 PDF and 20 for the
reviewed SSPR PDF. The current `backend/rag/pipeline.py` requests `uc_policies`,
which is absent in this local snapshot. Thus 34 files are ingestion candidates;
this review does not claim all 34 are currently searchable by the running model.
No collection was rebuilt or renamed during this task.

The ingestion script does not apply this CSV or the offline manifest's review
statuses. Runtime document filtering is still to be implemented. The rule engine
also embeds facts and source quotations in `rules/provenance.py`, including FAR
material with no local source file. Any later permissions enforcement must cover
that answer path as well as retrieved chunks, section expansion, citations, and
caches. This CSV covers the 34 ingestible source documents, not external rules as
if they were local PDFs.

The requisition workbook in `data/raw` is outside this ingestion path and therefore
is not included as a policy document. If it is indexed later, review completed
purchase records separately for department, transaction, and assigned-review scope.

## Review method and next use

Extracted text from every PDF page and DOCX body/table, checked template fields and
document restriction markers, and inspected DOCX first-page headers for draft
markings. Visually checked the Risk Matrix and training cover markings. Source
identity and prior public verification come from `data/policies/document_manifest.json`
and `docs/policy-source-review.md`. No fresh official-site release verification was
performed, so unverified public proposals remain explicitly pending.

Before activating a policy, confirm release and access scope with its owner. Before
using restricted material in an AI demonstration, obtain authorization for that use
or substitute synthetic records. When implemented, copy approved document labels
to every chunk and enforce them on the server before sending context to Qwen.
