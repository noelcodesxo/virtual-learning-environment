from vle.rag.preprocessing import PreProcessor


class Retriever():
    TOP_K = 10

    def __init__(self):
        self.preprocessor = PreProcessor()

    def search(self, query: str, index: list[dict], top_k: int = TOP_K) -> list[dict]:
        terms = set(self.preprocessor.process(query).split())
        if not terms:
            return []

        scored = []
        for entry in index:
            score = sum(entry["bm25"].get(term, 0.0) for term in terms)
            if score > 0:
                scored.append({**entry, "score": score})

        scored.sort(key=lambda entry: entry["score"], reverse=True)
        return scored[:top_k]
