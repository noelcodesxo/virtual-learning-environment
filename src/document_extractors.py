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
        reader = PdfReader(str(path))
        outline_entries = self._outline_entries(reader)
        chapter = None
        section = None
        for page_number, page in enumerate(reader.pages):
            for entry_page, title, depth in outline_entries:
                if entry_page != page_number:
                    continue
                if depth == 0:
                    chapter = title
                    section = None
                elif depth == 1:
                    section = title

            text = page.extract_text() or ""
            chunker.chunker_processer(
                text,
                chapter=chapter or f"Page {page_number + 1}",
                section=section,
            )

        if not chunker.chunks:
            raise ValueError("The PDF does not contain extractable text")

        for chunk in chunker.chunks:
            chunk["book"] = path.stem
        return chunker.chunks

    def catalog(self, path: Path) -> dict:
        reader = PdfReader(str(path))
        chapters = [title for _, title, depth in self._outline_entries(reader) if depth == 0]
        return {
            "title": path.stem,
            "chapters": list(dict.fromkeys(chapters)) or [ENTIRE_DOCUMENT_CHAPTER],
        }

    @staticmethod
    def _outline_entries(reader) -> list[tuple[int, str, int]]:
        entries = []

        def walk(nodes, depth=0):
            for node in nodes:
                if isinstance(node, list):
                    walk(node, depth + 1)
                    continue
                title = getattr(node, "title", None)
                try:
                    page_number = reader.get_destination_page_number(node)
                except Exception:
                    continue
                if title and page_number is not None and page_number >= 0:
                    entries.append((page_number, str(title), depth))

        try:
            walk(reader.outline)
        except Exception:
            return []
        return entries
