import json
import logging
import os
import re
import sys
from collections import Counter
from datetime import datetime

import fitz  # PyMuPDF
import pdfplumber
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError

try:
    import weaviate
except ImportError:  # pragma: no cover
    weaviate = None

# Optional OCR dependencies for scanned documents
try:
    from pdf2image import convert_from_path
    import pytesseract
    OCR_AVAILABLE = True
except ImportError:
    OCR_AVAILABLE = False


# ─────────────────────────────────────────────────────────────────────────────
# PATHS  (all relative to this script's directory)
# ─────────────────────────────────────────────────────────────────────────────
_HERE = os.path.dirname(os.path.abspath(__file__))

_PDFS_ROOT = os.path.join(_HERE, "pdfs")

# Dynamically discover all subfolders inside pdfs/.
# Each subfolder (e.g. pdfs/ESP/, pdfs/Kiln/) is added as a separate source
# so PDFs from different machine companies are all picked up automatically.
# If there are no subfolders, fall back to the root pdfs/ folder itself.
_pdf_subdirs = [
    os.path.join(_PDFS_ROOT, d)
    for d in os.listdir(_PDFS_ROOT)
    if os.path.isdir(os.path.join(_PDFS_ROOT, d))
] if os.path.isdir(_PDFS_ROOT) else []

PDF_SOURCES = _pdf_subdirs if _pdf_subdirs else [_PDFS_ROOT]

DATA_DIR       = os.path.join(_HERE, "data")
EXTRACTED_DIR  = os.path.join(DATA_DIR, "extracted")
CLEANED_DIR    = os.path.join(DATA_DIR, "cleaned")
LOGS_DIR       = os.path.join(DATA_DIR, "logs")
STATUS_EXTRACT = os.path.join(DATA_DIR, "status_extracted.json")
STATUS_CLEAN   = os.path.join(DATA_DIR, "status_cleaned.json")
STATUS_INGEST  = os.path.join(DATA_DIR, "status_ingested.json")
CONFIG_PATH    = os.path.join(_HERE, "weaviate_config.json")


# ─────────────────────────────────────────────────────────────────────────────
# EXTRACTION SETTINGS
# ─────────────────────────────────────────────────────────────────────────────
TABLE_EXTRACTION_TIMEOUT = 30  # seconds per page for table extraction

MIN_IMG_WIDTH        = 200     # px – anything smaller is a logo / icon
MIN_IMG_HEIGHT       = 200     # px
MIN_IMG_BYTES        = 50000   # 50 KB – filters small logos, fragments, and low-res images
LOGO_PAGE_THRESHOLD  = 3       # xref on this many pages → recurring logo

MIN_DRAWINGS         = 100     # vector primitives to qualify as a diagram page
MIN_DRAWING_COVERAGE = 30.0    # % of page area the drawing bbox must cover
MAX_TEXT_FOR_DIAGRAM = 300     # chars – more = spec table, not a diagram

# Page rendering settings (for complex vector diagrams)
PAGE_RENDER_TIMEOUT     = 30    # seconds – timeout for rendering a single page
COMPLEX_DIAGRAM_THRESHOLD = 40  # drawing count – diagrams with more drawings use lower DPI
HIGH_RES_DPI            = 300   # DPI for normal diagrams
LOW_RES_DPI             = 150   # DPI for complex diagrams to avoid memory issues

# OCR fallback settings (for scanned documents)
CONSECUTIVE_EMPTY_PAGES_THRESHOLD = 3    # switch to OCR after this many consecutive empty pages
MIN_TEXT_LENGTH_FOR_VALID_PAGE    = 50   # chars – page with less text is considered "empty"
OCR_DPI                           = 300  # resolution for converting PDF pages to images


# ─────────────────────────────────────────────────────────────────────────────
# CLEANUP SETTINGS
# ─────────────────────────────────────────────────────────────────────────────
HEADER_MIN_OCCURRENCE = 0.5    # fraction of pages a line must appear on → boilerplate
MIN_FRAGMENT_RUN      = 4      # consecutive single-word lines needed to trigger rejoin


# ═════════════════════════════════════════════════════════════════════════════
# SHARED HELPERS
# ═════════════════════════════════════════════════════════════════════════════
_PAGE_NUM_RE = re.compile(r"Page:\s*\d+\s*/\s*\d+")

# Caption / label patterns – used by image-label extraction.
# CN patterns are listed longest-first so the alternation matches greedily.
_CAPTION_RE_CN = re.compile(
    r'(?:附图|示意图|原理图|结构图|图)\s*[一二三四五六七八九十〇\d]*\s*[、.:：—–\-]*\s*[^\n]{0,50}'
)
_CAPTION_RE_EN = re.compile(
    r'(?i)\b(?:figure|fig\.?|diagram|drawing|illustration)\s*[\d.]*[a-z]?\s*[.:—–\-]*\s*[^\n]{0,60}'
)

# CJK Unified Ideographs detector – used by OCR language selection
_CJK_CHAR_RE = re.compile(r'[\u4e00-\u9fff]')

# Pattern for detecting garbled text (random uppercase sequences)
_GARBLED_UPPERCASE_RE = re.compile(r'[A-Z]{3,}')

# Common English words to check for readable text
_COMMON_ENGLISH_WORDS = {
    'the', 'be', 'to', 'of', 'and', 'a', 'in', 'that', 'have', 'i',
    'it', 'for', 'not', 'on', 'with', 'he', 'as', 'you', 'do', 'at',
    'this', 'but', 'his', 'by', 'from', 'they', 'we', 'say', 'her', 'she',
    'or', 'an', 'will', 'my', 'one', 'all', 'would', 'there', 'their', 'what',
    'so', 'up', 'out', 'if', 'about', 'who', 'get', 'which', 'go', 'me',
    'is', 'are', 'was', 'were', 'been', 'being', 'has', 'had', 'does', 'did',
    'can', 'could', 'may', 'might', 'must', 'shall', 'should', 'will', 'would',
}


