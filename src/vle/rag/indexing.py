import json
import math
from pathlib import Path

class Indexer():
    _K1 = 1.2 # 0 - 2, 0 = no term frequency saturation, 2 = full saturation
    _B = 0.75 # 0 - 1, 0 = no length normalization, 1 = full length normalization

    def __init__(self):
        pass

    def index(self, chunks: list[object]) -> list[dict]:
        average_chunk_length = self._compute_chunk_average(chunks)
        bm25_tf: list[dict[str, float]] = [self._term_frequencies(chunk["text"], average_chunk_length) for chunk in chunks]
        bm25_idf = self._inverse_document_frequencies(bm25_tf, len(chunks))

        return [
            {
                "book": chunk.get("book"),
                "chapter": chunk.get("chapter"),
                "section": chunk.get("section"),
                "text": chunk.get("text"),
                "bm25": {term: tf * bm25_idf[term] for term, tf in tf_map.items()},
            }
            for chunk, tf_map in zip(chunks, bm25_tf)
        ]

    def _term_frequencies(self, text: str, average_chunk_length: float) -> dict[str, float]:
        terms = text.split()
        if not terms:
            return {}

        counts = {}
        for term in terms:
            counts[term] = counts.get(term, 0) + 1

        # BM25 formula: https://en.wikipedia.org/wiki/Okapi_BM25
        return {term: count * (self._K1 + 1) / (count + self._K1) * (1 - self._B + self._B * len(terms) / average_chunk_length) for term, count in counts.items()}

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

        # BM25 formula (IDF): https://en.wikipedia.org/wiki/Okapi_BM25
        return {
            term: math.log((num_chunks - df + 0.5) / (df + 0.5))
            for term, df in document_frequency.items()
        }

    def save(self, indexed: list[dict], path: str | Path) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(indexed, f, indent=2)

    def _compute_chunk_average(self, chunks: list[object]) -> float:
        total_length = sum(len(chunk["text"].split()) for chunk in chunks)
        return total_length / len(chunks) if chunks else 0
