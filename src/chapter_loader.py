import re
from pathlib import Path

from ebooklib import epub

from chunker import Chunker

CHAPTER_TITLE_RE = re.compile(r"^\d+\.")


class ChapterLoader:
    """Loads full, clean chapter text straight from an epub's own TOC -
    no chunking, no BM25, no stopword stripping. Used by the exam builder,
    which needs whole-chapter context rather than search-ranked snippets."""

    def __init__(self, resources_dir: Path):
        self.resources_dir = Path(resources_dir)
        self._chunker = Chunker()

    def list_books(self) -> list[dict]:
        return [
            {"title": self._chunker.book_title(book), "chapters": self._chapter_titles(book)}
            for book in (epub.read_epub(str(path)) for path in self._epub_paths())
        ]

    def load_chapter_text(self, book_title: str, chapter_title: str) -> str:
        for path in self._epub_paths():
            book = epub.read_epub(str(path))
            if self._chunker.book_title(book) != book_title:
                continue

            texts = [text for text, chapter, _ in self._chunker.context_rewrite(book) if chapter == chapter_title]
            if not texts:
                raise ValueError(f"Chapter {chapter_title!r} not found in {book_title!r}")
            return "\n\n".join(texts)

        raise ValueError(f"Book {book_title!r} not found")

    def _epub_paths(self) -> list[Path]:
        return sorted(self.resources_dir.glob("*.epub"))

    def _chapter_titles(self, book: epub.EpubBook) -> list[str]:
        flat = self._chunker.flatten_toc(book.toc)
        return [title for _, _, title, depth in flat if depth == 0 and CHAPTER_TITLE_RE.match(title)]
