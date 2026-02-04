import re
import logging
import hashlib
from io import BytesIO

# Import the high-performance backend to prevent hangs on complex PDFs
from docling.backend.pypdfium2_backend import PyPdfiumDocumentBackend

from docling.document_converter import DocumentConverter, PdfFormatOption
from docling.datamodel.base_models import InputFormat, DocumentStream
from docling.datamodel.pipeline_options import PdfPipelineOptions, TableStructureOptions

from apps.forensic_corpus.models import ForensicRule
from apps.forensic_corpus.ingestion.llm_normalizer import extract_metadata_only

logger = logging.getLogger(__name__)

# --- SINGLETON CACHE ---
_SHARED_CONVERTER = None

class BaseParser:
    """
    Base parser: Uses Docling to convert PDF -> Structured Markdown.
    Includes 'Warmup Routine' to prevent Gunicorn Timeouts on first request.
    """
    def __init__(self):
        global _SHARED_CONVERTER

        if _SHARED_CONVERTER is None:
            # [VISIBILITY] Force print to console
            print(" [DOCLING] Cold Start: Initializing Engine...", flush=True)
            logger.info(" [COLD START] Initializing Docling Engine...")
            
            # 1. Configure Options
            pipeline_options = PdfPipelineOptions()
            pipeline_options.do_ocr = False
            pipeline_options.do_table_structure = True
            pipeline_options.table_structure_options = TableStructureOptions(
                do_cell_matching=True 
            )

            # 2. Create Converter
            # [FIX] Added backend=PyPdfiumDocumentBackend to solve the 100% CPU hang
            converter = DocumentConverter(
                format_options={
                    InputFormat.PDF: PdfFormatOption(
                        pipeline_options=pipeline_options,
                        backend=PyPdfiumDocumentBackend
                    )
                }
            )

            # 3. WARMUP ROUTINE (FIXED)
            # We wrap the BytesIO in a DocumentStream so Pydantic is happy.
            try:
                print(" [DOCLING] Warming up models (this happens once)...", flush=True)
                logger.info("🔥 [WARMUP] Pre-loading RapidOCR models (this takes time)...")
                
                # Minimal valid PDF binary string
                pdf_bytes = b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj 2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj 3 0 obj<</Type/Page/MediaBox[0 0 3 3]/Parent 2 0 R/Resources<<>>>>endobj xref 0 4 0000000000 65535 f 0000000009 00000 n 0000000052 00000 n 0000000101 00000 n trailer<</Size 4/Root 1 0 R>>startxref 178 %%EOF"
                
                # FIX: Wrap in DocumentStream
                dummy_source = DocumentStream(name="warmup_dummy.pdf", stream=BytesIO(pdf_bytes))
                
                # This triggers the heavy imports (rapidocr, onnxruntime) without validation errors
                converter.convert(dummy_source)
                print(" [DOCLING] Engine Ready.", flush=True)
                logger.info("✅ [READY] Docling Pipeline Active.")
            except Exception as e:
                logger.warning(f"⚠️ Warmup warning (non-fatal): {e}")

            _SHARED_CONVERTER = converter
        
        self.converter = _SHARED_CONVERTER

    def extract_markdown(self, file_path):
        """
        Converts the PDF to Markdown, preserving layout hierarchy.
        """
        # [VISIBILITY] Detailed status updates
        print(f"\n[DOCLING] Analyzing layout for {file_path}...", flush=True)
        print("[DOCLING] This process uses AI Vision models. Please wait...", flush=True)
        logger.info(f"Docling: Analyzing layout for {file_path}...")
        try:
            result = self.converter.convert(file_path)
            md_output = result.document.export_to_markdown()
            print(f"[DOCLING] Conversion complete! Generated {len(md_output)} chars of Markdown.", flush=True)
            return md_output
        except Exception as e:
            print(f"[DOCLING] CRITICAL ERROR: {e}", flush=True)
            logger.error(f"Docling conversion failed: {e}")
            raise e

    def process_file(self, file_path, protocol_obj):
        raise NotImplementedError


class ClinicalProtocolParser(BaseParser):
    """
    Target: NIST OSAC, CMS CoPs (Hierarchical Documents)
    Input: Markdown text with clear headers (# 1.1) or Tags (# Tag A-0123)
    """
    def process_file(self, file_path, protocol_obj):
        md_text = self.extract_markdown(file_path)
        
        # IMPROVED REGEX: Tag-Aware + Hierarchical
        split_pattern = r"(?m)^#+\s+(?:Section\s+|Tag\s+)?(?:(A-\d{4})|(\d+(?:\.\d+)*))\.?\s+"
        
        tokens = re.split(split_pattern, md_text)
        
        rules = []
        clean_tokens = [t for t in tokens if t is not None]

        print(f"[PARSER] Scanning {len(clean_tokens)} tokens...", flush=True)

        for i in range(1, len(clean_tokens), 2):
            if i+1 >= len(clean_tokens): break
            
            identifier = clean_tokens[i] 
            content_body = clean_tokens[i+1]
            
            if len(content_body.strip()) < 20: 
                continue
            
            if identifier.startswith("A-"):
                full_rule_code = f"Tag {identifier}"
            else:
                full_rule_code = f"Rule {identifier}"

            print(f"  -> Extracted {full_rule_code}", flush=True)

            metadata = extract_metadata_only(full_rule_code, content_body)
            
            # [UPGRADE] Added scope_tags and intent_tags mapping from LLM metadata
            rules.append(ForensicRule(
                protocol=protocol_obj,
                rule_code=full_rule_code,
                rule_type=metadata.get('rule_type', 'existence'),
                text_description=content_body.strip(),
                logic_config=metadata.get('logic_config', {}),
                scope_tags=metadata.get('scope_tags', ['clinical']), # Default to clinical
                intent_tags=metadata.get('intent_tags', ['quality']) # Default to quality
            ))
            
        return rules


