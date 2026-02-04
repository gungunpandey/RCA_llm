# Data Ingestion Pipeline

PDF processing and ingestion pipeline for Weaviate vector database with OCR fallback for scanned documents.

## Features

- **Text Extraction**: pdfplumber for standard PDFs with table support
- **OCR Fallback**: Automatically switches to Tesseract OCR for scanned documents
- **Image Extraction**: Extracts diagrams and renders vector drawings
- **Text Cleanup**: Removes headers/footers, rejoins fragmented text
- **Metadata**: Includes `collectionName` from config in all ingested objects
- **Incremental Processing**: Tracks status to avoid reprocessing

## Directory Structure

```
data_ingestion/
├── pdf_processor.py      # Main processing script
├── weaviate_config.json  # Configuration file
├── .env                  # Credentials (not committed)
├── pdfs/                 # Input PDF folders
├── pdfs_pellet/
└── data/
    ├── extracted/        # Raw extracted text + images
    ├── cleaned/          # Cleaned text files
    ├── logs/             # Processing logs
    └── status_*.json     # Processing status tracking
```

## Installation

```bash
pip install pymupdf pdfplumber weaviate-client

# For OCR support (scanned documents)
pip install pdf2image pytesseract
# Also install Tesseract OCR: https://github.com/tesseract-ocr/tesseract
```

## Usage

```bash
# Run all stages
python pdf_processor.py

# Individual stages
python pdf_processor.py --extract
python pdf_processor.py --cleanup
python pdf_processor.py --ingest

# Options
python pdf_processor.py --force              # Reprocess all
python pdf_processor.py --file "doc.pdf"     # Process specific file
```

## Metadata Schema

| Field | Type | Description |
|-------|------|-------------|
| content | text | Text content (vectorized) |
| chunkType | keyword | 'text' or 'image' |
| sourcePdf | keyword | Source PDF filename |
| sourceFolder | keyword | Source folder label |
| pageNumber | int | Page number |
| chunkIndex | int | Chunk index within page |
| collectionName | keyword | Collection name from config |
| imageType | keyword | Image type (if applicable) |
| imagePath | keyword | Relative path to image |

## OCR Fallback

Automatically detects scanned documents when 10+ consecutive pages have < 50 chars of text, then switches to OCR extraction.
