FROM python:3.10-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
# Explicitly define where Hugging Face models live to ensure build/runtime consistency
ENV HF_HOME=/root/.cache/huggingface

WORKDIR /apps

RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    cmake \
    libpq-dev \
    tesseract-ocr \
    libtesseract-dev \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --upgrade pip

RUN pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu --default-timeout=1000 --no-cache-dir

COPY requirements.txt .
RUN pip install --default-timeout=1000 --no-cache-dir -r requirements.txt

# --- BAKE STEP ---
# We initialize the converter with the EXACT same options as parser.py
# and run a dummy conversion to force-download layout, table, and cell-matching models.
RUN python3 -c "from docling.document_converter import DocumentConverter, PdfFormatOption; \
                from docling.datamodel.base_models import InputFormat, DocumentStream; \
                from docling.datamodel.pipeline_options import PdfPipelineOptions, TableStructureOptions; \
                from docling.backend.pypdfium2_backend import PyPdfiumDocumentBackend; \
                from io import BytesIO; \
                pipeline_options = PdfPipelineOptions(); \
                pipeline_options.do_ocr = False; \
                pipeline_options.do_table_structure = True; \
                pipeline_options.table_structure_options = TableStructureOptions(do_cell_matching=True); \
                converter = DocumentConverter( \
                    format_options={ \
                        InputFormat.PDF: PdfFormatOption( \
                            pipeline_options=pipeline_options, \
                            backend=PyPdfiumDocumentBackend \
                        ) \
                    } \
                ); \
                pdf_bytes = b'%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj 2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj 3 0 obj<</Type/Page/MediaBox[0 0 3 3]/Parent 2 0 R/Resources<<>>>>endobj xref 0 4 0000000000 65535 f 0000000009 00000 n 0000000052 00000 n 0000000101 00000 n trailer<</Size 4/Root 1 0 R>>startxref 178 %%EOF'; \
                converter.convert(DocumentStream(name='warmup.pdf', stream=BytesIO(pdf_bytes)))"

COPY . .

EXPOSE 8000

CMD ["gunicorn", "medgate.wsgi:application", \
     "--bind", "0.0.0.0:8000", \
     "--timeout", "600", \
     "--preload", \
     "--workers", "1"]