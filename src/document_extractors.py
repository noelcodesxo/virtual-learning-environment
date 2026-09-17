from pathlib import Path
from typing import Protocol

from ebooklib import epub
from pypdf import PdfReader

from chunker import Chunker


class DocumentExtractor(Protocol):
    extensions: frozenset[str]

    def extract_chunks(self, path: Path) -> list[dict]: ...


class EpubExtractor:
    extensions = frozenset({".epub"})

    def extract_chunks(self, path: Path) -> list[dict]:
        book = epub.read_epub(str(path))
        return Chunker().process_book(book)


class PdfExtractor:
    extensions = frozenset({".pdf"})

    def extract_chunks(self, path: Path) -> list[dict]:
        chunker = Chunker()
        for page_number, page in enumerate(PdfReader(str(path)).pages, start=1):
            text = page.extract_text() or ""
            chunker.chunker_processer(text, chapter=f"Page {page_number}", section=None)

        if not chunker.chunks:
            raise ValueError("The PDF does not contain extractable text")

        for chunk in chunker.chunks:
            chunk["book"] = path.stem
        return chunker.chunks
