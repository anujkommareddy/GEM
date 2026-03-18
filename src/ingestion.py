"""PDF ingestion and text extraction pipeline."""

import json
import logging
from pathlib import Path
from typing import Dict, Optional, List
import pdfplumber

logger = logging.getLogger(__name__)


class PDFIngester:
    """Ingest PDFs, extract text, and store with metadata."""

    def __init__(self, pdf_source: Path, output_dir: Path):
        """
        Initialize PDF ingester.

        Args:
            pdf_source: Directory containing PDFs
            output_dir: Directory to write extracted text and metadata
        """
        self.pdf_source = Path(pdf_source)
        self.output_dir = Path(output_dir)

        if not self.pdf_source.exists():
            raise FileNotFoundError(f"PDF source directory not found: {self.pdf_source}")

        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.metadata_file = self.output_dir / "metadata.jsonl"

    def ingest_all(self, skip_existing: bool = False) -> List[Dict]:
        """
        Ingest all PDFs in source directory.

        Args:
            skip_existing: If True, skip PDFs that have already been extracted

        Returns:
            List of metadata dictionaries for all ingested files
        """
        pdf_files = sorted(self.pdf_source.glob("*.pdf"))
        if not pdf_files:
            logger.warning(f"No PDF files found in {self.pdf_source}")
            return []

        logger.info(f"Found {len(pdf_files)} PDF files to ingest")

        all_metadata = []
        for i, pdf_path in enumerate(pdf_files, 1):
            logger.info(f"[{i}/{len(pdf_files)}] Ingesting {pdf_path.name}...")

            try:
                metadata = self.ingest_one(pdf_path, skip_existing=skip_existing)
                if metadata:
                    all_metadata.append(metadata)
            except Exception as e:
                logger.error(f"Failed to ingest {pdf_path.name}: {e}")

        # Write metadata file
        with open(self.metadata_file, "w") as f:
            for metadata in all_metadata:
                f.write(json.dumps(metadata) + "\n")

        logger.info(f"Ingestion complete. Processed {len(all_metadata)} files.")
        return all_metadata

    def ingest_one(self, pdf_path: Path, skip_existing: bool = False) -> Optional[Dict]:
        """
        Ingest a single PDF file.

        Args:
            pdf_path: Path to PDF file
            skip_existing: If True, skip if text file already exists

        Returns:
            Metadata dictionary or None if skipped
        """
        pdf_path = Path(pdf_path)
        text_path = self.output_dir / f"{pdf_path.stem}.txt"

        # Check if already extracted
        if skip_existing and text_path.exists():
            logger.debug(f"Skipping {pdf_path.name} (already extracted)")
            return None

        # Extract text
        try:
            text_chunks = []
            page_count = 0
            with pdfplumber.open(pdf_path) as pdf:
                page_count = len(pdf.pages)
                for page in pdf.pages:
                    text_chunks.append(page.extract_text() or "")
        except Exception as e:
            logger.error(f"PDF read error for {pdf_path.name}: {e}")
            raise

        full_text = "\n\n".join(text_chunks)

        # Write extracted text
        text_path.write_text(full_text, encoding="utf-8")

        # Extract metadata
        metadata = {
            "script_id": pdf_path.stem,
            "filename": pdf_path.name,
            "source_path": str(pdf_path),
            "extracted_text_path": str(text_path),
            "page_count": page_count,
            "text_length": len(full_text),
            "extracted_at": self._get_timestamp(),
        }

        # Try to detect title from first line
        lines = [l.strip() for l in full_text.split("\n") if l.strip()]
        if lines:
            metadata["detected_title"] = lines[0][:100]

        logger.debug(f"✓ {pdf_path.name} → {len(full_text)} characters, {page_count} pages")
        return metadata

    @staticmethod
    def _get_timestamp() -> str:
        """Get ISO timestamp."""
        from datetime import datetime

        return datetime.utcnow().isoformat()

    def load_metadata(self) -> List[Dict]:
        """Load previously ingested metadata."""
        if not self.metadata_file.exists():
            return []

        metadata = []
        with open(self.metadata_file) as f:
            for line in f:
                if line.strip():
                    metadata.append(json.loads(line))
        return metadata

    def get_script_text(self, script_id: str) -> Optional[str]:
        """Load extracted text for a script."""
        text_path = self.output_dir / f"{script_id}.txt"
        if not text_path.exists():
            return None
        return text_path.read_text(encoding="utf-8")
