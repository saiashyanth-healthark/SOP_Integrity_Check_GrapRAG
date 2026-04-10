"""
graph_viz.py — Full self-contained graph + detail panel in one HTML.
Graph on left (75%), detail panel on right (25%) — all inside one iframe.
Click events handled entirely within the HTML — no cross-iframe comms needed.
"""
import networkx as nx
from pyvis.network import Network
import tempfile, os, json


def build_pyvis_graph(
    G: nx.DiGraph,
    highlight_node: str = None,
    highlight_subgraph_nodes: list = None,
    show_ghosts: bool = False,
    filter_nodes: set = None,
) -> str:
    """
    filter_nodes: if provided, only render nodes in this set (used for impact subgraph).
    """

    highlight_set = set(highlight_subgraph_nodes or [])

    # ── Build node data dict ───────────────────────────────────────────────
    nodes_data = {}
    for node, data in G.nodes(data=True):
        node_type  = data.get("type", "SOP")
        if node_type == "GHOST" and not show_ghosts:
            continue
        # Impact subgraph filter — only show relevant nodes
        if filter_nodes is not None and node not in filter_nodes:
            continue
        title_text = data.get("title", node)
        in_deg     = G.in_degree(node)
        out_deg    = G.out_degree(node)
        has_broken = any(d.get("broken") for _, _, d in G.out_edges(node, data=True))
        is_orphan  = in_deg == 0 and node_type == "SOP"

        nodes_data[node] = {
            "id": node,
            "title": title_text,
            "node_type": node_type,
            "version": data.get("version", ""),
            "effective_date": data.get("effective_date", ""),
            "sections": data.get("sections", [])[:15],
            "regulatory_refs": data.get("regulatory_refs", []),
            "in_degree": in_deg,
            "out_degree": out_deg,
            "is_orphan": is_orphan,
            "has_broken": has_broken,
            "refs_out": [
                {
                    "target": tgt,
                    "target_title": G.nodes.get(tgt, {}).get("title", tgt),
                    "broken": d.get("broken", False),
                    "src_sec": d.get("source_section", ""),
                    "tgt_sec": d.get("target_section", ""),
                    "reason": d.get("break_reason", ""),
                }
                for _, tgt, d in G.out_edges(node, data=True)
            ],
            "refs_in": [
                {
                    "source": src,
                    "source_title": G.nodes.get(src, {}).get("title", src),
                    "src_sec": d.get("source_section", ""),
                    "tgt_sec": d.get("target_section", ""),
                }
                for src, _, d in G.in_edges(node, data=True)
            ],
        }

    # ── Build edge data dict ───────────────────────────────────────────────
    edges_data = {}
    for src, tgt, data in G.edges(data=True):
        if not show_ghosts:
            if G.nodes.get(src, {}).get("type") == "GHOST": continue
            if G.nodes.get(tgt, {}).get("type") == "GHOST": continue
        key = f"{src}||{tgt}"
        edges_data[key] = {
            "source": src,
            "source_title": G.nodes.get(src, {}).get("title", src),
            "target": tgt,
            "target_title": G.nodes.get(tgt, {}).get("title", tgt),
            "relation": data.get("relation", "REFERENCES"),
            "broken": data.get("broken", False),
            "src_sec": data.get("source_section", ""),
            "tgt_sec": data.get("target_section", ""),
            "reason": data.get("break_reason", ""),
        }

    # ── Build Pyvis network ────────────────────────────────────────────────
    net = Network(
        height="560px",
        width="100%",
        directed=True,
        bgcolor="#0E1117",
        font_color="#FFFFFF",
    )
    net.set_options("""
    {
      "physics": {
        "enabled": true,
        "barnesHut": {
          "gravitationalConstant": -5000,
          "centralGravity": 0.15,
          "springLength": 220,
          "springConstant": 0.03,
          "damping": 0.2
        },
        "stabilization": {"iterations": 200, "fit": true}
      },
      "edges": {
        "arrows": {"to": {"enabled": true, "scaleFactor": 0.8}},
        "smooth": {"type": "curvedCW", "roundness": 0.2},
        "font": {"size": 9, "color": "#CCCCCC", "strokeWidth": 2,
                 "strokeColor": "#0E1117", "align": "top"}
      },
      "nodes": {
        "font": {"size": 13, "color": "#FFFFFF", "bold": true},
        "borderWidth": 2,
        "shadow": {"enabled": true, "size": 6}
      },
      "interaction": {
        "hover": true,
        "tooltipDelay": 50,
        "navigationButtons": false,
        "keyboard": false,
        "selectConnectedEdges": true
      }
    }
    """)

    for node, d in nodes_data.items():
        node_type  = d["node_type"]
        title_text = d["title"]
        in_deg     = d["in_degree"]
        short      = (title_text[:20] + "…") if len(title_text) > 20 else title_text

        if node_type == "GHOST":
            label = f"⬛ {node}\n(not in library)"
            color, shape, size, border = "#555555", "diamond", 16, "#888888"
        else:
            icons = ""
            if d["has_broken"]: icons += "🔴 "
            if d["is_orphan"]:  icons += "🟡 "
            label = f"{icons}{short}\n({node})"
            if node == highlight_node:
                color, shape, size, border = "#F5A623", "ellipse", 35, "#FF8C00"
            elif node in highlight_set:
                color, shape, size, border = "#27AE60", "ellipse", 28, "#1E8449"
            elif d["is_orphan"]:
                color, shape, size, border = "#8E44AD", "ellipse", 26, "#6C3483"
            else:
                color, shape, size, border = "#2980B9", "ellipse", 26, "#1A5276"

        net.add_node(
            node, label=label,
            title="Click for details",
            color={"background": color, "border": border,
                   "highlight": {"background": "#F39C12", "border": "#E67E22"},
                   "hover":     {"background": "#5DADE2", "border": "#2E86C1"}},
            shape=shape, size=size,
        )

    for key, d in edges_data.items():
        src, tgt = d["source"], d["target"]
        # Skip edges where either endpoint is not in the filter set
        if filter_nodes is not None and (src not in filter_nodes or tgt not in filter_nodes):
            continue
        if d["broken"]:
            color, width, dashes = "#E74C3C", 3, True
        elif d["relation"] == "SUPERSEDES":
            color, width, dashes = "#9B59B6", 2, False
        else:
            color, width, dashes = "#3498DB", 2, False
        # Build edge label from section numbers
        src_sec = d.get("src_sec", "")
        tgt_sec = d.get("tgt_sec", "")
        if src_sec and tgt_sec:
            edge_label = f"§{src_sec}→§{tgt_sec}"
        elif tgt_sec:
            edge_label = f"§{tgt_sec}"
        elif src_sec:
            edge_label = f"§{src_sec}"
        else:
            edge_label = ""

        net.add_edge(src, tgt, title="Click for details",
                     label=edge_label,
                     color=color, width=width, dashes=dashes,
                     font={"size": 9, "color": "#CCCCCC",
                           "strokeWidth": 2, "strokeColor": "#0E1117",
                           "align": "top"})

    # Generate pyvis HTML
    with tempfile.NamedTemporaryFile(suffix=".html", delete=False, mode="w") as f:
        tmp_path = f.name
    net.save_graph(tmp_path)
    with open(tmp_path, "r", encoding="utf-8") as f:
        pyvis_html = f.read()
    os.unlink(tmp_path)

    # Extract just the body content and scripts from pyvis HTML
    import re
    body_match = re.search(r'<body[^>]*>(.*?)</body>', pyvis_html, re.DOTALL)
    body_content = body_match.group(1) if body_match else pyvis_html
    head_scripts = re.findall(r'<script[^>]*>.*?</script>', pyvis_html, re.DOTALL)
    head_styles  = re.findall(r'<style[^>]*>.*?</style>',  pyvis_html, re.DOTALL)

    nodes_json = json.dumps(nodes_data)
    edges_json = json.dumps(edges_data)

    # ── Full self-contained HTML with 75/25 layout ─────────────────────────
    full_html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8"/>
{''.join(head_styles)}
{''.join(head_scripts)}
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ background: #0E1117; color: #FFFFFF; font-family: Arial, sans-serif; overflow: hidden; }}
  #container {{ display: flex; width: 100%; height: 560px; }}
  #graph-area {{ width: 75%; height: 560px; position: relative; }}
  #mynetwork {{ width: 100%; height: 560px; background: #0E1117; border: none; }}
  #detail-panel {{
    width: 25%; height: 560px; background: #1A1F2E;
    border-left: 2px solid #2E4057; padding: 12px;
    overflow-y: auto; font-size: 13px;
  }}
  #detail-panel h3 {{ color: #5DADE2; margin-bottom: 10px; font-size: 15px; }}
  .detail-hint {{ color: #8899AA; text-align: center; padding: 30px 10px; line-height: 1.6; }}
  .detail-hint span {{ font-size: 28px; display: block; margin-bottom: 8px; }}
  .badge {{ display: inline-block; padding: 2px 8px; border-radius: 4px;
            font-size: 11px; font-weight: bold; margin-bottom: 6px; }}
  .badge-ok     {{ background: #27AE60; color: white; }}
  .badge-broken {{ background: #E74C3C; color: white; }}
  .badge-orphan {{ background: #8E44AD; color: white; }}
  .badge-ghost  {{ background: #555; color: #ccc; }}
  .sop-title {{ font-size: 13px; font-weight: bold; color: #FFFFFF; margin: 4px 0; }}
  .sop-sub   {{ font-size: 11px; color: #8899AA; margin-bottom: 8px; }}
  .divider   {{ border-top: 1px solid #2E4057; margin: 8px 0; }}
  .ref-item  {{ padding: 4px 0; border-bottom: 1px solid #1E2A3A; }}
  .ref-id    {{ font-weight: bold; font-size: 12px; }}
  .ref-name  {{ font-size: 11px; color: #8899AA; }}
  .ref-sec   {{ font-size: 11px; color: #5DADE2; }}
  .ref-broken{{ color: #E74C3C; font-size: 11px; }}
  .section-label {{ font-size: 12px; font-weight: bold; color: #5DADE2;
                    margin: 8px 0 4px 0; }}
  .sec-item  {{ font-size: 11px; color: #AABBCC; padding: 1px 0; }}
  .edge-from {{ background: #1E2A3A; padding: 6px 8px; border-radius: 4px; margin: 4px 0; }}
  .edge-label{{ font-size: 11px; color: #8899AA; }}
  .edge-val  {{ font-size: 13px; font-weight: bold; color: #FFFFFF; }}
</style>
</head>
<body>
<div id="container">
  <div id="graph-area">
    {body_content}
  </div>
  <div id="detail-panel">
    <h3>🔍 Details</h3>
    <div id="detail-content">
      <div class="detail-hint">
        <span>👆</span>
        Click any <b>node</b> or <b>arrow</b> in the graph to see details here.
      </div>
    </div>
  </div>
</div>

<script>
var NODE_DATA = {nodes_json};
var EDGE_DATA = {edges_json};

function esc(s) {{
  if (!s) return '';
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}}

function showNodeDetail(nodeId) {{
  var d = NODE_DATA[nodeId];
  if (!d) {{ showClear(); return; }}

  var html = '';

  // Badge + title
  if (d.node_type === 'GHOST') {{
    html += '<span class="badge badge-ghost">NOT IN LIBRARY</span>';
    html += '<div class="sop-title">⬛ ' + esc(nodeId) + '</div>';
    html += '<div class="sop-sub">This SOP is referenced but not uploaded.</div>';
  }} else if (d.is_orphan) {{
    html += '<span class="badge badge-orphan">ORPHAN</span>';
    html += '<div class="sop-title">🟡 ' + esc(nodeId) + '</div>';
    html += '<div class="sop-sub">' + esc(d.title) + '</div>';
    html += '<div class="sop-sub">Nothing references this SOP.</div>';
  }} else if (d.has_broken) {{
    html += '<span class="badge badge-broken">HAS BROKEN REFS</span>';
    html += '<div class="sop-title">🔴 ' + esc(nodeId) + '</div>';
    html += '<div class="sop-sub">' + esc(d.title) + '</div>';
  }} else {{
    html += '<span class="badge badge-ok">VALID</span>';
    html += '<div class="sop-title">🔵 ' + esc(nodeId) + '</div>';
    html += '<div class="sop-sub">' + esc(d.title) + '</div>';
  }}

  if (d.version) html += '<div class="sop-sub">Version: ' + esc(d.version) + '</div>';
  if (d.effective_date) html += '<div class="sop-sub">Effective: ' + esc(d.effective_date) + '</div>';

  html += '<div class="divider"></div>';

  // Outgoing refs
  if (d.refs_out && d.refs_out.length > 0) {{
    html += '<div class="section-label">📤 References (' + d.refs_out.length + ')</div>';
    d.refs_out.forEach(function(r) {{
      var icon = r.broken ? '🔴' : '✅';
      html += '<div class="ref-item">';
      html += '<div class="ref-id">' + icon + ' ' + esc(r.target) + (r.tgt_sec ? ' <span class="ref-sec">§' + esc(r.tgt_sec) + '</span>' : '') + '</div>';
      html += '<div class="ref-name">' + esc((r.target_title||'').substring(0,40)) + '</div>';
      if (r.broken && r.reason) html += '<div class="ref-broken">⚠️ ' + esc(r.reason) + '</div>';
      html += '</div>';
    }});
    html += '<div class="divider"></div>';
  }}

  // Incoming refs
  if (d.refs_in && d.refs_in.length > 0) {{
    html += '<div class="section-label">📥 Referenced by (' + d.refs_in.length + ')</div>';
    d.refs_in.forEach(function(r) {{
      html += '<div class="ref-item">';
      html += '<div class="ref-id">🔵 ' + esc(r.source) + (r.src_sec ? ' <span class="ref-sec">§' + esc(r.src_sec) + '</span>' : '') + '</div>';
      html += '<div class="ref-name">' + esc((r.source_title||'').substring(0,40)) + '</div>';
      html += '</div>';
    }});
    html += '<div class="divider"></div>';
  }} else if (d.node_type === 'SOP') {{
    html += '<div class="section-label">📥 Referenced by</div>';
    html += '<div class="sop-sub">Nothing references this SOP.</div>';
    html += '<div class="divider"></div>';
  }}

  // Sections
  if (d.sections && d.sections.length > 0) {{
    html += '<div class="section-label">📑 Sections</div>';
    var shown = d.sections.slice(0,8);
    shown.forEach(function(s) {{
      html += '<div class="sec-item">' + esc(s.id||'') + ' — ' + esc(s.title||'') + '</div>';
    }});
    if (d.sections.length > 8) html += '<div class="sec-item">... +' + (d.sections.length-8) + ' more</div>';
  }}

  document.getElementById('detail-content').innerHTML = html;
}}

function showEdgeDetail(key) {{
  var d = EDGE_DATA[key];
  if (!d) {{ showClear(); return; }}

  var html = '';
  if (d.broken) {{
    html += '<span class="badge badge-broken">BROKEN REFERENCE</span>';
  }} else {{
    html += '<span class="badge badge-ok">VALID REFERENCE</span>';
  }}

  html += '<div class="divider"></div>';
  html += '<div class="edge-label">FROM</div>';
  html += '<div class="edge-from">';
  html += '<div class="edge-val">' + esc(d.source) + (d.src_sec ? ' §' + esc(d.src_sec) : '') + '</div>';
  html += '<div class="ref-name">' + esc((d.source_title||'').substring(0,45)) + '</div>';
  html += '</div>';

  html += '<div style="text-align:center;color:#5DADE2;font-size:18px;margin:4px 0;">↓</div>';

  html += '<div class="edge-label">TO</div>';
  html += '<div class="edge-from">';
  html += '<div class="edge-val">' + esc(d.target) + (d.tgt_sec ? ' §' + esc(d.tgt_sec) : '') + '</div>';
  html += '<div class="ref-name">' + esc((d.target_title||'').substring(0,45)) + '</div>';
  html += '</div>';

  if (d.broken && d.reason) {{
    html += '<div class="divider"></div>';
    html += '<div class="section-label" style="color:#E74C3C;">⚠️ Reason</div>';
    html += '<div style="color:#E74C3C;font-size:12px;padding:4px 0;">' + esc(d.reason) + '</div>';
  }}

  if (d.relation === 'SUPERSEDES') {{
    html += '<div class="divider"></div>';
    html += '<div class="sop-sub">This SOP supersedes the target.</div>';
  }}

  document.getElementById('detail-content').innerHTML = html;
}}

function showClear() {{
  document.getElementById('detail-content').innerHTML = '<div class="detail-hint"><span>👆</span>Click any <b>node</b> or <b>arrow</b> to see details here.</div>';
}}

function attachHandlers() {{
  if (typeof network === 'undefined') {{ setTimeout(attachHandlers, 400); return; }}

  network.on('click', function(params) {{
    if (params.nodes.length > 0) {{
      showNodeDetail(params.nodes[0]);
    }} else if (params.edges.length > 0) {{
      var edgeId = params.edges[0];
      var edge   = network.body.data.edges.get(edgeId);
      var key    = edge.from + '||' + edge.to;
      showEdgeDetail(key);
    }} else {{
      showClear();
    }}
  }});
}}
attachHandlers();
</script>
</body>
</html>"""

    return full_html