"""
builder.py — Build a NetworkX DiGraph from extracted SOP entity lists.
"""
import networkx as nx
from typing import List, Dict


def build_graph(all_sop_entities: List[Dict]) -> nx.DiGraph:
    """
    Build directed graph from list of extracted SOP entity dicts.
    
    Node types: SOP
    Edge types: REFERENCES, SUPERSEDES
    """
    G = nx.DiGraph()

    # First pass: add all SOP nodes
    for sop in all_sop_entities:
        sop_id = sop["sop_id"]
        G.add_node(
            sop_id,
            type="SOP",
            title=sop.get("title", sop_id),
            version=sop.get("version", ""),
            effective_date=sop.get("effective_date", ""),
            sections=sop.get("sections", []),
            defined_terms=sop.get("defined_terms", []),
            regulatory_refs=sop.get("regulatory_refs", []),
        )

    # Second pass: add edges
    known_sops = set(G.nodes())

    for sop in all_sop_entities:
        sop_id = sop["sop_id"]

        # REFERENCES edges
        for ref in sop.get("references", []):
            target = ref.get("target_sop", "").strip()
            if not target:
                continue

            # Check if target exists
            target_exists = target in known_sops
            target_section = ref.get("target_section", "")
            target_version = ref.get("target_version", "")
            source_section = ref.get("source_section", "")

            # Validate section exists in target node
            section_valid = True
            if target_exists and target_section:
                target_node = G.nodes[target]
                target_sections = [s["id"] for s in target_node.get("sections", [])]
                if target_sections and target_section not in target_sections:
                    section_valid = False

            # If target SOP not in graph, add as ghost node
            if not target_exists:
                G.add_node(target, type="GHOST", title=f"{target} (not in library)")

            G.add_edge(
                sop_id,
                target,
                relation="REFERENCES",
                source_section=source_section,
                target_section=target_section,
                target_version=target_version,
                broken=not target_exists or not section_valid,
                break_reason=(
                    "SOP not found in library" if not target_exists
                    else ("Section not found" if not section_valid else "")
                ),
            )

        # SUPERSEDES edges
        supersedes = sop.get("supersedes", "").strip()
        if supersedes and supersedes in known_sops:
            G.add_edge(sop_id, supersedes, relation="SUPERSEDES", broken=False, break_reason="")

    return G


def get_graph_metrics(G: nx.DiGraph) -> Dict:
    """Compute summary metrics for the dashboard."""
    all_edges = list(G.edges(data=True))
    ref_edges = [e for e in all_edges if e[2].get("relation") == "REFERENCES"]
    broken_edges = [e for e in ref_edges if e[2].get("broken")]

    # Orphan = real SOP node with no incoming edges
    real_nodes = [n for n, d in G.nodes(data=True) if d.get("type") == "SOP"]
    orphans = [n for n in real_nodes if G.in_degree(n) == 0]

    # Health score
    total_refs = len(ref_edges)
    broken_count = len(broken_edges)
    health = round((1 - broken_count / total_refs) * 100) if total_refs > 0 else 100

    return {
        "total_sops": len(real_nodes),
        "total_refs": total_refs,
        "broken_refs": broken_count,
        "orphans": orphans,
        "health_score": health,
    }