def _is_garbled_text(text: str) -> bool:
    """Detect if text appears to be garbled (font encoding issues).

    Signs of garbled text:
    1. Contains CJK characters mixed with random uppercase sequences
    2. Has excessive uppercase letters compared to lowercase
    3. Very few common English words despite having lots of text
    4. High ratio of uppercase sequences that don't form real words
    5. Pure ASCII gibberish from font-encoded Chinese (e.g., "AAMAS RAMANA")

    NOTE: This function is designed to detect SCANNED documents with garbled OCR,
    not font encoding issues in normal PDFs (like "INtLOCUCTION"). Font encoding
    issues should be extracted as-is, not trigger OCR.

    Returns True if text appears garbled and should use OCR instead.
    """
    if len(text.strip()) < 50:
        return False

    cjk_chars = len(_CJK_CHAR_RE.findall(text))
    uppercase_sequences = _GARBLED_UPPERCASE_RE.findall(text)
    uppercase_chars = sum(len(seq) for seq in uppercase_sequences)

    # Count uppercase vs lowercase letters
    uppercase_count = sum(1 for c in text if c.isupper())
    lowercase_count = sum(1 for c in text if c.islower())
    total_alpha = uppercase_count + lowercase_count

    # Case 1: CJK characters mixed with lots of uppercase garbage
    if cjk_chars > 5 and uppercase_chars > 20:
        if uppercase_chars > cjk_chars * 0.5:
            return True

    # Case 2: ANY CJK chars with significant uppercase sequences
    if cjk_chars > 0 and uppercase_chars > 30:
        return True

    # Case 3: Pure ASCII gibberish (no CJK, but text doesn't look like English)
    # This catches font-encoded Chinese that appears as random ASCII
    if total_alpha > 100 and cjk_chars == 0:
        # Normal English has ~2-5% uppercase; gibberish often has >30%
        uppercase_ratio = uppercase_count / total_alpha if total_alpha > 0 else 0

        # Check for common English words
        words = text.lower().split()
        common_word_count = sum(1 for w in words if w.strip('.,;:!?()[]') in _COMMON_ENGLISH_WORDS)
        common_word_ratio = common_word_count / len(words) if words else 0

        # Gibberish: high uppercase AND very few common English words
        if uppercase_ratio > 0.4 and common_word_ratio < 0.05:
            return True

        # ENHANCED: More aggressive detection for random uppercase sequences
        # Typical pattern: "AAMAS RAMANA FRABEF NERA" (font-encoded Chinese)
        # - Many 3+ letter uppercase sequences
        # - Very few recognizable English words
        # - Lowered threshold from 0.1 to 0.15 for better detection
        if len(uppercase_sequences) > 5 and common_word_ratio < 0.15:
            return True
        
        # ENHANCED: Check for extremely low common word ratio even with moderate uppercase
        # This catches cases where there's some lowercase but still gibberish
        if uppercase_ratio > 0.25 and common_word_ratio < 0.1:
            return True

    return False


def _extract_tables_with_timeout(page, timeout: int = TABLE_EXTRACTION_TIMEOUT):
    """Extract tables from a pdfplumber page with a timeout to prevent hanging."""
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(page.extract_tables)
        try:
            return future.result(timeout=timeout)
        except FuturesTimeoutError:
            return None  # Timed out


def _normalize_header(line: str) -> str:
    """Lowercase + collapse 'Page: X/Y' so variable page numbers compare equal."""
    return _PAGE_NUM_RE.sub("Page: #/#", line.strip()).lower()


# ── label / caption helpers ─────────────────────────────────────────────────
def _sanitize_label(label: str) -> str:
    """Turn a raw caption into a short, filesystem-safe string (≤ 40 chars)."""
    if not label:
        return ""
    label = label.strip()
    label = re.sub(r'[/\\:*?"<>|]', '', label)        # strip FS-unsafe chars
    label = re.sub(r'[\s]+', '_', label)               # whitespace → _
    label = label.strip('_.-')                         # trim edges
    return label[:40].rstrip('_.-')


def _extract_caption_from_text(text: str) -> str:
    """Return the first figure/diagram caption found in *text*, or empty string.

    Chinese patterns are tried first – they are more specific and avoid
    false-positives on words like "configuration" that contain "fig".
    """
    for pat in (_CAPTION_RE_CN, _CAPTION_RE_EN):
        m = pat.search(text)
        if m:
            return m.group(0).strip()
    return ""


def _find_image_label(page, xref: int) -> str:
    """Return a sanitised label for an embedded raster image on a fitz *page*.

    Resolution order:
      1. Locate image rect → collect text-blocks within 60 pt vertically
         (≥ 30 % horizontal overlap).  Prefer blocks *below* the image.
      2. Among nearby blocks, return the first caption-pattern match.
      3. If no pattern match, use the shortest nearby block (< 80 chars).
      4. Final fallback: caption pattern anywhere on the page.
    """
    PROXIMITY_GAP = 60  # points above / below the image

    # ── locate image bounding-box on page ──
    img_rect = None
    try:
        rects = page.get_image_rects(xref)
        if rects:
            img_rect = rects[0]
    except Exception:
        pass  # older PyMuPDF – fall through to page-level search

    if img_rect:
        blocks = page.get_text("blocks")  # (x0, y0, x1, y1, text, block_no, block_type)
        nearby_below: list = []
        nearby_above: list = []

        for blk in blocks:
            if len(blk) < 5 or not blk[4].strip():
                continue
            bx0, by0, bx1, by1, txt = blk[:5]

            # horizontal overlap ≥ 30 % of image width
            h_overlap = min(img_rect.x1, bx1) - max(img_rect.x0, bx0)
            if h_overlap < 0.3 * max(img_rect.width, 1):
                continue

            if img_rect.y1 <= by0 <= img_rect.y1 + PROXIMITY_GAP:
                nearby_below.append((by0, txt.strip()))
            elif img_rect.y0 - PROXIMITY_GAP <= by1 <= img_rect.y0:
                nearby_above.append((by0, txt.strip()))

        # captions below the image are the norm in technical manuals
        nearby = sorted(nearby_below) + sorted(nearby_above)

        # 1st priority: explicit caption pattern
        for _, txt in nearby:
            cap = _extract_caption_from_text(txt)
            if cap:
                return _sanitize_label(cap)

        # 2nd priority: short nearby text block (likely an un-patterned label)
        for _, txt in nearby:
            if len(txt) < 80:
                return _sanitize_label(txt)

    # final fallback – regex scan of full page
    cap = _extract_caption_from_text(page.get_text())
    return _sanitize_label(cap)


def _find_page_label(page) -> str:
    """Caption for a full-page render (vector diagram / figure page)."""
    return _sanitize_label(_extract_caption_from_text(page.get_text()))


class _SafeStreamHandler(logging.StreamHandler):
    """StreamHandler that never crashes on unencodable characters.

    Windows PowerShell defaults to cp1252 which can't render box-drawing chars.
    Normal StreamHandler raises UnicodeEncodeError; this subclass catches it and
    re-encodes with errors="replace" (bad chars become '?') so the console output
    keeps flowing.  The FileHandler is unaffected and still writes full UTF-8.
    """

    def emit(self, record):
        try:
            super().emit(record)
        except UnicodeEncodeError:
            msg = self.format(record) + self.terminator
            self.stream.write(msg.encode("utf-8", errors="replace").decode("utf-8"))
            self.flush()

def _setup_logger(stage: str) -> logging.Logger:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_dir = os.path.join(LOGS_DIR, stage)
    os.makedirs(log_dir, exist_ok=True)

    logger = logging.getLogger(f"pdf_processor.{stage}")
    logger.setLevel(logging.DEBUG)
    logger.propagate = False

    if logger.hasHandlers():
        logger.handlers.clear()

    fmt = logging.Formatter(
        "[%(asctime)s] %(levelname)-7s %(message)s",
        datefmt="%H:%M:%S",
    )

    file_handler = logging.FileHandler(
        os.path.join(log_dir, f"{stage}_{timestamp}.log"),
        encoding="utf-8",
    )
    file_handler.setFormatter(fmt)

    console_handler = _SafeStreamHandler(stream=sys.stdout)
    console_handler.setFormatter(fmt)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return logger


