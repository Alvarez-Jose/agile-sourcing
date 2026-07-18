import ollama

def ask(question: str, collection, top_k: int = 5, model: str = "llama3") -> str:
    results = collection.query(query_texts=[question], n_results=top_k)
    context_chunks = results["documents"][0]
    sources = results["metadatas"][0]

    context = ""
    for i, (chunk, meta) in enumerate(zip(context_chunks, sources)):
        context += f"\n[{i+1}] ({meta['policy_name']})\n{chunk}\n"

    prompt = f"""You are a UC procurement policy assistant.
Answer using ONLY the policy excerpts below. 
If the answer is not in the excerpts, say "I don't have enough information."
Do NOT make up policy details. Cite source numbers [1], [2] etc.

POLICY EXCERPTS:
{context}

QUESTION: {question}
ANSWER:"""

    response = ollama.chat(
        model=model,
        messages=[{"role": "user", "content": prompt}]
    )
    return response["message"]["content"]