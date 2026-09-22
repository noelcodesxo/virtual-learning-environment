import argparse
import os
from pathlib import Path

from ebooklib import epub

from vle.llm.clients import build_client
from vle.rag.chunking import Chunker
from vle.rag.index_loader import load_index
from vle.rag.indexing import Indexer
from vle.rag.preprocessing import PreProcessor
from vle.rag.prompts import build_rag_messages
from vle.rag.retrieval import Retriever

RESOURCES_DIR = Path(__file__).parent / "src" / "resources"
OUTPUT_PATH = Path(__file__).parent / "index.json"
DEFAULT_MODEL = "qwen3:8b"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("query")
    parser.add_argument("-k", "--top-k", type=int, default=Retriever.TOP_K)
    parser.add_argument("--provider", choices=["ollama", "openrouter"], default="ollama")
    parser.add_argument("--model", default=os.environ.get("LLM_MODEL", DEFAULT_MODEL))
    parser.add_argument("--no-answer", action="store_true", help="Skip sending the query to the LLM")
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

    if args.no_answer:
        return

    client = build_client(args.provider, args.model)
    messages = build_rag_messages(args.query, results)
    answer = client.chat(messages)

    print("Answer:\n")
    print(answer)


if __name__ == "__main__":
    main()
