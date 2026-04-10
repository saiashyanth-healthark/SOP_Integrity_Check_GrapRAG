"""
validator.py — Detect broken references, orphan SOPs, concept drift, and cycles.
"""
import networkx as nx
from typing import List, Dict


def validate_graph(G: nx.DiGraph) -> Dict:
    """
    Run all validation checks. Returns a dict of issues.
    """
    return {
        "broken_refs": get_broken_refs(G),
        "orphans": get_orphans(G),
        "concept_drift": get_concept_drift(G),
        "cycles": get_cycles(G),
    }


def get_broken_refs(G: nx.DiGraph) -> List[Dict]:
    """All edges marked as broken."""
    broken = []
    for src, tgt, data in G.edges(data=True):
        if data.get("broken"):
            broken.append({
                "source_sop": src,
                "target_sop": tgt,
                "source_section": data.get("source_section", ""),
                "target_section": data.get("target_section", ""),
                "reason": data.get("break_reason", "Unknown"),
            })
    return broken


def get_orphans(G: nx.DiGraph) -> List[str]:
    """SOPs with no incoming REFERENCES edges (not referenced by anyone)."""
    real_nodes = [n for n, d in G.nodes(data=True) if d.get("type") == "SOP"]
    return [n for n in real_nodes if G.in_degree(n) == 0]


def get_concept_drift(G: nx.DiGraph) -> List[Dict]:
    """
    Detect the same term defined differently across SOPs.
    Returns list of {term, sops, definitions}.
    """
    term_map: Dict[str, List[Dict]] = {}
    for node, data in G.nodes(data=True):
        if data.get("type") != "SOP":
            continue
        for term_entry in data.get("defined_terms", []):
            term = term_entry.get("term", "").lower().strip()
            defn = term_entry.get("definition", "").strip()
            if not term or not defn:
                continue
            if term not in term_map:
                term_map[term] = []
            term_map[term].append({"sop": node, "definition": defn})

    drift = []
    for term, entries in term_map.items():
        if len(entries) > 1:
            # Check if definitions differ meaningfully
            defs = [e["definition"].lower() for e in entries]
            if len(set(defs)) > 1:
                drift.append({
                    "term": term,
                    "entries": entries,
                })
    return drift


def get_cycles(G: nx.DiGraph) -> List[List[str]]:
    """Detect circular reference chains."""
    try:
        cycles = list(nx.simple_cycles(G))
        return [c for c in cycles if len(c) >= 2]
    except Exception:
        return []
