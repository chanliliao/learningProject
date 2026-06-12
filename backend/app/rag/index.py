"""
RAG indexing and retrieval for completed pipeline runs.

Each completed run gets its own Qdrant collection (``run_{id}``) containing one
document per ``FieldMapping`` row.  The support agent retrieves relevant context from
this collection before answering user questions.
"""

from typing import Any
from llama_index.core import VectorStoreIndex, Document
from llama_index.core.schema import NodeWithScore
from llama_index.vector_stores.qdrant import QdrantVectorStore
from llama_index.core import StorageContext


def _collection(run_id: int) -> str:
    """Return the Qdrant collection name for a given run.

    Args:
        run_id: Primary key of the ``PipelineRun``.

    Returns:
        Collection name string, e.g. ``"run_42"``.
    """
    return f"run_{run_id}"


def _get_embed_model(embed_model: Any | None = None) -> Any:
    """Return the embedding model to use for indexing and retrieval.

    Resolution order:
    1. Return ``embed_model`` if provided (used in tests and overrides).
    2. Try ``OpenAIEmbedding`` via the OpenRouter base URL when
       ``Settings.embeddings_provider == "openrouter"``.
    3. Fall back to ``FastEmbedEmbedding`` (local, no API key required).

    Args:
        embed_model: Explicit embedding model override.  ``None`` triggers
            auto-resolution.

    Returns:
        A LlamaIndex-compatible embedding model instance.
    """
    if embed_model is not None:
        return embed_model
    from app.config import get_settings
    s = get_settings()
    if s.embeddings_provider == "openrouter":
        try:
            from llama_index.embeddings.openai import OpenAIEmbedding
            return OpenAIEmbedding(
                model="text-embedding-ada-002",
                api_base=s.openrouter_base_url,
                api_key=s.openrouter_api_key,
            )
        except Exception:
            pass
    from llama_index.embeddings.fastembed import FastEmbedEmbedding
    return FastEmbedEmbedding(model_name="BAAI/bge-small-en-v1.5")


def _get_client(client: Any | None = None) -> Any:
    """Return the Qdrant client to use for vector storage.

    Args:
        client: Explicit Qdrant client override.  ``None`` creates a new client
            using the URL from ``Settings.qdrant_url``.

    Returns:
        A ``QdrantClient`` instance.
    """
    if client is not None:
        return client
    from qdrant_client import QdrantClient
    from app.config import get_settings
    s = get_settings()
    return QdrantClient(url=s.qdrant_url)


async def index_run(
    run_id: int,
    docs: list[str],
    *,
    client: Any | None = None,
    embed_model: Any | None = None,
) -> None:
    """Index a list of text documents into Qdrant for a completed run.

    Creates (or overwrites) the collection ``run_{run_id}`` and inserts one
    ``Document`` per string in ``docs``.  Each document is tagged with a
    ``run_id`` metadata key for filtering.

    Args:
        run_id: ID of the completed ``PipelineRun``.
        docs: List of plain-text strings to index (one per field mapping).
        client: Qdrant client override.  ``None`` uses ``_get_client()``.
        embed_model: Embedding model override.  ``None`` uses ``_get_embed_model()``.
    """
    qdrant = _get_client(client)
    em = _get_embed_model(embed_model)
    collection = _collection(run_id)

    vector_store = QdrantVectorStore(client=qdrant, collection_name=collection)
    storage_ctx = StorageContext.from_defaults(vector_store=vector_store)
    documents = [Document(text=d, metadata={"run_id": run_id}) for d in docs]
    VectorStoreIndex.from_documents(
        documents,
        storage_context=storage_ctx,
        embed_model=em,
        show_progress=False,
    )


def query_run(
    run_id: int,
    question: str,
    *,
    client: Any | None = None,
    embed_model: Any | None = None,
    top_k: int = 3,
) -> list[NodeWithScore]:
    """Retrieve the most relevant documents from a run's Qdrant collection.

    Used by the support agent to fetch context before answering a question.

    Args:
        run_id: ID of the completed ``PipelineRun`` to query.
        question: Natural-language question from the user.
        client: Qdrant client override.  ``None`` uses ``_get_client()``.
        embed_model: Embedding model override.  ``None`` uses ``_get_embed_model()``.
        top_k: Number of most-similar documents to return.

    Returns:
        List of up to ``top_k`` ``NodeWithScore`` objects, ordered by similarity
        (highest first).  Returns an empty list if the collection does not exist.
    """
    qdrant = _get_client(client)
    em = _get_embed_model(embed_model)
    collection = _collection(run_id)

    vector_store = QdrantVectorStore(client=qdrant, collection_name=collection)
    storage_ctx = StorageContext.from_defaults(vector_store=vector_store)
    index = VectorStoreIndex.from_vector_store(vector_store, embed_model=em, storage_context=storage_ctx)
    retriever = index.as_retriever(similarity_top_k=top_k)
    return retriever.retrieve(question)
