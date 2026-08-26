import json
import math
from pathlib import Path

class Indexer():
    def __init__(self):
        pass

    # My chunks look like this: {"text": "dfkgfjkdfg", "chapter": "x", "section": "x"}
    def index(self, chunks: list[object]) -> list[dict]:
        term_frequencies = [self._term_frequencies(chunk["text"]) for chunk in chunks]
        idf = self._inverse_document_frequencies(term_frequencies, len(chunks))

        return [
            {
                "book": chunk.get("book"),
                "chapter": chunk.get("chapter"),
                "section": chunk.get("section"),
                "text": chunk.get("text"),
                "tf_idf": {term: tf * idf[term] for term, tf in tf_map.items()},
            }
            for chunk, tf_map in zip(chunks, term_frequencies)
        ]

    def _term_frequencies(self, text: str) -> dict[str, float]:
        terms = text.split()
        if not terms:
            return {}

        counts = {}
        for term in terms:
            counts[term] = counts.get(term, 0) + 1

        return {term: count / len(terms) for term, count in counts.items()}

    # A dict's keys are already unique, so each chunk contributes at most one
    # count per term here regardless of how many times that term repeats
    # within the chunk - no extra flag needed to "stop at the first one".
    def _inverse_document_frequencies(
        self, term_frequencies: list[dict[str, float]], num_chunks: int
    ) -> dict[str, float]:
        document_frequency = {}
        for tf_map in term_frequencies:
            for term in tf_map:
                document_frequency[term] = document_frequency.get(term, 0) + 1

        return {
            term: math.log(num_chunks / df)
            for term, df in document_frequency.items()
        }

    def save(self, indexed: list[dict], path: str | Path) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(indexed, f, indent=2)