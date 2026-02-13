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
    Locked Parser for Kenya MoH 2020 Certification Manual.
    Captures: Star Ratings, Critical Standards, and Certification Decisions.
    """
    def process_file(self, file_path, protocol_obj):
        md_text = self.extract_markdown(file_path)
        lines = md_text.splitlines()

        # 1. Manual-Specific Anchors
        SECTION_ANCHORS = sorted([
            "Star Rating", "Certification Decision", "Critical Standards",
            "Scoring Methodology", "Verification of Evidence", "Corrective Action",
            "Grading Scale", "Award of Certificate", "Non-conformity"
        ], key=len, reverse=True)

        # 2. Precision Patterns for the 2020 Manual
        # Pattern for Star Levels (e.g., "80-89% : 4 Stars")
        star_pattern = re.compile(r"(?P<range>\d+[-]\d+%)|(?P<star>\d\s*Star)", re.I)
        # Pattern for Numeric Clauses (e.g., 4.1.2)
        clause_pattern = re.compile(r"(?:^|\||\s)(?P<id>\d{1,2}\.\d+(?:\.\d+)*)(?:\s|\||:)(?P<text>.*)")
        # Critical Standard Marker
        critical_pattern = re.compile(r"(Critical Standard|Safe Care|Non-negotiable)", re.I)

        candidates = []
        current_section = "Certification Logic"
        current_id = None
        current_buffer = []

        def flush_candidate():
            nonlocal current_id, current_buffer, current_section
            if not current_id or not current_buffer: return
            
            raw_text = " ".join(current_buffer).strip()
            clean_text = re.sub(r"\||☐|Criteria|Table|Figure", "", raw_text, flags=re.I).strip()
            
            if len(clean_text) < 12:
                current_id = None; current_buffer = []; return

            # Rule Code uses the CERT- prefix to designate "Grading Logic"
            full_rule_code = f"CERT-{current_id}"

            candidates.append({
                'rule_code': full_rule_code,
                'section_name': current_section,
                'clean_text': clean_text,
                'grounded_text': (
                    f"LEGAL_SOURCE: Quality of Care Certification Manual 2020\n"
                    f"DECISION_SECTION: {current_section}\n"
                    f"LOGIC_ID: {current_id}\n"
                    f"CERTIFICATION_RULE: {clean_text}\n"
                    f"CRITICALITY: {'HIGH' if critical_pattern.search(clean_text) else 'STANDARD'}"
                )
            })
            current_id = None; current_buffer = []

        print(f"[PARSER] Ingesting Certification Stamp: {protocol_obj.title}...", flush=True)

        for line in lines:
            stripped = line.strip()
            if not stripped: continue

            # Detect Section Header
            found_anchor = None
            for anchor in SECTION_ANCHORS:
                if anchor.upper() in stripped.upper():
                    found_anchor = anchor
                    break
            
            if found_anchor:
                flush_candidate()
                current_section = found_anchor
                continue

            # Identify Scorer Logic
            match = clause_pattern.search(stripped)
            star_match = star_pattern.search(stripped)

            if match or star_match:
                flush_candidate()
                if star_match:
                    # Capture "4-STAR" type rules
                    current_id = star_match.group(0).replace(" ", "-").upper()
                    content = stripped
                else:
                    # Capture numeric clauses
                    current_id = match.group("id")
                    content = match.group("text")
                
                if content: current_buffer.append(content)
            
            elif current_id:
                if not any(x in stripped.upper() for x in ["MINISTRY OF HEALTH", "PAGE", "AFYA"]):
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