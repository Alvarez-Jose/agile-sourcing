'''
Gist of this is to have tags chunk with richer metadata so the retriever
can filter by policy type
'''

# This Maps filenames to human readable policy names
POLICY_MAP = {
    # ---- Procurement & Supply Chain ----
    "BUS43_ProcurementSupplyChainManagement_Main_Policy.pdf": "BFB-BUS-43: Procurement & Supply Chain Management",
    "SOURCE_SELECTION___PRICE_REASONABLENESS_JUSTIFICATION_FORM__1_.docx": "Source Selection & Price Reasonableness Justification Form",
    "Federal_Funds_Checklist-121525__2_.docx": "Federal Funds Checklist",
    "ssprfaq.pdf": "Source Selection & Price Reasonableness FAQ",
 
    # ---- Risk, Insurance & Compliance ----
    "BUS63_Risk_Matrix_9192025.pdf": "BUS-63: Risk Matrix",
    "UCRK25762_BFBBUS63_RiskTransferInsuranceRequirements_Accessible_1.pdf": "BFB-BUS-63: Risk Transfer & Insurance Requirements",
    "UCRK25761_ControlledSubstances_Accessible.pdf": "BFB-BUS-50: Controlled Substances",
 
    # ---- Contracting for Services ----
    "GUHR230643_ContractingforServices_Accessible.pdf": "Contracting for Services Guide",
    "article5contractingout13120.pdf": "Article 5: Contracting Out",
    "Regents_Policy_5402__Policy_Generally_Prohibiting_Contracting_for_Services___Board_of_Regents.pdf": "Regents Policy 5402: Policy Generally Prohibiting Contracting for Services",
    "TC-Operating_Lease-Equip_Rental.docx": "Terms & Conditions: Operating Lease / Equipment Rental",
 
    # ---- Independent Contractors ----
    "GUFA200506_UCIndependentContractorGuidelines_Accessible.pdf": "UC Independent Contractor Guidelines",
 
    # ---- Property & Equipment ----
    "UCFA210555_BUS29_ManagementControlUniversityEquipment_Accessible.pdf": "BFB-BUS-29: Management & Control of University Equipment",
    "UCPS120029_AcquisitionDispositionUniversityVehicles.pdf": "UCPS-120029: Acquisition & Disposition of University Vehicles",
    "UCPS120068_DispositionExcessPropertyTransferProperty.pdf": "UCPS-120068: Disposition of Excess Property & Transfer of Property",
 
    # ---- Finance & Business ----
    "UCFA220617_BUS79_Bus_Meetings_Entertainment_updatedaccessible_12_15_2022.pdf": "BFB-BUS-79: Business Meetings & Entertainment",
    "UCFA23672_BFBG41_EmployeeNonCashAwardGifts_Accessible.pdf": "BFB-G-41: Employee Non-Cash Awards & Gifts",
    "UCFA180381_BFBG13_MovingRelocationPolicy_Accessible_4_12_2018.pdf": "BFB-G-13: Moving & Relocation Policy",
    "UCFO000180_a0007.pdf": "UCFO-000180: Financial Policy (a0007)",
    "UCFO000190_a25327.pdf": "UCFO-000190: Financial Policy (a25327)",
 
    # ---- Alcohol & Controlled Substances ----
    "UCPS120031_TaxFreeAlcoholPermitsRecordsOperations_3.pdf": "UCPS-120031: Tax-Free Alcohol Permits, Records & Operations",
 
    # ---- Information Security ----
    "UCIT190480_IS3_Accessible.pdf": "BFB-IS-3: Electronic Information Security",
 
    # ---- Conflict of Interest ----
    "Conflict_of_Interest_TrainingProcurement2024.pdf": "Conflict of Interest Training: Procurement 2024",
    "compendiumofconflictofinterestandrelatedpoliciesguidanceformerlybfbg39.pdf": "Compendium of Conflict of Interest & Related Policies (formerly BFB-G-39)",
    "mmpostemploymentcoirules102023.pdf": "Post-Employment Conflict of Interest Rules",
 
    # ---- GDPR / Privacy ----
    "appendixgdpreeauk42721.pdf": "Appendix GDPR: EEA & UK (Standard Contractual Clauses)",
    "appendixdatasecurity.pdf": "Appendix: Data Security Requirements",
    "appendixbaa.pdf": "Appendix: Business Associate Agreement (BAA)",
    "addendum-a-to-appendix-gdpr-scope-of-processing-data_0__1_.docx": "Addendum A to GDPR Appendix: Scope of Processing Data",
    "Addendum_B_to_Appendix_GDPR_-_SCC_0.docx": "Addendum B to GDPR Appendix: Standard Contractual Clauses",
    "Addendum_C__UK_GDPR__template_to_SCC_0.docx": "Addendum C to GDPR Appendix: UK GDPR Template",
 
    # ---- UC Terms & Conditions ----
    "UC_Terms_and_Conditions040125.pdf": "UC Terms and Conditions of Purchase (April 2025)",
}
 
