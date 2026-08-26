import argparse
import sys
from pathlib import Path

from ebooklib import epub

sys.path.insert(0, str(Path(__file__).parent / "src"))

from chunker import Chunker
from index_loader import load_index
from indexer import Indexer
from preprocessor import PreProcessor
from retriever import Retriever

RESOURCES_DIR = Path(__file__).parent / "src" / "resources"
OUTPUT_PATH = Path(__file__).parent / "index.json"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("query")
    parser.add_argument("-k", "--top-k", type=int, default=Retriever.TOP_K)
    args = parser.parse_args()

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

    index = load_index(OUTPUT_PATH)
    results = Retriever().search(args.query, index, top_k=args.top_k)

    print(f"\nTop {len(results)} results for {args.query!r}:\n")
    for result in results:
        print(f"[{result['score']:.4f}] {result['book']} > {result['chapter']} > {result['section']}")
        print(result["text"])
        print()


if __name__ == "__main__":
    main()
