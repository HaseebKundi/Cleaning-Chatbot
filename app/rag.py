"""
Chroma + FastEmbed RAG over the cleaning business's FAQ content.
Reused as-is from the original project's rag.py pattern — only data/faq.json changes per client.
"""
import json
import os

import chromadb
from fastembed import TextEmbedding

FAQ_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "faq.json")
CHROMA_DIR = os.path.join(os.path.dirname(__file__), "..", "chroma_store")


class _FastEmbedFunction:
    """Thin adapter so FastEmbed satisfies Chroma's embedding_function interface.
    (Older chromadb versions don't ship a built-in FastEmbed wrapper, so we bring our own.)

    The model loads lazily on first use, not at import time — so the FastAPI app
    can still start (and /health respond) even before the embedding model has
    been downloaded, e.g. on a cold container with a slow first pull.
    """

    def __init__(self, model_name: str = "BAAI/bge-small-en-v1.5"):
        self._model_name = model_name
        self._model = None

    def _get_model(self):
        if self._model is None:
            self._model = TextEmbedding(model_name=self._model_name)
        return self._model

    def __call__(self, input: list[str]) -> list[list[float]]:
        return [emb.tolist() for emb in self._get_model().embed(input)]

    def name(self) -> str:
        return "fastembed"


_client = chromadb.PersistentClient(path=CHROMA_DIR)
_embed_fn = _FastEmbedFunction()
_collection = _client.get_or_create_collection(name="faq", embedding_function=_embed_fn)


def load_faq_into_chroma() -> int:
    """Rebuild the FAQ collection from data/faq.json. Call on startup or after editing the FAQ file."""
    with open(FAQ_PATH, "r") as f:
        faq_items = json.load(f)

    existing = _collection.get()
    if existing["ids"]:
        _collection.delete(ids=existing["ids"])

    ids = [f"faq-{i}" for i in range(len(faq_items))]
    documents = [f"Q: {item['question']}\nA: {item['answer']}" for item in faq_items]
    metadatas = [{"question": item["question"]} for item in faq_items]

    _collection.add(ids=ids, documents=documents, metadatas=metadatas)
    return len(faq_items)


def search_faq(query: str, n_results: int = 3) -> list[dict]:
    results = _collection.query(query_texts=[query], n_results=n_results)
    if not results["documents"] or not results["documents"][0]:
        return []

    hits = []
    for doc, dist in zip(results["documents"][0], results["distances"][0]):
        hits.append({"text": doc, "distance": dist})
    return hits
