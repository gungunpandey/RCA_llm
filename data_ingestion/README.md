# Data Ingestion Pipeline

Comprehensive PDF processing pipeline that extracts text, tables, and images from technical manuals and ingests them into Weaviate vector database for RAG (Retrieval Augmented Generation) applications.

---

## 📋 Table of Contents

- [Quick Start](#quick-start)
- [Pipeline Overview](#pipeline-overview)
- [Text Extraction Logic](#text-extraction-logic)
- [Table Extraction](#table-extraction)
- [Image Extraction](#image-extraction)
- [OCR Support](#ocr-support)
- [Cleanup Pipeline](#cleanup-pipeline)
- [Ingestion to Weaviate](#ingestion-to-weaviate)
- [Configuration](#configuration)

---

## Quick Start

### Installation

```bash
# Core dependencies
pip install pymupdf pdfplumber weaviate-client

# For OCR support (optional, for scanned documents)
pip install pdf2image pytesseract
# Also install Tesseract: https://github.com/tesseract-ocr/tesseract
# Windows: Download Poppler from https://github.com/osber/poppler/releases
```

### Basic Usage

```bash
# Run complete pipeline (extract → cleanup → ingest)
python pdf_processor.py

# Run individual stages
python pdf_processor.py --extract    # Extract text and images
python pdf_processor.py --cleanup    # Clean extracted text
python pdf_processor.py --ingest     # Upload to Weaviate

# Options
python pdf_processor.py --force              # Reprocess all files
python pdf_processor.py --target "filename"  # Process specific file
```

### Directory Structure

```
data_ingestion/
├── pdf_processor.py      # Main processing script
├── weaviate_config.json  # Weaviate connection config
├── .env                  # API credentials (not committed)
├── pdfs/                 # Input PDF folder 1
├── pdfs_pellet/          # Input PDF folder 2
└── data/
    ├── extracted/        # Raw extracted text + images
    ├── cleaned/          # Cleaned text files
    ├── logs/             # Processing logs by stage
    └── status_*.json     # Processing status tracking
```

---

## Pipeline Overview

The pipeline has **3 main stages**:

### 1. **Extraction** (`--extract`)
- Extracts text from PDFs using pdfplumber (preserves tables)
- Falls back to OCR for scanned documents
- Extracts images (embedded rasters + vector diagrams)
- Handles rotated pages, complex diagrams, and font encoding issues

### 2. **Cleanup** (`--cleanup`)
- Removes recurring headers/footers
- Rejoins fragmented text (broken paragraphs)
- Preserves table formatting

### 3. **Ingestion** (`--ingest`)
- Chunks text into manageable pieces
- Uploads to Weaviate with metadata
- Includes images with captions

---

## Text Extraction Logic

### Standard Extraction (pdfplumber)

**Why pdfplumber?** It preserves table structure better than PyMuPDF.

**Process:**
1. Extract text from each page
2. Detect and extract tables with timeout protection (30s per page)
3. Format tables as markdown-style text
4. Combine table text + regular text

**Example Table Output:**
```
[TABLE 1]
| Parameter | Value | Unit |
| --------- | ----- | ---- |
| Power     | 100   | kW   |
| Speed     | 1500  | RPM  |
```

### Rotated Page Handling

Some PDFs have metadata rotation (e.g., landscape pages). The system:
1. Detects rotated pages using PyMuPDF
2. If pdfplumber extracts < 50 chars, switches to PyMuPDF (handles rotation better)
3. Logs the switch: `"Page 25: rotation=180° — switched to PyMuPDF"`

### Timeout Protection

**Problem:** Some pages with complex tables can hang extraction indefinitely.

**Solution:** 30-second timeout per page for table extraction. If timeout occurs:
- Skips table extraction for that page
- Falls back to text-only extraction
- Logs warning: `"Table extraction timed out on page X"`

---

## Table Extraction

### How It Works

1. **Detection:** pdfplumber analyzes page layout to find table boundaries
2. **Extraction:** Extracts cell contents row-by-row
3. **Formatting:** Converts to aligned markdown-style table
4. **Preservation:** Tables are clearly marked with `[TABLE N]` headers

### Table Quality

- ✅ **Good for:** Clean, well-structured tables
- ⚠️ **May struggle with:** Merged cells, nested tables, hand-drawn tables
- 🔧 **Timeout protection:** Prevents hanging on problematic tables

---

## Image Extraction

The system uses a **3-phase approach** to capture all diagrams:

### Phase 1: Embedded Raster Images

Extracts photos, scanned diagrams, and embedded PNG/JPEG images.

**Filters:**
- Minimum size: 200×200 pixels
- Minimum file size: 50 KB
- Skips recurring logos (appears on 3+ pages)

**Output:** `diagram_p7_0.jpeg`, `diagram_p11_2_TLT_Job_No.png`

### Phase 2: Vector Diagrams

Renders full pages that are primarily vector drawings (CAD diagrams, schematics).

**Detection criteria (all must be true):**
- Page has 100+ vector drawing primitives (lines, curves, shapes)
- Drawing coverage > 30% of page area
- Page text < 300 characters (filters out spec tables with borders)

**Adaptive DPI:**
- Normal diagrams: 300 DPI
- Complex diagrams (>40 drawings): 150 DPI (prevents memory issues)
- Very complex diagrams (>10,000 drawings): 150 DPI with timeout protection

**Output:** `page_45_highres.png`

### Phase 3: Figure Pages

Renders pages containing figure keywords ("Figure", "图", "Diagram").

**Why?** Captures labeled diagrams that might have been missed in Phase 1/2.

**Output:** `figure_p9_figures_in_brackets_refer_to_items_of_th.png`

### Image Labeling

The system tries to find descriptive labels for images:

1. **Nearby text:** Looks for text within 60 points above/below the image
2. **Caption patterns:** Matches "Figure X", "图 X", "Diagram X" patterns
3. **Fallback:** Uses short nearby text blocks or generic names

**Example:** `diagram_p13_3_TLT_Job_No.png` (found "TLT Job No" label near image)

### Rendering Safety

**Problem:** Very complex diagrams (27,000+ drawing primitives) can cause:
- Memory errors
- Rendering timeouts
- System hangs

**Solution:**
- 30-second timeout per page render
- Adaptive DPI based on complexity
- Graceful error handling with logging

---

## OCR Support

### When OCR is Used

The system supports **3 OCR modes**:

#### 1. Automatic OCR Detection

**Trigger:** First 3 pages have < 50 characters of text each

**Action:** Switches to full OCR for entire PDF

**Use case:** Fully scanned documents (photos of paper manuals)

**Processing:**
- Converts PDF pages to images (300 DPI)
- Processes in batches of 10 pages (prevents memory issues)
- Uses Tesseract OCR with language detection
- Logs progress: `"OCR processing page 10/46"`

#### 2. Per-Page OCR Configuration

**Trigger:** Manual configuration in `pdf_processor.py`

**Use case:** PDFs with specific problematic pages (e.g., ultra-high-resolution diagrams that cause hangs)

**Configuration:**
```python
force_ocr_config = {
    "ID&HR Fan_TLT_OEM Manual.pdf": [45],  # OCR only page 45
    "Another Manual.pdf": [10, 15, 20],    # OCR pages 10, 15, 20
    "Fully Scanned.pdf": "all",            # OCR entire PDF
}
```

**Benefits:**
- ⚡ **Much faster:** Only processes problematic pages (~2 min vs 3+ min)
- 📊 **Preserves tables:** Standard extraction keeps table structure on other pages
- 🛡️ **Prevents hangs:** Avoids processing 27,000+ drawing primitive pages

**Example log:**
```
Using OCR for specific pages: [45] (rest will use standard extraction)
Page 45: Using OCR extraction (problematic page)
Text -> ... (method: standard+ocr(pages:[45]))
```

#### 3. Language Detection

**How it works:**
1. Checks PDF metadata for language hints
2. Analyzes first 10 pages for CJK (Chinese/Japanese/Korean) characters
3. If mixed content detected, uses `chi_sim+eng` (Chinese + English)
4. Falls back to `eng` for English-only documents

**Supported languages:**
- `eng` - English
- `chi_sim` - Simplified Chinese
- `chi_sim+eng` - Mixed Chinese and English

### OCR Dependencies

**Required:**
- `pdf2image` - Converts PDF pages to images
- `pytesseract` - Python wrapper for Tesseract
- Tesseract OCR - The actual OCR engine
- Poppler (Windows) - PDF rendering library

**Installation:**
```bash
pip install pdf2image pytesseract

# Windows:
# 1. Download Tesseract: https://github.com/UB-Mannheim/tesseract/wiki
# 2. Download Poppler: https://github.com/osber/poppler/releases
# 3. Add both to system PATH
```

---

## Cleanup Pipeline

The cleanup stage processes extracted text to remove noise and improve readability.

### 1. Header/Footer Removal

**Problem:** Recurring headers/footers appear on every page (e.g., "Page 1/50", "Confidential", company logos)

**Detection:**
- Normalizes lines (lowercase, collapse page numbers)
- Counts occurrences across all pages
- If a line appears on > 50% of pages → it's a header/footer

**Action:** Removes all instances of detected headers/footers

**Example log:** `"Removing 8 recurring header pattern(s)"`

### 2. Fragment Rejoining

**Problem:** PDFs sometimes break paragraphs into single-word lines:
```
This
is
a
broken
paragraph.
```

**Detection:** 4+ consecutive lines with single words

**Action:** Rejoins into proper paragraph:
```
This is a broken paragraph.
```

### 3. Table Preservation

**Important:** Cleanup preserves `[TABLE N]` markers and table formatting from extraction stage.

---

## Ingestion to Weaviate

### Chunking Strategy

**Text chunks:**
- Max 1000 characters per chunk
- Splits on paragraph boundaries (preserves context)
- Each chunk gets unique metadata

**Image chunks:**
- Each image is a separate chunk
- Includes caption/label as content
- Links to image file path

### Metadata Schema

Every chunk in Weaviate includes:

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `content` | text | Text content (vectorized) | "The motor operates at..." |
| `chunkType` | keyword | Type of chunk | "text" or "image" |
| `sourcePdf` | keyword | Source PDF filename | "ID&HR Fan_TLT_OEM Manual.pdf" |
| `sourceFolder` | keyword | Source folder | "pdfs_pellet" |
| `pageNumber` | int | Page number (1-indexed) | 45 |
| `chunkIndex` | int | Chunk index within page | 0, 1, 2... |
| `collectionName` | keyword | Collection from config | "RCA_Manuals" |
| `imageType` | keyword | Image type (if applicable) | "diagram", "figure" |
| `imagePath` | keyword | Relative path to image | "pdfs_pellet/..." |

### Incremental Processing

**Status tracking:** Each stage maintains a JSON status file:
- `status_extracted.json` - Tracks extracted PDFs
- `status_cleaned.json` - Tracks cleaned files
- `status_ingested.json` - Tracks ingested files

**Behavior:**
- ✅ Skips already-processed files (unless `--force` flag used)
- 📝 Logs: `"Already extracted – skip: pdfs_pellet/Manual.pdf"`
- 🔄 Resumes from last successful file on errors

---

## Configuration

### Weaviate Connection (`weaviate_config.json`)

```json
{
  "url": "http://localhost:8080",
  "collectionName": "RCA_Manuals",
  "headers": {
    "X-OpenAI-Api-Key": "your-api-key"
  }
}
```

**Note:** API keys can also be set in `.env` file:
```
OPENAI_API_KEY=your-api-key
```

### Extraction Settings (`pdf_processor.py`)

**Table extraction:**
```python
TABLE_EXTRACTION_TIMEOUT = 30  # seconds per page
```

**Image filtering:**
```python
MIN_IMG_WIDTH = 200      # pixels
MIN_IMG_HEIGHT = 200     # pixels
MIN_IMG_BYTES = 50000    # 50 KB
LOGO_PAGE_THRESHOLD = 3  # recurring on 3+ pages = logo
```

**Vector diagram detection:**
```python
MIN_DRAWINGS = 100              # minimum drawing primitives
MIN_DRAWING_COVERAGE = 30.0     # % of page area
MAX_TEXT_FOR_DIAGRAM = 300      # max chars (filters tables)
```

**Rendering:**
```python
PAGE_RENDER_TIMEOUT = 30        # seconds
COMPLEX_DIAGRAM_THRESHOLD = 40  # drawings count
HIGH_RES_DPI = 300              # normal diagrams
LOW_RES_DPI = 150               # complex diagrams
```

**OCR:**
```python
CONSECUTIVE_EMPTY_PAGES_THRESHOLD = 3  # trigger OCR
MIN_TEXT_LENGTH_FOR_VALID_PAGE = 50    # chars
OCR_DPI = 300                          # image resolution
```

**Cleanup:**
```python
HEADER_MIN_OCCURRENCE = 0.5    # 50% of pages
MIN_FRAGMENT_RUN = 4           # consecutive single-word lines
```

### PDF Source Folders

Add/remove source folders in `pdf_processor.py`:

```python
PDF_SOURCES = [
    os.path.join(_HERE, "pdfs"),
    os.path.join(_HERE, "pdfs_pellet"),
    # Add more folders here
]
```

---

## Troubleshooting

### Common Issues

**1. OCR not working**
```
Error: OCR dependencies not available
```
**Solution:** Install OCR dependencies and Poppler (see [OCR Dependencies](#ocr-dependencies))

**2. Table extraction hanging**
```
(No log output for 30+ seconds on a page)
```
**Solution:** Timeout protection will kick in after 30s. If persistent, add page to OCR config.

**3. Very large diagrams causing memory errors**
```
Page 45: Out of memory during rendering
```
**Solution:** Add page to per-page OCR config to skip rendering.

**4. Missing images**
```
Only 2 images extracted, but PDF has 10 diagrams
```
**Solution:** Check if images are:
- Too small (< 200×200 px)
- Recurring logos (appear on 3+ pages)
- Vector diagrams without "Figure" keyword (check Phase 2 logs)

---

## Performance Tips

1. **Use `--target` for testing:** Process single files during development
2. **Monitor logs:** Check `data/logs/` for detailed processing info
3. **Adjust timeouts:** Increase if legitimate tables are timing out
4. **Use per-page OCR:** Much faster than full OCR for mostly-readable PDFs
5. **Batch processing:** Pipeline handles multiple PDFs automatically

---

## Support

For issues or questions, check:
- Processing logs in `data/logs/`
- Status files in `data/status_*.json`
- This README for configuration options