# Maps filenames to top-level category for filtering
DOC_TYPE_MAP = {
    # Procurement
    "BUS43_ProcurementSupplyChainManagement_Main_Policy.pdf": "Procurement",
    "SOURCE_SELECTION___PRICE_REASONABLENESS_JUSTIFICATION_FORM__1_.docx": "Procurement",
    "Federal_Funds_Checklist-121525__2_.docx": "Procurement",
    "ssprfaq.pdf": "Procurement",
    "UC_Terms_and_Conditions040125.pdf": "Procurement",
 
    # Risk & Insurance
    "BUS63_Risk_Matrix_9192025.pdf": "Risk & Insurance",
    "UCRK25762_BFBBUS63_RiskTransferInsuranceRequirements_Accessible_1.pdf": "Risk & Insurance",
    "UCRK25761_ControlledSubstances_Accessible.pdf": "Risk & Insurance",
 
    # Contracting
    "GUHR230643_ContractingforServices_Accessible.pdf": "Contracting",
    "article5contractingout13120.pdf": "Contracting",
    "Regents_Policy_5402__Policy_Generally_Prohibiting_Contracting_for_Services___Board_of_Regents.pdf": "Contracting",
    "TC-Operating_Lease-Equip_Rental.docx": "Contracting",
    "GUFA200506_UCIndependentContractorGuidelines_Accessible.pdf": "Contracting",
 
    # Property & Equipment
    "UCFA210555_BUS29_ManagementControlUniversityEquipment_Accessible.pdf": "Property & Equipment",
    "UCPS120029_AcquisitionDispositionUniversityVehicles.pdf": "Property & Equipment",
    "UCPS120068_DispositionExcessPropertyTransferProperty.pdf": "Property & Equipment",
 
    # Finance
    "UCFA220617_BUS79_Bus_Meetings_Entertainment_updatedaccessible_12_15_2022.pdf": "Finance",
    "UCFA23672_BFBG41_EmployeeNonCashAwardGifts_Accessible.pdf": "Finance",
    "UCFA180381_BFBG13_MovingRelocationPolicy_Accessible_4_12_2018.pdf": "Finance",
    "UCFO000180_a0007.pdf": "Finance",
    "UCFO000190_a25327.pdf": "Finance",
    "UCPS120031_TaxFreeAlcoholPermitsRecordsOperations_3.pdf": "Finance",
 
    # Information Security
    "UCIT190480_IS3_Accessible.pdf": "Information Security",
 
    # Conflict of Interest
    "Conflict_of_Interest_TrainingProcurement2024.pdf": "Conflict of Interest",
    "compendiumofconflictofinterestandrelatedpoliciesguidanceformerlybfbg39.pdf": "Conflict of Interest",
    "mmpostemploymentcoirules102023.pdf": "Conflict of Interest",
 
    # GDPR / Privacy
    "appendixgdpreeauk42721.pdf": "GDPR & Privacy",
    "appendixdatasecurity.pdf": "GDPR & Privacy",
    "appendixbaa.pdf": "GDPR & Privacy",
    "addendum-a-to-appendix-gdpr-scope-of-processing-data_0__1_.docx": "GDPR & Privacy",
    "Addendum_B_to_Appendix_GDPR_-_SCC_0.docx": "GDPR & Privacy",
    "Addendum_C__UK_GDPR__template_to_SCC_0.docx": "GDPR & Privacy",
}
 
