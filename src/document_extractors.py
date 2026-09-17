from pathlib import Path
import re
from typing import Protocol

from ebooklib import epub
from pypdf import PdfReader

from chunker import Chunker


ENTIRE_DOCUMENT_CHAPTER = "Entire document"
CHAPTER_TITLE_RE = re.compile(r"^\d+\.")


class DocumentExtractor(Protocol):
    extensions: frozenset[str]

    def extract_chunks(self, path: Path) -> list[dict]: ...

    def catalog(self, path: Path) -> dict: ...


class EpubExtractor:
    extensions = frozenset({".epub"})

    def extract_chunks(self, path: Path) -> list[dict]:
        book = epub.read_epub(str(path))
        return Chunker().process_book(book)

    def catalog(self, path: Path) -> dict:
        book = epub.read_epub(str(path))
        chunker = Chunker()
        chapters = [
            title
            for _, _, title, depth in chunker.flatten_toc(book.toc)
            if depth == 0 and CHAPTER_TITLE_RE.match(title)
        ]
        return {"title": chunker.book_title(book) or path.stem, "chapters": chapters}


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

    def catalog(self, path: Path) -> dict:
        return {"title": path.stem, "chapters": [ENTIRE_DOCUMENT_CHAPTER]}
