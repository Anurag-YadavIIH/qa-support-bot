# app/prompts.py
# Prompt templates for the RAG system.
#
# A "prompt template" is a reusable string with placeholders
# that get filled in at runtime with real data.
#
# Why a separate file?
# Prompts are like config — you'll want to tweak them to improve
# answer quality without touching the logic code. Keeping them
# separate makes that easy.


# ── Main QA Prompt ────────────────────────────────────────────────────
#
# This is the most important piece of the whole project.
# It tells the LLM exactly how to behave.
#
# Key techniques used:
#   1. ROLE:    "You are a support assistant" — sets persona
#   2. RULES:   Explicit "only use context" instruction — prevents hallucination
#   3. FALLBACK: Tells it what to say if context is empty — honesty over guessing
#   4. FORMAT:  Asks for sources — builds trust and verifiability
#   5. FENCING: {context} and {question} are clearly separated — no ambiguity

QA_PROMPT_TEMPLATE = """You are a helpful support assistant. Your job is to answer \
questions based ONLY on the context provided below.

STRICT RULES:
- Answer ONLY using information from the context below.
- If the context does not contain enough information to answer, say exactly:
  "I don't have enough information in my knowledge base to answer that question."
- Do NOT use your general training knowledge.
- Do NOT make up facts or guess.
- Be concise and direct.
- Always cite the source URL(s) at the end of your answer.

---
CONTEXT:
{context}
---

QUESTION: {question}

ANSWER (based only on the context above):"""


# ── Fallback message ──────────────────────────────────────────────────
# Used when no relevant chunks are retrieved at all.
# Better to tell the user clearly than to pass empty context to the LLM.

NO_CONTEXT_RESPONSE = (
    "I couldn't find any relevant information in my knowledge base "
    "to answer your question. Please try rephrasing, or ask about "
    "topics covered on the website."
)


# ── Context formatter ─────────────────────────────────────────────────
def format_context(chunks: list[dict]) -> str:
    """
    Format retrieved chunks into a clean context string for the prompt.

    Each chunk gets a numbered header and its source URL, so the LLM
    can reference specific sources in its answer.

    Input:  [{"text": "...", "url": "https://..."}, ...]
    Output: A formatted string like:
            [Source 1] https://docs.python.org/3/tutorial/
            Python lists are ordered...

            [Source 2] https://docs.python.org/3/tutorial/data.html
            You can add items with append()...
    """
    if not chunks:
        return "No relevant context found."

    parts = []
    for i, chunk in enumerate(chunks, start=1):
        url  = chunk.get("url", "Unknown source")
        text = chunk.get("text", "").strip()
        parts.append(f"[Source {i}] {url}\n{text}")

    # Join chunks with a clear separator
    return "\n\n---\n\n".join(parts)


def build_prompt(question: str, chunks: list[dict]) -> str:
    """
    Build the final prompt by filling in the template.

    Args:
        question: The user's question string
        chunks:   List of retrieved chunk dicts from ChromaDB

    Returns:
        The complete prompt string ready to send to Ollama
    """
    context = format_context(chunks)
    # .format() replaces {context} and {question} placeholders
    return QA_PROMPT_TEMPLATE.format(
        context=context,
        question=question
    )