# File format lookup (useful for routing to correct extractor)
FILE_FORMAT_MAP = {
    "addendum-a-to-appendix-gdpr-scope-of-processing-data_0__1_.docx": "docx",
    "SOURCE_SELECTION___PRICE_REASONABLENESS_JUSTIFICATION_FORM__1_.docx": "docx",
    "Addendum_C__UK_GDPR__template_to_SCC_0.docx": "docx",
    "Federal_Funds_Checklist-121525__2_.docx": "docx",
    "Addendum_B_to_Appendix_GDPR_-_SCC_0.docx": "docx",
    "TC-Operating_Lease-Equip_Rental.docx": "docx",
}
# Everything not in FILE_FORMAT_MAP is assumed to be pdf
 
 
# official UCSC SSPR PDF (Rev. 12-2025); the .docx is the same form, this is the version the
# rule-engine page numbers refer to
POLICY_MAP["SSPR_Official_UCSC_2025-12.pdf"] = "Source Selection & Price Reasonableness Justification Form (SSPR, Rev. 12-2025)"
DOC_TYPE_MAP["SSPR_Official_UCSC_2025-12.pdf"] = "Procurement"

# official 2026 interim BUS-43 (same identity, new bytes)
POLICY_MAP["BUS-43_Interim_2026-01-26.pdf"] = "BFB-BUS-43: Procurement & Supply Chain Management (Interim, Jan 2026)"
DOC_TYPE_MAP["BUS-43_Interim_2026-01-26.pdf"] = "Procurement"

# official 48 CFR Part 12 (govinfo.gov), added for the federal-contract commercial items questions
POLICY_MAP["CFR-2025-title48-vol1-part12.pdf"] = "FAR Part 12: Acquisition of Commercial Products and Commercial Services (48 CFR, 10-1-25 Edition)"
DOC_TYPE_MAP["CFR-2025-title48-vol1-part12.pdf"] = "Procurement"


def _key(filename: str) -> str:
    # downloaded names differ only in punctuation/spacing ("BUS-43_..._Main Policy.pdf"
    # vs "BUS43_..._Main_Policy.pdf", "(2)" vs "__2_"), so match on letters and digits
    return "".join(ch for ch in filename.lower() if ch.isalnum())


_POLICY = {_key(k): v for k, v in POLICY_MAP.items()}
_DOC_TYPE = {_key(k): v for k, v in DOC_TYPE_MAP.items()}


def tag_chunk(chunk: dict) -> dict:
    source = chunk.get("source", "")
    chunk["policy_name"] = _POLICY.get(_key(source), source)
    chunk["doc_type"] = _DOC_TYPE.get(_key(source), "General Policy")
    chunk["file_format"] = "docx" if source.lower().endswith(".docx") else "pdf"
    return chunk


def get_all_doc_types() -> list[str]:
    return sorted(set(DOC_TYPE_MAP.values()))


def get_files_by_type(doc_type: str) -> list[str]:
    return [f for f, t in DOC_TYPE_MAP.items() if t == doc_type]
 
 
if __name__ == "__main__":
    # Quick sanity check and then print a summary of the corpus
    print(f"Total files mapped: {len(POLICY_MAP)}\n")
    for doc_type in get_all_doc_types():
        files = get_files_by_type(doc_type)
        print(f"[{doc_type}] — {len(files)} file(s)")
        for f in files:
            print(f"    {POLICY_MAP[f]}")
        print()