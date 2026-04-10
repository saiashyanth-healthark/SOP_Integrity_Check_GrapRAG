"""
traversal.py — Impact analysis and subgraph retrieval for Graph RAG Q&A.
"""
import networkx as nx
from typing import Dict, List


def get_impact_subgraph(G: nx.DiGraph, sop_id: str) -> Dict:
    """
    Find all SOPs directly and indirectly affected if sop_id is modified.
    Returns dict with direct, indirect, and full subgraph data.
    """
    if sop_id not in G:
        return {"direct": [], "indirect": [], "subgraph_nodes": [], "subgraph_edges": []}

    # Direct: nodes that reference sop_id (in-edges) + nodes sop_id references (out-edges)
    direct_in = list(G.predecessors(sop_id))   # SOPs that reference this one
    direct_out = list(G.successors(sop_id))    # SOPs this one references

    # All affected = direct connections only (what the user actually sees below the graph)
    # Only count real SOP nodes, not ghost nodes
    real_nodes = set(n for n, d in G.nodes(data=True) if d.get("type") == "SOP")
    all_affected = list(set(direct_in + direct_out) & real_nodes)

    # Build subgraph
    subgraph_nodes = [sop_id] + all_affected
    sub = G.subgraph(subgraph_nodes)

    nodes_data = []
    for n in sub.nodes():
        d = G.nodes[n]
        nodes_data.append({
            "id": n,
            "title": d.get("title", n),
            "type": d.get("type", "SOP"),
            "is_selected": n == sop_id,
        })

    edges_data = []
    for src, tgt, d in sub.edges(data=True):
        edges_data.append({
            "source": src,
            "target": tgt,
            "relation": d.get("relation", ""),
            "broken": d.get("broken", False),
            "source_section": d.get("source_section", ""),
            "target_section": d.get("target_section", ""),
        })

    return {
        "direct_in": direct_in,
        "direct_out": direct_out,
        "all_affected": all_affected,
        "subgraph_nodes": nodes_data,
        "subgraph_edges": edges_data,
    }


def get_context_for_query(G: nx.DiGraph, question: str) -> str:
    """
    Build a context string from the graph for RAG Q&A.
    Extracts relevant nodes based on keywords in the question.
    """
    question_lower = question.lower()
    context_parts = []

    for node, data in G.nodes(data=True):
        if data.get("type") != "SOP":
            continue

        relevance_score = 0
        title = data.get("title", "").lower()
        sop_id_lower = node.lower()

        # Check if SOP is mentioned by ID or title keywords
        if node.lower() in question_lower or any(
            word in question_lower for word in title.split() if len(word) > 3
        ):
            relevance_score += 3

        # Check defined terms
        for term_entry in data.get("defined_terms", []):
            if term_entry.get("term", "").lower() in question_lower:
                relevance_score += 2

        # Check sections
        for section in data.get("sections", []):
            if section.get("title", "").lower() in question_lower:
                relevance_score += 1

        if relevance_score > 0:
            # Build context for this SOP
            part = f"\n--- {node}: {data.get('title', '')} ---\n"
            part += f"Version: {data.get('version', 'N/A')} | Effective: {data.get('effective_date', 'N/A')}\n"

            sections = data.get("sections", [])
            if sections:
                part += "Sections: " + ", ".join(
                    f"{s['id']} {s.get('title','')}" for s in sections[:10]
                ) + "\n"

            # Add outgoing references
            out_refs = []
            for _, tgt, edata in G.out_edges(node, data=True):
                ref_str = f"{tgt}"
                if edata.get("target_section"):
                    ref_str += f" §{edata['target_section']}"
                if edata.get("broken"):
                    ref_str += " [BROKEN]"
                out_refs.append(ref_str)
            if out_refs:
                part += "References: " + ", ".join(out_refs) + "\n"

            # Add incoming references
            in_refs = [src for src, _, _ in G.in_edges(node, data=True)]
            if in_refs:
                part += "Referenced by: " + ", ".join(in_refs) + "\n"

            context_parts.append((relevance_score, part))

    # Sort by relevance and take top 5
    context_parts.sort(key=lambda x: x[0], reverse=True)
    top_context = "\n".join(p for _, p in context_parts[:5])

    # Add graph-level summary
    real_sops = [n for n, d in G.nodes(data=True) if d.get("type") == "SOP"]
    summary = (
        f"\nSOP LIBRARY SUMMARY: {len(real_sops)} SOPs loaded: {', '.join(real_sops)}\n"
    )

    return summary + top_context if top_context else summary