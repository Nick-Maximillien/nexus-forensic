import re
import logging
import hashlib
from io import BytesIO
from pathlib import Path

# Import the high-performance backend to prevent hangs on complex PDFs
from docling.backend.pypdfium2_backend import PyPdfiumDocumentBackend

from docling.document_converter import DocumentConverter, PdfFormatOption
from docling.datamodel.base_models import InputFormat, DocumentStream
from docling.datamodel.pipeline_options import PdfPipelineOptions, TableStructureOptions

from apps.forensic_corpus.models import ForensicRule

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
            print(" [DOCLING] Cold Start: Initializing Engine...", flush=True)
            logger.info(" [COLD START] Initializing Docling Engine...")
            
            pipeline_options = PdfPipelineOptions()
            pipeline_options.do_ocr = False
            pipeline_options.do_table_structure = True
            pipeline_options.table_structure_options = TableStructureOptions(
                do_cell_matching=True 
            )

            converter = DocumentConverter(
                format_options={
                    InputFormat.PDF: PdfFormatOption(
                        pipeline_options=pipeline_options,
                        backend=PyPdfiumDocumentBackend
                    )
                }
            )

            try:
                print(" [DOCLING] Warming up models (this happens once)...", flush=True)
                pdf_bytes = b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj 2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj 3 0 obj<</Type/Page/MediaBox[0 0 3 3]/Parent 2 0 R/Resources<<>>>>endobj xref 0 4 0000000000 65535 f 0000000009 00000 n 0000000052 00000 n 0000000101 00000 n trailer<</Size 4/Root 1 0 R>>startxref 178 %%EOF"
                dummy_source = DocumentStream(name="warmup_dummy.pdf", stream=BytesIO(pdf_bytes))
                converter.convert(dummy_source)
                print(" [DOCLING] Engine Ready.", flush=True)
                logger.info(" [READY] Docling Pipeline Active.")
            except Exception as e:
                logger.warning(f" Warmup warning (non-fatal): {e}")

            _SHARED_CONVERTER = converter
        
        self.converter = _SHARED_CONVERTER

    def extract_markdown(self, file_path):
        """
        Converts the PDF to Markdown, preserving layout hierarchy.
        Modified: Uses /tmp/ for caching to ensure persistence in Docker.
        """
        file_hash = hashlib.md5(str(file_path).encode()).hexdigest()
        cache_path = Path(f"/tmp/medgate_cache_{file_hash}.md")
        
        if cache_path.exists():
            print(f"[CACHE HIT] Loading pre-converted markdown for {file_path}", flush=True)
            return cache_path.read_text(encoding='utf-8')

        print(f"\n[DOCLING] Analyzing layout (CPU Intensive) for {file_path}...", flush=True)
        logger.info(f"Docling: Analyzing layout for {file_path}...")
        try:
            result = self.converter.convert(file_path)
            md_output = result.document.export_to_markdown()
            
            # Persist to cache
            cache_path.write_text(md_output, encoding='utf-8')
            
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
    Unified Parser for Kenya MoH Corpus.
    Supports: 
    1. HIV Guidelines (Regimen extraction)
    2. Core Standards (Dimension & Scoring extraction)
    """
    def process_file(self, file_path, protocol_obj):
        md_text = self.extract_markdown(file_path)
        lines = md_text.splitlines()

        # Context detection: Is this a Certification/KQMH document?
        is_kqmh_doc = any(k in protocol_obj.title.upper() for k in ["KQMH", "QUALITY", "CORE STANDARD"])

        # KQMH Dimension Mapping
        DIM_MAP = {
            "1": "Leadership", "2": "Human Resources", "3": "Policies/Standards",
            "4": "Infrastructure", "5": "Supplies", "6": "Equipment",
            "7": "Transport", "8": "Referral", "9": "Records/HMIS",
            "10": "Finance", "11": "Clinical Processes", "12": "Clinical Results"
        }

        # 1. Section Anchors (Sorted Longest-First to prevent "Dimension 1" matching inside "Dimension 11")
        SECTION_ANCHORS = sorted([
            "Dimension 1", "Dimension 2", "Dimension 3", "Dimension 4", "Dimension 5",
            "Dimension 6", "Dimension 7", "Dimension 8", "Dimension 9", "Dimension 10",
            "Dimension 11", "Dimension 12", "ART Initiation", "First-line ART", 
            "Viral Load Monitoring", "PrEP", "Scoring System"
        ], key=len, reverse=True)

        # 2. Logic Patterns
        # Pattern for Standard IDs (e.g., 1.1, 11.4.2)
        logic_anchor_pattern = re.compile(r"(?:^|\||\s)(?P<id>\d{1,2}\.\d+(?:\.\d+)*)(?:\s|\||:)(?P<text>.*)")
        # Pattern for drug regimens (relevant for NASCOP but ignored for KQMH labeling)
        regimen_pattern = re.compile(r"(TDF|3TC|DTG|EFV|AZT|LPV/r|NVP|ABC|RAL)", re.IGNORECASE)
        # Pattern for Scoring Requirement (Core Standards)
        score_pattern = re.compile(r"Score\s*(?P<val>[1-5])\s*[:|-]\s*(?P<desc>.*)", re.I)

        candidates = []
        current_section = "General Context"
        current_id = None
        current_buffer = []

        def flush_candidate():
            nonlocal current_id, current_buffer, current_section
            if not current_id or not current_buffer: return

            raw_text = " ".join(current_buffer).strip()
            # Clean artifacts
            clean_text = re.sub(r"\||☐|Yes/No|Criteria|Table|Figure", "", raw_text, flags=re.I).strip()
            
            if len(clean_text) < 10:
                current_id = None; current_buffer = []; return

            # Resolve Code and Section
            # Prefix is the first part of the ID (e.g. '11' from '11.1')
            prefix = str(current_id).split('.')[0]
            section_display = DIM_MAP.get(prefix, current_section)
            
            # Context-Aware Prefixing: If the doc is KQMH, use KQMH prefix even for regex hits
            id_prefix = "KQMH" if (is_kqmh_doc or prefix in DIM_MAP) else "HIV"
            full_rule_code = f"{id_prefix}-{current_id}"

            candidates.append({
                'rule_code': full_rule_code,
                'section_name': section_display,
                'clean_text': clean_text,
                'grounded_text': (
                    f"DOCUMENT: {protocol_obj.title}\n"
                    f"DOMAIN: {section_display}\n"
                    f"IDENTIFIER: {current_id}\n"
                    f"REQUIREMENT/CRITERIA: {clean_text}\n"
                    f"CONTEXT: Forensic Audit/Certification Standard"
                )
            })
            
            current_id = None
            current_buffer = []

        print(f"[PARSER] Extracting Logic from {protocol_obj.title}...", flush=True)

        for line in lines:
            stripped = line.strip()
            if not stripped: continue

            # 3. Detect Section Changes (Using Longest-Match First)
            found_anchor = None
            for anchor in SECTION_ANCHORS:
                if anchor.upper() in stripped.upper():
                    found_anchor = anchor
                    break 
            
            if found_anchor:
                flush_candidate()
                current_section = found_anchor
                continue

            # 4. Identify Anchors (IDs, Scores, or Regimens)
            match = logic_anchor_pattern.search(stripped)
            score_match = score_pattern.search(stripped)
            is_regimen = regimen_pattern.search(stripped)

            if match or score_match or is_regimen:
                flush_candidate()
                if match:
                    current_id = match.group("id")
                    text_content = match.group("text")
                elif score_match:
                    current_id = f"Score-{score_match.group('val')}"
                    text_content = score_match.group("desc")
                else:
                    # Generate hash for regimens/un-numbered blocks
                    current_id = hashlib.md5(stripped.encode()).hexdigest()[:6].upper()
                    text_content = stripped

                if current_id and text_content: 
                    current_buffer.append(text_content)
            
            elif current_id:
                # Add continuation text if it's not noise
                is_noise = any(x in stripped.upper() for x in ["MINISTRY OF HEALTH", "PAGE", "AFYA HOUSE", "KQMH"])
                if not is_noise:
                    current_buffer.append(stripped)

        flush_candidate()
        return candidates

class GuidelineParser(BaseParser):
    """
    Target: ESC Guidelines (ACS, STEMI, NSTEMI, etc.)
    Logic kept 100% intact.
    """
    def process_file(self, file_path, protocol_obj):
        md_text = self.extract_markdown(file_path)
        lines = md_text.splitlines()
        candidates = []
        table_row_pattern = re.compile(
            r"\|\s*(?P<text>.+?)\s*\|\s*(?P<class>I|IIa|IIb|III)\s*\|\s*(?P<level>A|B|C)\s*\|",
            re.IGNORECASE,
        )

        for line in lines:
            stripped = line.strip()
            if stripped.startswith("|"):
                match = table_row_pattern.search(stripped)
                if not match: continue
                content = match.group("text").strip()
                cls = match.group("class").upper()
                lvl = match.group("level").upper()
                if "recommendation" in content.lower() and len(content) < 30: continue
                content = re.sub(r"[\"\\]", "", content)
                content = re.sub(r"\s+", " ", content).strip()
                if len(content) < 15: continue
                
                short_hash = hashlib.md5(content.encode()).hexdigest()[:8]
                candidates.append({
                    'rule_code': f"ESC-{cls}-{short_hash}",
                    'section_name': f"Class {cls}",
                    'clean_text': content,
                    'grounded_text': f"STRENGTH: Class {cls} (Level {lvl}). RECOMMENDATION: {content}"
                })
        return candidates