class GuidelineParser(BaseParser):
    """
    Target: ESC Guidelines (ACS, STEMI, NSTEMI, etc.)
    Extracts clinical rules from layout-aware tables:
    | Recommendation | Class | Level |
    Fully compatible with ForensicRule model + LLM normalizer.
    """

    def process_file(self, file_path, protocol_obj):
        md_text = self.extract_markdown(file_path)
        lines = md_text.splitlines()
        rules = []

        print(f"[PARSER] Scanning {len(lines)} lines for Table Rows...", flush=True)

        table_row_pattern = re.compile(
            r"\|\s*(?P<text>.+?)\s*\|\s*"
            r"(?P<class>I|IIa|IIb|III)\s*\|\s*"
            r"(?P<level>A|B|C)\s*\|",
            re.IGNORECASE,
        )

        for line in lines:
            stripped = line.strip()

            if stripped.startswith("|"):
                # [FIX] REMOVED BUFFER LOGIC
                # Docling guarantees one table row per line.
                # Direct check prevents O(N^2) hangs.
                match = table_row_pattern.search(stripped)

                if not match:
                    continue

                content = match.group("text").strip()
                cls = match.group("class").upper()
                lvl = match.group("level").upper()

                # Skip header rows
                if "recommendation" in content.lower() and len(content) < 30:
                    continue

                # Sanitize Docling artifacts
                content = re.sub(r"\\", "", content)
                content = re.sub(r'"', "", content)
                content = re.sub(r"\s+", " ", content).strip()

                if len(content) < 15:
                    continue

                # -----------------------------
                # ESC → MODEL-SAFE rule_type
                # -----------------------------
                if cls == "I":
                    rule_type = "existence"
                elif cls in ("IIA", "IIB"):
                    rule_type = "threshold"
                else:  # Class III
                    rule_type = "contra"

                # -----------------------------
                # Deterministic intent inference
                # -----------------------------
                text_l = content.lower()

                if any(k in text_l for k in [
                    "contraindicated", "not recommended", "avoid", "harm"
                ]):
                    intent_tags = ["safety"]
                elif any(k in text_l for k in [
                    "bleeding", "hemorrhage"
                ]):
                    intent_tags = ["safety"]
                elif any(k in text_l for k in [
                    "pci", "angiography", "revascular"
                ]):
                    intent_tags = ["quality"]
                elif any(k in text_l for k in [
                    "aspirin", "clopidogrel", "ticagrelor",
                    "prasugrel", "heparin", "anticoagulant",
                    "antiplatelet"
                ]):
                    intent_tags = ["quality"]
                else:
                    intent_tags = ["quality"]

                # -----------------------------
                # Stable rule identity
                # -----------------------------
                short_hash = hashlib.md5(content.encode()).hexdigest()[:8]
                full_rule_code = f"ESC-{cls}-{short_hash}"

                print(f"  -> Extracted {full_rule_code}", flush=True)

                # -----------------------------
                # LLM enrichment (bounded)
                # -----------------------------
                enriched_text = (
                    f"STRENGTH: Class {cls} (Level {lvl}). "
                    f"RECOMMENDATION: {content}"
                )

                metadata = extract_metadata_only(full_rule_code, enriched_text)

                # -----------------------------
                # Normalize intent tags to model enum
                # -----------------------------
                intent_map = {
                    "integrity": "billing",
                    "documentation": "documentation",
                }

                final_intents = [
                    intent_map.get(t, t)
                    for t in metadata.get("intent_tags", intent_tags)
                    if t in dict(ForensicRule.RULE_INTENTS)
                    or t in intent_map
                ] or intent_tags

                rules.append(
                    ForensicRule(
                        protocol=protocol_obj,
                        rule_code=full_rule_code,
                        rule_type=metadata.get("rule_type", rule_type),
                        text_description=content,
                        logic_config=metadata.get("logic_config", {}),
                        scope_tags=metadata.get("scope_tags", ["clinical"]),
                        intent_tags=final_intents,
                    )
                )

        logger.info(f"ESC GuidelineParser extracted {len(rules)} rules.")
        print(f"[PARSER] Completed. Extracted {len(rules)} rules.", flush=True)
        return rules