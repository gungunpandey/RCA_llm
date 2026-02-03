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


# ─────────────────────────────────────────────────────────────────────────────
# PATHS  (all relative to this script's directory)
# ─────────────────────────────────────────────────────────────────────────────
_HERE = os.path.dirname(os.path.abspath(__file__))

PDF_SOURCES = [
    # os.path.join(_HERE, "pdfs"),
    os.path.join(_HERE, "pdfs_pellet"),
]

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


# ─────────────────────────────────────────────────────────────────────────────
# CLEANUP SETTINGS
# ─────────────────────────────────────────────────────────────────────────────
HEADER_MIN_OCCURRENCE = 0.5    # fraction of pages a line must appear on → boilerplate
MIN_FRAGMENT_RUN      = 4      # consecutive single-word lines needed to trigger rejoin


# ═════════════════════════════════════════════════════════════════════════════
# SHARED HELPERS
# ═════════════════════════════════════════════════════════════════════════════
_PAGE_NUM_RE = re.compile(r"Page:\s*\d+\s*/\s*\d+")


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


def _extract_pdf(pdf_path: str, out_dir: str, log: logging.Logger) -> None:
    """Extract text + images from one PDF into out_dir/."""
    doc = fitz.open(pdf_path)
    os.makedirs(out_dir, exist_ok=True)

    # ── Text extraction using pdfplumber (better table handling) ──────
    text_path = os.path.join(out_dir, "text.txt")
    pdf_path_str = str(pdf_path)  # Convert to string for pdfplumber

    with pdfplumber.open(pdf_path_str) as pdf:
        total_pages = len(pdf.pages)
        log.info("  Processing %d pages...", total_pages)
        with open(text_path, "w", encoding="utf-8") as f:
            for pn, page in enumerate(pdf.pages):
                if pn % 20 == 0 or pn == total_pages - 1:
                    log.info("    Page %d/%d", pn + 1, total_pages)
                f.write(f"===== Page {pn + 1} =====\n")

                # Extract tables from the page (with timeout to prevent hanging)
                tables = _extract_tables_with_timeout(page)

                if tables is None:
                    log.warning("    Table extraction timed out on page %d - using text only", pn + 1)
                    tables = []

                if tables:
                    # Page has tables - extract them formatted
                    for table_idx, table in enumerate(tables):
                        if not table or len(table) == 0:
                            continue

                        f.write(f"\n[TABLE {table_idx + 1}]\n")

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

                            f.write("| " + " | ".join(cells) + " |\n")

                            # Add separator after first row
                            if row_idx == 0:
                                separators = ["-" * col_widths[i] for i in range(num_cols)]
                                f.write("| " + " | ".join(separators) + " |\n")

                        f.write("\n")

                # Extract all text (includes non-table text and table text)
                text = page.extract_text()
                if text:
                    f.write(text.strip() + "\n\n")

    log.info("Text -> %s (with pdfplumber table extraction)", text_path)

    # ── Images (two-phase) ────────────────────────────────────────────
    img_dir = os.path.join(out_dir, "images")
    os.makedirs(img_dir, exist_ok=True)

    logo_xrefs = _recurring_logo_xrefs(doc)
    log.info("Filtered %d recurring logo xref(s)", len(logo_xrefs))

    seen_xrefs: set = set()
    n_embedded = n_rendered = 0

    for pn in range(len(doc)):
        page = doc[pn]
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
            fname = f"diagram_p{pn + 1}_{n_embedded}.{ext}"
            with open(os.path.join(img_dir, fname), "wb") as f:
                f.write(raw["image"])

            seen_xrefs.add(xref)
            n_embedded += 1
            page_had_image = True
            log.info("  Extracted: %s  (%dx%d, %.1f KB)", fname, w, h, size / 1024)

        # Phase 2 – render full page only for pure vector diagrams
        if not page_had_image and _is_vector_diagram(page):
            fname = f"page_{pn + 1}_highres.png"
            page.get_pixmap(dpi=300).save(os.path.join(img_dir, fname))
            n_rendered += 1
            log.info("  Rendered: %s", fname)

    doc.close()
    log.info("Images done — %d embedded, %d vector pages", n_embedded, n_rendered)


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
_IMG_EMBEDDED_RE = re.compile(r"^diagram_p(\d+)_\d+\.")   # diagram_p6_2.png
_IMG_RENDERED_RE = re.compile(r"^page_(\d+)_highres\.")    # page_11_highres.png


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
    """Return (page_number, image_type) or (None, None) if unrecognised."""
    m = _IMG_EMBEDDED_RE.match(fname)
    if m:
        return int(m.group(1)), "embedded"
    m = _IMG_RENDERED_RE.match(fname)
    if m:
        return int(m.group(1)), "vector_render"
    return None, None


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
                    page_num, img_type = _parse_image_filename(fname)
                    if page_num is None:
                        continue

                    rel_path = "/".join([
                        cfg["data"]["images_base_dir"],
                        source_label, pdf_stem, "images", fname,
                    ])
                    batch.add_object(properties={
                        "content":      f"[{img_type} diagram] Page {page_num} from {pdf_stem}",
                        "chunkType":    "image",
                        "sourcePdf":    pdf_stem,
                        "sourceFolder": source_label,
                        "pageNumber":   page_num,
                        "chunkIndex":   0,
                        "imageType":    img_type,
                        "imagePath":    rel_path,
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
