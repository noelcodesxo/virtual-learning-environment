import math

from preprocessor import PreProcessor


class Retriever():
    TOP_K = 10

    def __init__(self):
        self.preprocessor = PreProcessor()

    def search(self, query: str, index: list[dict], top_k: int = TOP_K) -> list[dict]:
        terms = self.preprocessor.process(query).split()
        if not terms:
            return []

        query_tf = self._term_frequencies(terms)

        scored = []
        for entry in index:
            score = self._cosine_similarity(query_tf, entry["tf_idf"])
            if score > 0:
                scored.append({**entry, "score": score})

        scored.sort(key=lambda entry: entry["score"], reverse=True)
        return scored[:top_k]

    def _term_frequencies(self, terms: list[str]) -> dict[str, float]:
        counts = {}
        for term in terms:
            counts[term] = counts.get(term, 0) + 1
        return {term: count / len(terms) for term, count in counts.items()}

    def _cosine_similarity(self, vec_a: dict[str, float], vec_b: dict[str, float]) -> float:
        dot = sum(weight * vec_b.get(term, 0.0) for term, weight in vec_a.items())
        if dot == 0:
            return 0.0
        norm_a = math.sqrt(sum(weight ** 2 for weight in vec_a.values()))
        norm_b = math.sqrt(sum(weight ** 2 for weight in vec_b.values()))
        return dot / (norm_a * norm_b)
