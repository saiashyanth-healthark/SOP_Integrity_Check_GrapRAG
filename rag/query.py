"""
query.py — Graph-grounded Q&A using Gemini.
Takes a question, retrieves relevant subgraph context, then answers with citations.
"""
import google.generativeai as genai
import networkx as nx


def graph_rag_query(G: nx.DiGraph, question: str, api_key: str, chat_history: list = None) -> str:
    """
    Retrieve relevant subgraph context → send to Gemini → return grounded answer.
    chat_history: list of {"role": "user"/"model", "parts": [text]} for multi-turn.
    """
    from graph.traversal import get_context_for_query

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("gemini-2.5-flash")

    # Build graph context
    context = get_context_for_query(G, question)

    system_prompt = f"""You are an expert SOP compliance analyst for a clinical research organization.
You have access to the organization's SOP knowledge graph. Answer questions accurately and cite specific SOP IDs and sections.

IMPORTANT RULES:
- Always cite which SOP and section your answer comes from
- If a reference is marked [BROKEN], flag it clearly
- If you cannot find the answer in the graph context, say so explicitly
- Be concise but thorough
- Use bullet points for multi-part answers

SOP KNOWLEDGE GRAPH CONTEXT:
{context}
"""

    # Build messages for Gemini
    history = chat_history or []

    # For multi-turn, use chat
    if history:
        chat = model.start_chat(history=history)
        full_prompt = f"{system_prompt}\n\nUser question: {question}"
        response = chat.send_message(full_prompt)
    else:
        full_prompt = f"{system_prompt}\n\nUser question: {question}"
        response = model.generate_content(full_prompt)

    return response.text
