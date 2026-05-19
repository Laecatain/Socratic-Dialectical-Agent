"""Phase 3 - Adversarial Retriever (HyDE + Score Normalization + Async Self-Evolution)

Core pipeline:
1. LLM generates HyDE hypothetical counter-example text (100-150 words)
2. Vector search on HyDE text, REMOVED hard metadata filter on type field
3. Cosine distance normalized to S_similarity = 1.0 - D_cosine
4. S_similarity gte 0.5: high-quality hit, direct route to Ironist
5. S_similarity lt 0.5: route to Web_Search + trigger async runtime cache
"""

import asyncio
import logging
import os
import uuid

from langchain_core.prompts import ChatPromptTemplate
from langchain_chroma import Chroma
from langchain_openai import ChatOpenAI, OpenAIEmbeddings

from state import DialogueState

# ---------- Config ----------
CHROMA_PERSIST_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "chroma_db"
)
COLLECTION_NAME = "socratic_social_justice"
TOP_K = 3
MAX_RUNTIME_CACHE = 20

# ---------- HyDE Prompt ----------

HYDE_SYSTEM_PROMPT = 'You are a scholar of Western political philosophy and ethics. Write a rigorous philosophical counter-argument or thought experiment based on the user claim and its classical opposing philosophy. Output only the argument core, 100-150 words, no preamble.'

HYDE_HUMAN_TEMPLATE = 'Core claim: {core_claim}\nImplicit premise: {underlying_assumption}\nOpposing philosophy: {opponent_philosophy}\nOpponent core argument: {opponent_core_argument}\nHypothetical counter-example:'

# ---------- Runtime Cache Prompt ----------

RUNTIME_CACHE_SYSTEM = 'You are a philosophical critic. Local DB and web search both missed. Generate a 120-160 word philosophical counter-argument based on the user claim and its classical opposing school. Include a concrete thought experiment or logical flaw analysis. Output only the argument text, no preamble.'

RUNTIME_CACHE_HUMAN = 'User claim: {core_claim}\nImplicit premise: {underlying_assumption}\nOpposing school: {opponent_philosophy}\nOpponent reason: {opponent_core_argument}'


# ---------- Async Write-Back ----------

async def write_back_cache_async(collection, text_id, text_content, metadata):
    """Async background vectorization and persist, non-blocking."""
    try:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None,
            lambda: collection.add(
                documents=[text_content],
                ids=[text_id],
                metadatas=[metadata],
            )
        )
        print(f"[Self-Evolution] Cached: {text_id}")
    except Exception as e:
        print(f"[Self-Evolution Error] {e}")


# ---------- Factory ----------

