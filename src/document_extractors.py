from pathlib import Path
import re
from typing import Protocol

from ebooklib import epub
from pypdf import PdfReader

from chunker import Chunker


ENTIRE_DOCUMENT_CHAPTER = "Entire document"
CHAPTER_TITLE_RE = re.compile(r"^\d+\.")
CONTENTS_HEADER_RE = re.compile(r"^\s*(?:table of )?contents\s*$", re.IGNORECASE | re.MULTILINE)
# A contents page is not limited to book-style "Chapter 1" headings. Research
# papers commonly use entries such as "Abstract", "1 Introduction", and
# "References". The final page number (with optional dot leaders) is the
# reliable part of those entries.
TOC_ENTRY_RE = re.compile(
    r"^\s*(?P<title>.+?)\s*(?:[.\u2026\u00b7\u2022]{2,}\s*|\s+)(?P<page>\d+)\s*$",
    re.MULTILINE,
)
NUMBERED_TOC_ENTRY_RE = re.compile(
    r"^(?:chapter\s+)?(?P<number>\d+(?:\.\d+)*)(?:\.|\))?(?:\s+|$)",
    re.IGNORECASE,
)
PRINTED_PAGE_RE = re.compile(r"^\s*(\d+)\s*$", re.MULTILINE)
MAX_TOC_SCAN_PAGES = 20
MAX_TOC_CONTINUATION_PAGES = 5


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

        for attribute in ("outline", "outlines"):
            try:
                outline = getattr(reader, attribute)
            except Exception:
                continue
            if outline is None:
                continue
            try:
                walk(outline)
            except Exception:
                # Some PDFs contain a malformed bookmark after valid entries.
                # Keep those valid entries and fall back to the printed TOC only
                # when no usable bookmark was recovered.
                pass
            if entries:
                break
        return entries or PdfExtractor._printed_toc_entries(reader)

    @staticmethod
    def _printed_toc_entries(reader) -> list[tuple[int, str, int]]:
        toc_pages = []
        toc_start_page = None
        for page_number, page in enumerate(reader.pages[:MAX_TOC_SCAN_PAGES]):
            text = page.extract_text() or ""
            if CONTENTS_HEADER_RE.search(text):
                toc_start_page = page_number
                toc_pages.append(text)
                break
        if toc_start_page is None:
            return []

        for page_number in range(toc_start_page + 1, min(
            toc_start_page + MAX_TOC_CONTINUATION_PAGES + 1,
            len(reader.pages),
        )):
            text = reader.pages[page_number].extract_text() or ""
            if not TOC_ENTRY_RE.search(text):
                break
            toc_pages.append(text)

        printed_page = PRINTED_PAGE_RE.search(toc_pages[0])
        page_offset = toc_start_page - int(printed_page.group(1)) if printed_page else 0
        entries = []
        for text in toc_pages:
            for match in TOC_ENTRY_RE.finditer(text):
                title = re.sub(r"\s+", " ", match.group("title")).strip(" .")
                if not title or CONTENTS_HEADER_RE.fullmatch(title):
                    continue
                entries.append((
                    int(match.group("page")) + page_offset,
                    title,
                    PdfExtractor._toc_entry_depth(title),
                ))
        return [entry for entry in entries if 0 <= entry[0] < len(reader.pages)]

    @staticmethod
    def _toc_entry_depth(title: str) -> int:
        """Return the hierarchy depth encoded in a printed TOC title."""
        match = NUMBERED_TOC_ENTRY_RE.match(title)
        if not match or title.lower().startswith("chapter "):
            return 0
        return match.group("number").count(".")