def _load_env() -> dict:
    """Parse .env in the script directory (KEY=VALUE lines). No extra package needed."""
    env_path = os.path.join(_HERE, ".env")
    env: dict = {}
    if os.path.isfile(env_path):
        with open(env_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, value = line.partition("=")
                    env[key.strip()] = value.strip()
    return env


def _load_status(path: str) -> dict:
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return {}


def _save_status(path: str, status: dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(status, f, indent=2)


# ═════════════════════════════════════════════════════════════════════════════
# EXTRACTION PIPELINE
# ═════════════════════════════════════════════════════════════════════════════
def _recurring_logo_xrefs(doc) -> set:
    """Return image xrefs that appear on LOGO_PAGE_THRESHOLD+ pages (logos)."""
    counts: Counter = Counter()
    for pn in range(len(doc)):
        seen: set = set()
        for img in doc[pn].get_images(full=True):
            xref = img[0]
            if xref not in seen:
                counts[xref] += 1
                seen.add(xref)
    return {x for x, c in counts.items() if c >= LOGO_PAGE_THRESHOLD}


def _is_vector_diagram(page) -> bool:
    """True when the page is a real vector technical drawing, not a table or frame.

    All three checks must pass:
      1. At least MIN_DRAWINGS drawing primitives.
      2. Their combined bbox covers >= MIN_DRAWING_COVERAGE % of the page.
      3. Page text is short (< MAX_TEXT_FOR_DIAGRAM) — filters spec tables
         that have many cell-border paths but are mostly text.
    """
    drawings = page.get_drawings()
    if len(drawings) < MIN_DRAWINGS:
        return False

    rects = [fitz.Rect(d["rect"]) for d in drawings if d.get("rect")]
    if not rects:
        return False

    bbox = rects[0]
    for r in rects[1:]:
        bbox = bbox | fitz.Rect(r)

    page_area = page.rect.width * page.rect.height
    if page_area == 0:
        return False
    if bbox.width * bbox.height / page_area * 100 < MIN_DRAWING_COVERAGE:
        return False
    if len(page.get_text()) > MAX_TEXT_FOR_DIAGRAM:
        return False

    return True


def _safe_render_page(page, page_num: int, log: logging.Logger, dpi: int = None) -> tuple:
    """Safely render a page to PNG with timeout and error handling.
    
    Args:
        page: PyMuPDF page object
        page_num: Page number (1-indexed) for logging
        log: Logger instance
        dpi: Optional DPI override. If None, uses adaptive DPI based on complexity.
    
    Returns:
        tuple: (pixmap_or_none, success_bool, warning_message)
               Returns (None, False, error_msg) if rendering fails
    """
    # Determine DPI based on diagram complexity if not specified
    if dpi is None:
        drawings = page.get_drawings()
        num_drawings = len(drawings)
        
        if num_drawings > COMPLEX_DIAGRAM_THRESHOLD:
            dpi = LOW_RES_DPI
            log.info("  Page %d: Complex diagram detected (%d drawings) - using %d DPI",
                     page_num, num_drawings, dpi)
        else:
            dpi = HIGH_RES_DPI
    
    # Render with timeout protection
    def _render():
        return page.get_pixmap(dpi=dpi)
    
    try:
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(_render)
            try:
                pixmap = future.result(timeout=PAGE_RENDER_TIMEOUT)
                return pixmap, True, None
            except FuturesTimeoutError:
                warning = f"Page {page_num}: Rendering timed out after {PAGE_RENDER_TIMEOUT}s"
                log.warning("  %s - skipping", warning)
                return None, False, warning
    except MemoryError as e:
        warning = f"Page {page_num}: Out of memory during rendering"
        log.warning("  %s - skipping", warning)
        return None, False, warning
    except Exception as e:
        warning = f"Page {page_num}: Rendering failed - {type(e).__name__}: {e}"
        log.warning("  %s - skipping", warning)
        return None, False, warning


def _check_for_scanned_document(pages_text: list) -> tuple:
    """Check if the document appears to be scanned (too many empty pages).

    Args:
        pages_text: List of text content from each page.

    Returns:
        tuple: (is_scanned, total_empty_pages, max_consecutive_empty)
    """
    total_empty = 0
    max_consecutive = 0
    current_consecutive = 0

    for text in pages_text:
        if len(text.strip()) < MIN_TEXT_LENGTH_FOR_VALID_PAGE:
            total_empty += 1
            current_consecutive += 1
            max_consecutive = max(max_consecutive, current_consecutive)
        else:
            current_consecutive = 0

    is_scanned = max_consecutive >= CONSECUTIVE_EMPTY_PAGES_THRESHOLD
    return is_scanned, total_empty, max_consecutive



def _extract_text_with_ocr(pdf_path: str, log: logging.Logger, lang: str = "eng") -> list:
    """Extract text from PDF using OCR (for scanned documents).

    Args:
        pdf_path: Path to the PDF file.
        log:      Logger instance.
        lang:     Tesseract language string (e.g. 'eng', 'chi_sim', 'chi_sim+eng').

    Returns:
        List of (page_number, text) tuples, or empty list if OCR fails.
    """
    if not OCR_AVAILABLE:
        log.error("OCR dependencies not available. Install: pip install pdf2image pytesseract")
        log.error("Also install Tesseract OCR: https://github.com/tesseract-ocr/tesseract")
        return []

    log.info("  Starting OCR extraction (lang=%s) for scanned document...", lang)
    pages_text = []

    # Process pages in batches to avoid MemoryError on large PDFs
    OCR_BATCH_SIZE = 10

    try:
        # First, get total page count without loading images
        from pdf2image.pdf2image import pdfinfo_from_path
        try:
            info = pdfinfo_from_path(pdf_path)
            total_pages = info["Pages"]
        except Exception:
            # Fallback: use PyMuPDF to get page count
            doc = fitz.open(pdf_path)
            total_pages = len(doc)
            doc.close()

        log.info("  Processing %d pages in batches of %d...", total_pages, OCR_BATCH_SIZE)

        for batch_start in range(0, total_pages, OCR_BATCH_SIZE):
            batch_end = min(batch_start + OCR_BATCH_SIZE, total_pages)
            log.info("    Converting pages %d-%d to images...", batch_start + 1, batch_end)

            # Convert only this batch of pages (first_page and last_page are 1-indexed)
            images = convert_from_path(
                pdf_path,
                dpi=OCR_DPI,
                first_page=batch_start + 1,
                last_page=batch_end
            )

            for i, image in enumerate(images):
                page_num = batch_start + i + 1
                if page_num % 10 == 0 or page_num == total_pages:
                    log.info("    OCR processing page %d/%d", page_num, total_pages)


                # ── OCR with graceful language fallback ──
                try:
                    text = pytesseract.image_to_string(image, lang=lang)
                except pytesseract.TesseractError as te:
                    if "Failed loading language" in str(te):
                        log.warning("  Tesseract language '%s' not installed — "
                                    "falling back to 'eng'. Download tessdata from "
                                    "https://github.com/tessdata/tessdata and place "
                                    "in your Tesseract tessdata/ directory.", lang)
                        text = pytesseract.image_to_string(image, lang="eng")
                    else:
                        raise

                pages_text.append((page_num, text.strip()))

            # Clear batch images from memory
            del images

        log.info("  OCR extraction completed for %d pages", len(pages_text))

    except Exception as e:
        error_msg = str(e).lower()
        if "poppler" in error_msg or "page count" in error_msg:
            log.error("  OCR failed: Poppler is not installed or not in PATH")
            log.error("  Windows: Download from https://github.com/osber/poppler/releases")
            log.error("           Extract and add 'bin' folder to system PATH")
            log.error("  Or install via conda: conda install -c conda-forge poppler")
        else:
            log.error("  OCR extraction failed: %s", e)
        return []

    return pages_text


def _extract_single_page_with_ocr(pdf_path: str, page_num: int, log: logging.Logger, lang: str = "eng") -> str:
    """Extract text from a single PDF page using OCR.
    
    Args:
        pdf_path: Path to the PDF file.
        page_num: Page number to extract (1-indexed).
        log:      Logger instance.
        lang:     Tesseract language string (e.g. 'eng', 'chi_sim', 'chi_sim+eng').
    
    Returns:
        Extracted text from the page, or empty string if OCR fails.
    """
    if not OCR_AVAILABLE:
        log.error("OCR dependencies not available. Install: pip install pdf2image pytesseract")
        return ""
    
    try:
        log.info("    Page %d: Using OCR extraction (problematic page)", page_num)
        
        # Convert only this specific page
        images = convert_from_path(
            pdf_path,
            dpi=OCR_DPI,
            first_page=page_num,
            last_page=page_num
        )
        
        if not images:
            log.warning("    Page %d: Failed to convert to image for OCR", page_num)
            return ""
        
        # OCR with graceful language fallback
        try:
            text = pytesseract.image_to_string(images[0], lang=lang)
        except pytesseract.TesseractError as te:
            if "Failed loading language" in str(te):
                log.warning("  Tesseract language '%s' not installed — falling back to 'eng'", lang)
                text = pytesseract.image_to_string(images[0], lang="eng")
            else:
                raise
        
        return text.strip()
        
    except Exception as e:
        log.error("    Page %d: OCR extraction failed - %s", page_num, e)
        return ""


def _detect_ocr_language(doc, pdf_path: str = None) -> str:
    """Choose the Tesseract language string based on document content.

    Detection priority:
      1. PDF metadata ``language`` field (works even for fully-scanned docs).
      2. CJK vs Latin character counts in fitz text (first 10 pages).
      3. Sample OCR on first page (for scanned docs with garbled embedded text).
      4. Default ``'eng'``.
    """
    # 1. metadata hint
    meta_lang = ((doc.metadata or {}).get("language") or "").lower()
    if "zh" in meta_lang or "chi" in meta_lang or "中文" in meta_lang:
        return "chi_sim+eng"

    # 2. character-count heuristic from embedded text
    cjk_count  = 0
    latin_count = 0
    for i in range(min(len(doc), 10)):
        text = doc[i].get_text()
        cjk_count  += len(_CJK_CHAR_RE.findall(text))
        latin_count += sum(1 for ch in text if ch.isascii() and ch.isalpha())

    if cjk_count > 20 and latin_count > 20:
        return "chi_sim+eng"
    if cjk_count > 20:
        return "chi_sim"
    
    # 3. Sample OCR fallback for scanned documents
    # If we have very little embedded text (likely scanned), try OCR on first page
    # to detect the actual language
    if OCR_AVAILABLE and pdf_path and (cjk_count == 0 and latin_count < 100):
        try:
            from pdf2image import convert_from_path
            # Convert only first page at low DPI for quick detection
            images = convert_from_path(pdf_path, dpi=150, first_page=1, last_page=1)
            if images:
                # Try OCR with Chinese to see if we get CJK characters
                sample_text = pytesseract.image_to_string(images[0], lang="chi_sim+eng")
                sample_cjk = len(_CJK_CHAR_RE.findall(sample_text))
                
                # If we found significant Chinese characters, use Chinese OCR
                if sample_cjk > 10:
                    return "chi_sim+eng"
                elif sample_cjk > 0:
                    return "chi_sim+eng"  # Even a few CJK chars suggest mixed content
        except Exception:
            pass  # Fallback to default if sample OCR fails
    
    return "eng"


def _get_page_rotations(doc) -> dict:
    """Return {page_index: rotation_degrees} for every page with non-zero /Rotate.

    Works on both scanned and vector PDFs – any page whose metadata declares
    a rotation will appear here so the caller can apply a fallback.
    """
    rotations: dict = {}
    for i in range(len(doc)):
        r = doc[i].rotation
        if r != 0:
            rotations[i] = r
    return rotations


def _extract_pdf(pdf_path: str, out_dir: str, log: logging.Logger) -> None:
    """Extract text + images from one PDF into out_dir/."""
    doc = fitz.open(pdf_path)
    os.makedirs(out_dir, exist_ok=True)

    # ── Text extraction using pdfplumber (better table handling) ──────
    text_path = os.path.join(out_dir, "text.txt")
    pdf_path_str = str(pdf_path)  # Convert to string for pdfplumber
    extraction_method = "standard"

    # ── detect rotated pages (applies to ALL PDFs, not just scanned) ──
    page_rotations = _get_page_rotations(doc)
    if page_rotations:
        log.info("  Rotated pages detected: %s",
                 {k + 1: v for k, v in page_rotations.items()})

    # ── Check for specific PDFs that require OCR (e.g., high-res diagrams) ──
    # Format: {filename: "all"} for full OCR, or {filename: [page_nums]} for specific pages
    pdf_filename = os.path.basename(pdf_path)
    force_ocr_config = {
        "ID&HR Fan_TLT_OEM Manual.pdf": [45],  # Page 45 has very high-resolution diagram (27796 drawings)
    }
    
    # ── Pre-check first 3 pages to decide extraction method ──
    # If all first 3 pages are empty OR have garbled text, use OCR
    ocr_config = force_ocr_config.get(pdf_filename)
    use_ocr = ocr_config == "all"  # Full OCR only if explicitly set to "all"
    ocr_pages_only = ocr_config if isinstance(ocr_config, list) else []  # Specific pages for OCR
    
    if use_ocr:
        log.info("  Forcing OCR extraction for entire PDF (contains problematic high-res diagrams)")
    elif ocr_pages_only:
        log.info("  Using OCR for specific pages: %s (rest will use standard extraction)", ocr_pages_only)
    else:
        with pdfplumber.open(pdf_path_str) as pdf:
            total_pages = len(pdf.pages)
            pages_to_check = min(3, total_pages)
            log.info("  Checking first %d pages to determine extraction method...", pages_to_check)

            empty_count = 0
            garbled_count = 0
            for pn in range(pages_to_check):
                page = pdf.pages[pn]
                text = page.extract_text() or ""
                # Also try PyMuPDF for rotated pages
                if len(text.strip()) < MIN_TEXT_LENGTH_FOR_VALID_PAGE and pn in page_rotations:
                    text = doc[pn].get_text()

                if len(text.strip()) < MIN_TEXT_LENGTH_FOR_VALID_PAGE:
                    empty_count += 1
                    log.info("    Page %d: empty (<%d chars)", pn + 1, MIN_TEXT_LENGTH_FOR_VALID_PAGE)
                elif _is_garbled_text(text):
                    garbled_count += 1
                    log.info("    Page %d: garbled text detected (%d chars)", pn + 1, len(text.strip()))
                else:
                    log.info("    Page %d: has text (%d chars)", pn + 1, len(text.strip()))

            if empty_count == pages_to_check:
                log.info("  All first %d pages are empty - document appears to be scanned", pages_to_check)
                use_ocr = True
            # DISABLED: Garbled text detection was triggering OCR for normal PDFs with font encoding issues
            # OCR extraction loses table structure, so we only use it for truly scanned documents
            # The old script didn't have this check and successfully extracted tables
            # elif garbled_count > 0:
            #     log.info("  Detected garbled text in %d page(s) - using OCR for better extraction", garbled_count)
            #     use_ocr = True
            else:
                log.info("  Found text in first %d pages - using standard extraction", pages_to_check)

    pages_content = []  # Store (page_num, content) tuples
    skip_text_file = False  # Flag to skip text file for scanned docs without OCR

    if use_ocr:
        # Use OCR for scanned document
        if OCR_AVAILABLE:
            ocr_lang = _detect_ocr_language(doc, pdf_path)
            log.info("  Detected OCR language: %s", ocr_lang)
            ocr_pages = _extract_text_with_ocr(pdf_path, log, lang=ocr_lang)
            if ocr_pages:
                extraction_method = "ocr"
                pages_content = ocr_pages
            else:
                log.warning("  OCR failed - skipping text file for scanned document")
                skip_text_file = True
        else:
            log.warning("  OCR not available - skipping text file for scanned document")
            log.warning("  Install OCR: pip install pdf2image pytesseract")
            log.warning("  Install Poppler: https://github.com/osber/poppler/releases")
            skip_text_file = True
    else:
        # Standard extraction for normal PDFs (with optional page-specific OCR)
        ocr_lang = None  # Detect language only if needed
        
        with pdfplumber.open(pdf_path_str) as pdf:
            total_pages = len(pdf.pages)
            log.info("  Processing %d pages (standard extraction)...", total_pages)

            for pn, page in enumerate(pdf.pages):
                page_num = pn + 1
                
                if pn % 20 == 0 or pn == total_pages - 1:
                    log.info("    Page %d/%d", page_num, total_pages)

                # ── Check if this specific page needs OCR ──
                if page_num in ocr_pages_only:
                    # Detect OCR language once if not already done
                    if ocr_lang is None:
                        ocr_lang = _detect_ocr_language(doc, pdf_path)
                        log.info("  Detected OCR language: %s", ocr_lang)
                    
                    # Use OCR for this page
                    ocr_text = _extract_single_page_with_ocr(pdf_path, page_num, log, lang=ocr_lang)
                    pages_content.append((page_num, ocr_text))
                    continue  # Skip standard extraction for this page

                page_content = []

                # Extract tables from the page (with timeout to prevent hanging)
                tables = _extract_tables_with_timeout(page)

                if tables is None:
                    log.warning("    Table extraction timed out on page %d - using text only", page_num)
                    tables = []
                elif tables:
                    log.info("    Page %d: Found %d table(s)", page_num, len(tables))
                    for i, table in enumerate(tables):
                        if table:
                            rows = len(table)
                            cols = max(len(row) for row in table) if table else 0
                            log.debug("      Table %d: %d rows x %d cols", i+1, rows, cols)

                if tables:
                    # Page has tables - extract them formatted
                    for table_idx, table in enumerate(tables):
                        if not table or len(table) == 0:
                            continue

                        page_content.append(f"\n[TABLE {table_idx + 1}]")

                        # Find max width for each column
                        num_cols = max(len(row) for row in table)
                        col_widths = [0] * num_cols

                        for row in table:
                            for i, cell in enumerate(row):
                                if i < num_cols and cell:
                                    col_widths[i] = max(col_widths[i], len(str(cell)))

                        # Write table rows
                        for row_idx, row in enumerate(table):
                            # Pad row to num_cols
                            padded_row = list(row) + [None] * (num_cols - len(row))

                            # Format cells with padding
                            cells = []
                            for i in range(num_cols):
                                cell = str(padded_row[i] or "").strip()
                                cells.append(cell.ljust(col_widths[i]))

                            page_content.append("| " + " | ".join(cells) + " |")

                            # Add separator after first row
                            if row_idx == 0:
                                separators = ["-" * col_widths[i] for i in range(num_cols)]
                                page_content.append("| " + " | ".join(separators) + " |")

                        page_content.append("")

                # Extract all text (includes non-table text and table text)
                text = page.extract_text()
                if text:
                    page_content.append(text.strip())

                # ── rotation fallback (all PDFs, not just scanned) ──
                # If pdfplumber returned very little text but PyMuPDF knows the
                # page is rotated, use fitz extraction which handles /Rotate
                # reliably.  Catches metadata-rotated pages where pdfplumber /
                # pdfminer mis-applies the angle.
                if pn in page_rotations:
                    plumber_out = "\n".join(page_content).strip()
                    if len(plumber_out) < MIN_TEXT_LENGTH_FOR_VALID_PAGE:
                        fitz_text = doc[pn].get_text().strip()
                        if len(fitz_text) >= MIN_TEXT_LENGTH_FOR_VALID_PAGE:
                            page_content = [fitz_text]
                            log.info("    Page %d: rotation=%d° — pdfplumber "
                                     "yielded %d chars, switched to PyMuPDF "
                                     "(%d chars)",
                                     page_num, page_rotations[pn],
                                     len(plumber_out), len(fitz_text))

                pages_content.append((page_num, "\n".join(page_content)))
        
        # Update extraction method if we used page-specific OCR
        if ocr_pages_only:
            extraction_method = f"standard+ocr(pages:{ocr_pages_only})"

    # Write extracted text to file (skip for scanned docs without OCR)
    if skip_text_file:
        log.info("  Skipped text file (scanned document, OCR unavailable)")
    else:
        with open(text_path, "w", encoding="utf-8") as f:
            for page_num, content in pages_content:
                f.write(f"===== Page {page_num} =====\n")
                f.write(content.strip() + "\n\n")
        log.info("Text -> %s (method: %s)", text_path, extraction_method)

    # ── Images (three-phase) ────────────────────────────────────────────
    img_dir = os.path.join(out_dir, "images")
    os.makedirs(img_dir, exist_ok=True)

    logo_xrefs = _recurring_logo_xrefs(doc)
    log.info("Filtered %d recurring logo xref(s)", len(logo_xrefs))

    # Build set of pages that contain a figure keyword for Phase 3
    # (English "figure" + Chinese "图" covers the bulk of industrial manuals)
    figure_pages = set()
    for page_num, content in pages_content:
        content_lower = content.lower()
        if "figure" in content_lower or "图" in content:
            figure_pages.add(page_num)
    if figure_pages:
        log.info("Detected %d page(s) containing figure keyword: %s", len(figure_pages), sorted(figure_pages))

    seen_xrefs: set = set()
    rendered_pages: set = set()  # Track pages already rendered as full-page images
    n_embedded = n_rendered = n_figure = 0

    for pn in range(len(doc)):
        page = doc[pn]
        page_num = pn + 1
        page_had_image = False

        # Phase 1 – extract embedded raster images (skip logos + tiny icons)
        for img in page.get_images(full=True):
            xref = img[0]
            if xref in logo_xrefs or xref in seen_xrefs:
                continue

            raw = doc.extract_image(xref)
            w, h, size = raw["width"], raw["height"], len(raw["image"])
            if w < MIN_IMG_WIDTH or h < MIN_IMG_HEIGHT or size < MIN_IMG_BYTES:
                continue

            ext = raw.get("ext", "png")
            label = _find_image_label(page, xref)
            fname = (f"diagram_p{page_num}_{n_embedded}_{label}.{ext}"
                     if label else f"diagram_p{page_num}_{n_embedded}.{ext}")
            with open(os.path.join(img_dir, fname), "wb") as f:
                f.write(raw["image"])

            seen_xrefs.add(xref)
            n_embedded += 1
            page_had_image = True
            log.info("  Extracted: %s  (%dx%d, %.1f KB)", fname, w, h, size / 1024)

        # Phase 2 – render full page only for pure vector diagrams
        if not page_had_image and _is_vector_diagram(page):
            label = _find_page_label(page)
            fname = (f"page_{page_num}_{label}_highres.png"
                     if label else f"page_{page_num}_highres.png")
            
            # Use safe rendering with timeout and adaptive DPI
            pixmap, success, warning = _safe_render_page(page, page_num, log)
            if success and pixmap:
                pixmap.save(os.path.join(img_dir, fname))
                n_rendered += 1
                rendered_pages.add(page_num)
                log.info("  Rendered (vector): %s", fname)
            # If rendering failed, warning already logged by _safe_render_page

        # Phase 3 – render full page for pages containing a figure keyword
        # (captures diagrams with labels, even if text was already extracted)
        if page_num in figure_pages and page_num not in rendered_pages:
            label = _find_page_label(page)
            fname = (f"figure_p{page_num}_{label}.png"
                     if label else f"figure_p{page_num}.png")
            
            # Use safe rendering with timeout and adaptive DPI
            pixmap, success, warning = _safe_render_page(page, page_num, log)
            if success and pixmap:
                pixmap.save(os.path.join(img_dir, fname))
                n_figure += 1
                rendered_pages.add(page_num)
                log.info("  Rendered (figure): %s", fname)
            # If rendering failed, warning already logged by _safe_render_page

    doc.close()
    log.info("Images done — %d embedded, %d vector, %d figure pages", n_embedded, n_rendered, n_figure)


def run_extraction(log: logging.Logger, force: bool = False, target_file: str = None) -> None:
    """Iterate every source folder and extract all PDFs not yet processed."""
    status = _load_status(STATUS_EXTRACT)

    for source_dir in PDF_SOURCES:
        if not os.path.isdir(source_dir):
            log.warning("Source folder missing – skipped: %s", source_dir)
            continue

        label = os.path.basename(source_dir)  # "pdfs" or "pdfs_pellet"

        for fname in sorted(os.listdir(source_dir)):
            if not fname.lower().endswith(".pdf"):
                continue

            if target_file and target_file.lower() not in fname.lower():
                continue

            key = f"{label}/{fname}"
            if not force and status.get(key, {}).get("status") == "done":
                log.info("Already extracted – skip: %s", key)
                continue

            pdf_path = os.path.join(source_dir, fname)
            out_dir  = os.path.join(EXTRACTED_DIR, label, os.path.splitext(fname)[0])

            log.info("--- %s", key)
            try:
                _extract_pdf(pdf_path, out_dir, log)
                status[key] = {
                    "status":     "done",
                    "source":     pdf_path,
                    "output_dir": out_dir,
                    "timestamp":  datetime.now().isoformat(),
                }
            except Exception as exc:
                log.error("FAILED - %s: %s", key, exc)
                status[key] = {
                    "status":    "error",
                    "error":     str(exc),
                    "timestamp": datetime.now().isoformat(),
                }
            # Save status after each file (incremental)
            _save_status(STATUS_EXTRACT, status)

    log.info("Status -> %s", STATUS_EXTRACT)


# ═════════════════════════════════════════════════════════════════════════════
# CLEANUP PIPELINE
# ═════════════════════════════════════════════════════════════════════════════
def _detect_recurring_headers(page_lines_list: list) -> set:
    """Find normalized lines appearing on HEADER_MIN_OCCURRENCE fraction of pages.

    Returns a set of *normalized* strings.  Use _normalize_header() on any
    candidate line before checking membership.
    """
    counts: Counter = Counter()
    for lines in page_lines_list:
        seen: set = set()
        for line in lines:
            norm = _normalize_header(line)
            if norm and norm not in seen:
                counts[norm] += 1
                seen.add(norm)

    threshold = max(3, len(page_lines_list) * HEADER_MIN_OCCURRENCE)
    return {norm for norm, cnt in counts.items() if cnt >= threshold}


def _rejoin_fragments(lines: list) -> list:
    """Join runs of MIN_FRAGMENT_RUN+ consecutive single-word lines into one line.

    PDF text extraction breaks narrow-column text (e.g. beside an image) into
    one word per line.  This rejoins those runs while leaving real single-word
    lines (labels, list markers) untouched.
    """
    result: list = []
    run: list = []

    for line in lines:
        if len(line.split()) == 1 and len(line) < 30:
            run.append(line)
        else:
            # flush accumulated single-word run
            if len(run) >= MIN_FRAGMENT_RUN:
                result.append(" ".join(run))
            else:
                result.extend(run)
            run = []
            result.append(line)

    # flush trailing run
    if len(run) >= MIN_FRAGMENT_RUN:
        result.append(" ".join(run))
    else:
        result.extend(run)

    return result


def _clean_text(raw_path: str, clean_path: str, log: logging.Logger) -> None:
    """Full cleanup pass on one extracted text file.

    Steps applied per page section:
      1. Strip trailing whitespace on every line.
      2. Collapse consecutive blank lines → single blank line.
      3. Remove auto-detected recurring headers / footers.
      4. Rejoin fragmented single-word lines.
    """
    with open(raw_path, encoding="utf-8") as f:
        raw = f.read()

    # Split into per-page sections (keep the ===== Page X ===== markers)
    parts = re.split(r"(===== Page \d+ =====)", raw)

    pages: list = []  # [(marker, [lines]), ...]
    for i in range(1, len(parts), 2):
        marker  = parts[i]
        content = parts[i + 1] if i + 1 < len(parts) else ""
        pages.append((marker, [line.rstrip() for line in content.split("\n")]))

    # Detect recurring headers across the whole document
    headers = _detect_recurring_headers([lines for _, lines in pages])
    if headers:
        log.info("  Removing %d recurring header pattern(s)", len(headers))

    # Clean each page section
    cleaned: list = []
    for marker, lines in pages:
        # 1. Drop recurring headers (compare via normalized form)
        lines = [l for l in lines if _normalize_header(l) not in headers]

        # 2. Collapse blank lines
        collapsed: list = []
        prev_blank = False
        for line in lines:
            is_blank = not line.strip()
            if is_blank and prev_blank:
                continue
            collapsed.append(line)
            prev_blank = is_blank
        lines = collapsed

        # 3. Rejoin word fragments
        lines = _rejoin_fragments(lines)

        # Trim leading / trailing blank lines from section
        while lines and not lines[0].strip():
            lines.pop(0)
        while lines and not lines[-1].strip():
            lines.pop()

        cleaned.append(marker + ("\n" + "\n".join(lines) if lines else ""))

    os.makedirs(os.path.dirname(clean_path), exist_ok=True)
    with open(clean_path, "w", encoding="utf-8") as f:
        f.write("\n\n".join(cleaned) + "\n")

    log.info("  Cleaned → %s", clean_path)


def run_cleanup(log: logging.Logger, force: bool = False, target_file: str = None) -> None:
    """Walk extracted/ and clean every text.txt not yet processed."""
    status = _load_status(STATUS_CLEAN)

    if not os.path.isdir(EXTRACTED_DIR):
        log.warning("No extracted data at %s – run extraction first", EXTRACTED_DIR)
        return

    for source_label in sorted(os.listdir(EXTRACTED_DIR)):
        source_path = os.path.join(EXTRACTED_DIR, source_label)
        if not os.path.isdir(source_path):
            continue

        for pdf_stem in sorted(os.listdir(source_path)):
            raw_text = os.path.join(source_path, pdf_stem, "text.txt")
            if not os.path.isfile(raw_text):
                continue

            if target_file and target_file.lower() not in (pdf_stem + ".pdf").lower():
                continue

            key = f"{source_label}/{pdf_stem}"
            if not force and status.get(key, {}).get("status") == "done":
                log.info("Already cleaned – skip: %s", key)
                continue

            log.info("--- %s", key)
            clean_text = os.path.join(CLEANED_DIR, source_label, pdf_stem, "text.txt")
            try:
                _clean_text(raw_text, clean_text, log)
                status[key] = {
                    "status":    "done",
                    "source":    raw_text,
                    "output":    clean_text,
                    "timestamp": datetime.now().isoformat(),
                }
            except Exception as exc:
                log.error("FAILED - %s: %s", key, exc)
                status[key] = {
                    "status":    "error",
                    "error":     str(exc),
                    "timestamp": datetime.now().isoformat(),
                }
            # Save status after each file (incremental)
            _save_status(STATUS_CLEAN, status)

    log.info("Status -> %s", STATUS_CLEAN)


# ═════════════════════════════════════════════════════════════════════════════
# INGESTION PIPELINE
# ═════════════════════════════════════════════════════════════════════════════
# group(1) = page number, group(2) = optional sanitised label (may be None)
_IMG_EMBEDDED_RE = re.compile(r"^diagram_p(\d+)_\d+(?:_([^.]+))?\.")   # diagram_p6_2.png  |  diagram_p6_2_Fig1.png
_IMG_RENDERED_RE = re.compile(r"^page_(\d+)(?:_(.+))?_highres\.")      # page_11_highres.png  |  page_11_Fig1_highres.png
_IMG_FIGURE_RE   = re.compile(r"^figure_p(\d+)(?:_([^.]+))?\.")        # figure_p5.png  |  figure_p5_Fig1.png


def _load_config() -> dict:
    """Load weaviate_config.json, then overlay credentials from .env if present."""
    with open(CONFIG_PATH, encoding="utf-8") as f:
        cfg = json.load(f)

    env = _load_env()
    if "WEAVIATE_URL" in env:
        cfg["weaviate"]["url"] = env["WEAVIATE_URL"]
    if "WEAVIATE_API_KEY" in env:
        cfg["weaviate"]["api_key"] = env["WEAVIATE_API_KEY"]
    if "HUGGINGFACE_API_KEY" in env:
        cfg["embedding"]["huggingface_api_key"] = env["HUGGINGFACE_API_KEY"]

    return cfg


def _parse_pages(text: str) -> list:
    """Split cleaned text into [(page_number, content), ...] pairs."""
    parts = re.split(r"(===== Page (\d+) =====)", text)
    # layout: [preamble, marker, num, content, marker, num, content, …]
    pages = []
    i = 1
    while i < len(parts):
        page_num = int(parts[i + 1])
        content  = parts[i + 2].strip() if i + 2 < len(parts) else ""
        if content:
            pages.append((page_num, content))
        i += 3
    return pages


def _chunk_text(text: str, words_per_chunk: int, overlap: int) -> list:
    """Split text into overlapping word-based chunks."""
    words = text.split()
    if len(words) <= words_per_chunk:
        return [text]

    chunks = []
    step = words_per_chunk - overlap
    for start in range(0, len(words), step):
        chunk_words = words[start:start + words_per_chunk]
        chunks.append(" ".join(chunk_words))
        if start + words_per_chunk >= len(words):
            break
    return chunks


def _parse_image_filename(fname: str) -> tuple:
    """Return (page_number, image_type, label) or (None, None, None).

    *label* is the sanitised caption embedded in the filename during extraction,
    or an empty string when no caption was found.
    """
    m = _IMG_EMBEDDED_RE.match(fname)
    if m:
        return int(m.group(1)), "embedded", m.group(2) or ""
    m = _IMG_RENDERED_RE.match(fname)
    if m:
        return int(m.group(1)), "vector_render", m.group(2) or ""
    m = _IMG_FIGURE_RE.match(fname)
    if m:
        return int(m.group(1)), "figure_page", m.group(2) or ""
    return None, None, None


def _create_collection(client, cfg: dict, log: logging.Logger):
    """Create the Weaviate collection, or return it if it already exists."""
    from weaviate.classes.config import Configure, Property, DataType, Tokenization

    name = cfg["collection"]["name"]

    try:
        collection = client.collections.get(name)
        log.info("Collection '%s' already exists – using as-is", name)
        return collection
    except Exception:
        pass  # collection does not exist

    def _skip(prop_name: str):
        """TEXT/KEYWORD property excluded from vectorization."""
        return Property(
            name=prop_name,
            data_type=DataType.TEXT,
            tokenization=Tokenization.KEYWORD,
            vectorizer_config=Configure.VectorizerConfig.text2vec_huggingface(skip=True),
        )

    collection = client.collections.create(
        name=name,
        vectorizer_config=Configure.Vectorizer.text2vec_huggingface(
            model=cfg["embedding"]["model"],
        ),
        properties=[
            Property(name="content",     data_type=DataType.TEXT),   # only vectorized field
            _skip("chunkType"),
            _skip("sourcePdf"),
            _skip("sourceFolder"),
            Property(name="pageNumber",  data_type=DataType.INT),
            Property(name="chunkIndex",  data_type=DataType.INT),
            _skip("imageType"),
            _skip("imagePath"),
            _skip("collectionName"),  # collection name from config for metadata tracking
        ],
    )
    log.info("Created collection '%s'", name)
    return collection


def _ingest_text(collection, cfg: dict, status: dict, log: logging.Logger, force: bool, target_file: str = None) -> None:
    """Chunk every cleaned text file and batch-insert into Weaviate."""
    cleaned_dir = os.path.join(_HERE, cfg["data"]["cleaned_text_dir"])
    if not os.path.isdir(cleaned_dir):
        log.warning("Cleaned text dir not found: %s", cleaned_dir)
        return

    wpc  = cfg["chunking"]["words_per_chunk"]
    ovlp = cfg["chunking"]["overlap_words"]
    collection_name = cfg["collection"]["name"]  # Get collection name from config

    with collection.batch.fixed_size(batch_size=cfg["ingestion"]["batch_size"]) as batch:
        for source_label in sorted(os.listdir(cleaned_dir)):
            label_path = os.path.join(cleaned_dir, source_label)
            if not os.path.isdir(label_path):
                continue

            for pdf_stem in sorted(os.listdir(label_path)):
                text_file = os.path.join(label_path, pdf_stem, "text.txt")
                if not os.path.isfile(text_file):
                    continue

                if target_file and target_file.lower() not in (pdf_stem + ".pdf").lower():
                    continue

                key = f"text/{source_label}/{pdf_stem}"
                if not force and status.get(key, {}).get("status") == "done":
                    log.info("Already ingested – skip: %s", key)
                    continue

                log.info("--- %s", key)
                with open(text_file, encoding="utf-8") as f:
                    raw = f.read()

                n_chunks = 0
                for page_num, content in _parse_pages(raw):
                    for idx, chunk in enumerate(_chunk_text(content, wpc, ovlp)):
                        batch.add_object(properties={
                            "content":      chunk,
                            "chunkType":    "text",
                            "sourcePdf":    pdf_stem,
                            "sourceFolder": source_label,
                            "pageNumber":   page_num,
                            "chunkIndex":   idx,
                            "collectionName": collection_name,
                        })
                        n_chunks += 1

                log.info("  Ingested %d text chunk(s)", n_chunks)
                status[key] = {
                    "status":    "done",
                    "chunks":    n_chunks,
                    "timestamp": datetime.now().isoformat(),
                }
                # Save status after each file (incremental)
                _save_status(STATUS_INGEST, status)


def _ingest_images(collection, cfg: dict, status: dict, log: logging.Logger, force: bool, target_file: str = None) -> None:
    """Batch-insert image metadata (with a descriptive content string) into Weaviate."""
    images_base = os.path.join(_HERE, cfg["data"]["images_base_dir"])
    if not os.path.isdir(images_base):
        log.warning("Images base dir not found: %s", images_base)
        return

    collection_name = cfg["collection"]["name"]  # Get collection name from config

    with collection.batch.fixed_size(batch_size=cfg["ingestion"]["batch_size"]) as batch:
        for source_label in sorted(os.listdir(images_base)):
            label_path = os.path.join(images_base, source_label)
            if not os.path.isdir(label_path):
                continue

            for pdf_stem in sorted(os.listdir(label_path)):
                img_dir = os.path.join(label_path, pdf_stem, "images")
                if not os.path.isdir(img_dir):
                    continue

                if target_file and target_file.lower() not in (pdf_stem + ".pdf").lower():
                    continue

                key = f"images/{source_label}/{pdf_stem}"
                if not force and status.get(key, {}).get("status") == "done":
                    log.info("Already ingested – skip: %s", key)
                    continue

                log.info("--- %s", key)
                n_images = 0
                for fname in sorted(os.listdir(img_dir)):
                    page_num, img_type, label = _parse_image_filename(fname)
                    if page_num is None:
                        continue

                    # Include the label in the searchable content string so
                    # retrieval can match on the caption text.
                    label_display = label.replace("_", " ") if label else ""
                    content_str = (
                        f"[{img_type} diagram] {label_display} — Page {page_num} from {pdf_stem}"
                        if label_display
                        else f"[{img_type} diagram] Page {page_num} from {pdf_stem}"
                    )

                    rel_path = "/".join([
                        cfg["data"]["images_base_dir"],
                        source_label, pdf_stem, "images", fname,
                    ])
                    batch.add_object(properties={
                        "content":      content_str,
                        "chunkType":    "image",
                        "sourcePdf":    pdf_stem,
                        "sourceFolder": source_label,
                        "pageNumber":   page_num,
                        "chunkIndex":   0,
                        "imageType":    img_type,
                        "imagePath":    rel_path,
                        "collectionName": collection_name,
                    })
                    n_images += 1

                log.info("  Ingested %d image(s)", n_images)
                status[key] = {
                    "status":    "done",
                    "images":    n_images,
                    "timestamp": datetime.now().isoformat(),
                }
                # Save status after each file (incremental)
                _save_status(STATUS_INGEST, status)


def run_ingestion(log: logging.Logger, force: bool = False, target_file: str = None) -> None:
    """Connect to Weaviate Cloud, create collection, and ingest text + images."""
    if weaviate is None:
        log.error("weaviate-client not installed – run: pip install weaviate-client")
        return

    cfg    = _load_config()
    status = _load_status(STATUS_INGEST)

    headers = {}
    hf_key = cfg["embedding"].get("huggingface_api_key", "")
    if hf_key:
        headers["X-HuggingFace-Api-Key"] = hf_key

    # ApiKey was introduced in a later v4 build; fall back to the internal
    # class for older installs.  Upgrade: pip install --upgrade weaviate-client
    log.info("Connecting to Weaviate at %s …", cfg["weaviate"]["url"])

    _auth_cls = getattr(weaviate.auth, "ApiKey", None) or getattr(
        weaviate.auth, "_APIKey", None
    )

    try:
        client = weaviate.connect_to_weaviate_cloud(
            cluster_url=cfg["weaviate"]["url"],
            auth_credentials=_auth_cls(api_key=cfg["weaviate"]["api_key"]),
            additional_headers=headers,
        )
    except TypeError:
        if headers:
            log.warning(
                "additional_headers not supported – upgrade weaviate-client; retrying without …"
            )
        client = weaviate.connect_to_weaviate_cloud(
            cluster_url=cfg["weaviate"]["url"],
            auth_credentials=_auth_cls(api_key=cfg["weaviate"]["api_key"]),
        )

    try:
        collection = _create_collection(client, cfg, log)

        if cfg["ingestion"].get("ingest_text", True):
            log.info("── Ingesting text …")
            _ingest_text(collection, cfg, status, log, force, target_file)
            _save_status(STATUS_INGEST, status)

        if cfg["ingestion"].get("ingest_images", True):
            log.info("── Ingesting images …")
            _ingest_images(collection, cfg, status, log, force, target_file)
            _save_status(STATUS_INGEST, status)
    finally:
        client.close()


# ═════════════════════════════════════════════════════════════════════════════
# MAIN
# ═════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    force = "--force" in sys.argv
    
    target_file = None
    if "--file" in sys.argv:
        try:
            file_idx = sys.argv.index("--file") + 1
            if file_idx < len(sys.argv):
                target_file = sys.argv[file_idx]
        except ValueError:
            pass

    # Determine which phases to run
    run_extract = "--extract" in sys.argv
    run_clean = "--cleanup" in sys.argv
    run_ingest = "--ingest" in sys.argv
    run_all = "--all" in sys.argv

    # If no phase flags specified, run all phases
    if not (run_extract or run_clean or run_ingest or run_all):
        run_all = True

    if run_all:
        run_extract = run_clean = run_ingest = True

    # Phase 1 – Extraction
    if run_extract:
        extract_log = _setup_logger("extracted")
        extract_log.info("═══ EXTRACTION PIPELINE START ═══")
        run_extraction(extract_log, force=force, target_file=target_file)
        extract_log.info("═══ EXTRACTION PIPELINE DONE ═══")

    # Phase 2 – Cleanup  (runs on Phase 1 output)
    if run_clean:
        clean_log = _setup_logger("cleaned")
        clean_log.info("═══ CLEANUP PIPELINE START ═══")
        run_cleanup(clean_log, force=force, target_file=target_file)
        clean_log.info("═══ CLEANUP PIPELINE DONE ═══")

    # Phase 3 – Ingestion  (runs on Phase 2 output)
    if run_ingest:
        ingest_log = _setup_logger("ingestion")
        ingest_log.info("═══ INGESTION PIPELINE START ═══")
        run_ingestion(ingest_log, force=force, target_file=target_file)
        ingest_log.info("═══ INGESTION PIPELINE DONE ═══")