def make_retrieve_contradiction(
    llm: ChatOpenAI,
    embeddings: OpenAIEmbeddings,
) -> callable:
    """Build upgraded retriever node (HyDE + score norm + self-evolution)."""

    # HyDE chain
    hyde_prompt = ChatPromptTemplate.from_messages([
        ("system", HYDE_SYSTEM_PROMPT),
        ("human", HYDE_HUMAN_TEMPLATE),
    ])
    hyde_chain = hyde_prompt | llm

    # Runtime cache chain
    cache_prompt = ChatPromptTemplate.from_messages([
        ("system", RUNTIME_CACHE_SYSTEM),
        ("human", RUNTIME_CACHE_HUMAN),
    ])
    cache_chain = cache_prompt | llm

    # ChromaDB lazy load
    vector_store = None

    def _get_vector_store():
        nonlocal vector_store
        if vector_store is None:
            try:
                vector_store = Chroma(
                    persist_directory=CHROMA_PERSIST_DIR,
                    embedding_function=embeddings,
                    collection_name=COLLECTION_NAME,
                )
            except Exception as e:
                logging.error("ChromaDB connect failed: %s", e)
                raise RuntimeError(
                    "ChromaDB 连接失败，请先运行 python ingest.py 构建向量库。"
                ) from e
        return vector_store

    def _handle_miss(state):
        """Fallback when retrieval misses: generate runtime counter-example."""
        core_claim = state.get("core_claim", "")
        underlying = state.get("underlying_assumption", "")
        opponent_phil = state.get("opponent_philosophy", "")
        opponent_arg = state.get("opponent_core_argument", "")

        store = _get_vector_store()

        # Check cache limit
        try:
            count = store._collection.count()
        except Exception:
            count = 0

        if count is not None and count >= MAX_RUNTIME_CACHE:
            return dict(
                rag_counter_example="[RETRIEVER] No match, cache full.",
                rag_relevance_score=0.0,
                knowledge_source="chromadb",
            )

        # Generate runtime counter-example
        try:
            resp = cache_chain.invoke(dict(
                core_claim=core_claim,
                underlying_assumption=underlying,
                opponent_philosophy=opponent_phil,
                opponent_core_argument=opponent_arg,
            ))
            runtime_text = resp.content.strip()
        except Exception as e:
            print(f"[Runtime Cache] Generate failed: {e}")
            return dict(
                rag_counter_example="[RETRIEVER] No match, generate failed.",
                rag_relevance_score=0.0,
                knowledge_source="fallback",
            )

        # Async persist
        text_id = f"runtime_{uuid.uuid4().hex[:12]}"
        meta = dict(
            type="counter_example",
            philosophy=opponent_phil or "unknown",
            author="runtime_generator",
        )
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.create_task(write_back_cache_async(
                    store._collection, text_id, runtime_text, meta
                ))
            else:
                store._collection.add(
                    documents=[runtime_text],
                    ids=[text_id],
                    metadatas=[meta],
                )
        except Exception as e:
            print(f"[Self-Evolution] Schedule failed: {e}")

        return dict(
            rag_counter_example=(
                f"[Runtime Generated] Source: cache | ID: {text_id}\n{runtime_text}"
            ),
            rag_relevance_score=0.45,
            knowledge_source="runtime_generator",
        )

    # ---------- Node Main ----------

    def retrieve_contradiction(state: DialogueState) -> dict:
        core_claim = state.get("core_claim", "")
        if not core_claim:
            return dict(
                rag_counter_example="[RETRIEVER] No core claim extracted.",
                rag_relevance_score=0.0,
                knowledge_source="fallback",
            )

        underlying = state.get("underlying_assumption", "")
        opponent_phil = state.get("opponent_philosophy", "")
        opponent_arg = state.get("opponent_core_argument", "")

        # Step 1: HyDE generate hypothetical counter-example
        hyde_text = core_claim
        try:
            hyde_resp = hyde_chain.invoke(dict(
                core_claim=core_claim,
                underlying_assumption=underlying,
                opponent_philosophy=opponent_phil,
                opponent_core_argument=opponent_arg,
            ))
            hyde_text = hyde_resp.content.strip()
            print(f"[HyDE] Generated: {hyde_text[:80]}...")
        except Exception as e:
            print(f"[HyDE WARN] Failed ({e}), fallback to core_claim search")

        # Step 2: Vector search (NO hard metadata filter)
        store = _get_vector_store()
        try:
            results_with_scores = store.similarity_search_with_score(
                query=hyde_text,
                k=TOP_K,
            )
        except Exception as e:
            return dict(
                rag_counter_example=f"[RETRIEVER] Search failed: {e}",
                rag_relevance_score=0.0,
                knowledge_source="fallback",
            )

        if not results_with_scores:
            return _handle_miss(state)

        # Step 3: Cosine distance - normalizes to similarity score
        # S_similarity = 1.0 - D_cosine, clip to [0, 1]
        best_cosine_distance = min(score for _, score in results_with_scores)
        similarity_score = 1.0 - best_cosine_distance
        similarity_score = max(0.0, min(1.0, similarity_score))

        # Step 4: Concatenate results
        retrieved_texts = []
        for i, (doc, score) in enumerate(results_with_scores, 1):
            philosophy = doc.metadata.get("philosophy", "unknown")
            author = doc.metadata.get("author", "unknown")
            doc_type = doc.metadata.get("type", "unknown")
            retrieved_texts.append(
                f"[#{i}] School:{philosophy} | Author:{author} "
                f"| Type:{doc_type} | Dist:{score:.4f}\n{doc.page_content}"
            )

        rag_result = "\n\n---\n\n".join(retrieved_texts)
        print(
            f"[INFO] Retrieved {len(results_with_scores)} docs, "
            f"cosine_dist={best_cosine_distance:.4f}, "
            f"similarity={similarity_score:.4f}"
        )

        return dict(
            rag_counter_example=rag_result,
            rag_relevance_score=similarity_score,
            knowledge_source="chromadb",
        )

    return retrieve_contradiction
