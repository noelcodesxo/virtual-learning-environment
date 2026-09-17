from pathlib import Path
import re
from typing import Protocol

from ebooklib import epub
from pypdf import PdfReader

from chunker import Chunker


ENTIRE_DOCUMENT_CHAPTER = "Entire document"
CHAPTER_TITLE_RE = re.compile(r"^\d+\.")
CONTENTS_HEADER_RE = re.compile(r"^\s*(?:table of )?contents\s*$", re.IGNORECASE | re.MULTILINE)
TOC_CHAPTER_RE = re.compile(r"^\s*(Chapter\s+\d+\.?\s+.+?)\s+(\d+)\s*$", re.IGNORECASE | re.MULTILINE)
TOC_SECTION_RE = re.compile(r"^\s*(\d+\.\d+\.?\s+.+?)\s+(\d+)\s*$", re.MULTILINE)
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

        try:
            walk(reader.outline)
        except Exception:
            return PdfExtractor._printed_toc_entries(reader)
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
            if not TOC_CHAPTER_RE.search(text) and not TOC_SECTION_RE.search(text):
                break
            toc_pages.append(text)

        printed_page = PRINTED_PAGE_RE.search(toc_pages[0])
        page_offset = toc_start_page - int(printed_page.group(1)) if printed_page else 0
        entries = []
        for text in toc_pages:
            for title, page_number in TOC_CHAPTER_RE.findall(text):
                entries.append((int(page_number) + page_offset, title.strip(), 0))
            for title, page_number in TOC_SECTION_RE.findall(text):
                entries.append((int(page_number) + page_offset, title.strip(), 1))
        return [entry for entry in entries if 0 <= entry[0] < len(reader.pages)]
