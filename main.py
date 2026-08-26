import sys
from pathlib import Path

from ebooklib import epub

sys.path.insert(0, str(Path(__file__).parent / "src"))

from chunker import Chunker
from indexer import Indexer
from preprocessor import PreProcessor

RESOURCES_DIR = Path(__file__).parent / "src" / "resources"
OUTPUT_PATH = Path(__file__).parent / "index.json"


def main():
    epub_paths = sorted(RESOURCES_DIR.glob("*.epub"))
    books = [epub.read_epub(str(path)) for path in epub_paths]

    chunker = Chunker()
    chunks = [chunk for book_chunks in chunker.process_books(books) for chunk in book_chunks]

    preprocessor = PreProcessor()
    for chunk in chunks:
        chunk["text"] = preprocessor.process(chunk["text"])

    indexer = Indexer()
    indexed = indexer.index(chunks)
    indexer.save(indexed, OUTPUT_PATH)

    print(f"Indexed {len(chunks)} chunks from {len(books)} books -> {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
