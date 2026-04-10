"""
app.py — SOP Cross-Reference Integrity Checker (Graph RAG)
Full POC with: Upload → Extract → Graph → Validate → Impact Analysis → Live Editor → Q&A
"""
import streamlit as st
import pandas as pd
import json
import re
import sys
import os
from dotenv import load_dotenv

# Load API key from .env file
load_dotenv()
# Load from .env locally, from Streamlit secrets in cloud
try:
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "") or st.secrets.get("GEMINI_API_KEY", "")
except Exception:
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

sys.path.insert(0, os.path.dirname(__file__))

# ── Page config ────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="SOP Integrity Checker",
    page_icon="🔬",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Custom CSS ─────────────────────────────────────────────────────────────
st.markdown("""
<style>
/* Dark theme enhancements */
.metric-card {
    background: #1E2A3A;
    border-radius: 10px;
    padding: 16px 20px;
    text-align: center;
    border: 1px solid #2E4057;
}
.metric-value { font-size: 2rem; font-weight: 700; margin: 0; }
.metric-label { font-size: 0.78rem; color: #8899AA; margin-top: 4px; }
.broken-row { background-color: rgba(231,76,60,0.15) !important; }
.valid-row  { background-color: rgba(39,174,96,0.10) !important; }
.section-header {
    font-size: 1.1rem; font-weight: 600;
    border-left: 4px solid #3498DB;
    padding-left: 10px; margin: 20px 0 10px 0;
}
.orphan-badge {
    background: #8E44AD; color: white;
    border-radius: 4px; padding: 2px 8px;
    font-size: 0.75rem; font-weight: 600;
}
.broken-badge {
    background: #E74C3C; color: white;
    border-radius: 4px; padding: 2px 8px;
    font-size: 0.75rem; font-weight: 600;
}
.ok-badge {
    background: #27AE60; color: white;
    border-radius: 4px; padding: 2px 8px;
    font-size: 0.75rem; font-weight: 600;
}
div[data-testid="stChatMessage"] { border-radius: 10px; margin-bottom: 8px; }
</style>
""", unsafe_allow_html=True)


# ── Session state init ─────────────────────────────────────────────────────
def init_state():
    defaults = {
        "graph": None,
        "entities": [],
        "chat_history": [],
        "processing_done": False,
        "raw_texts": {},
        "edited_texts": {},
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

init_state()


# ── Sidebar ────────────────────────────────────────────────────────────────
with st.sidebar:
    st.image("https://img.icons8.com/fluency/96/document.png", width=60)
    st.title("SOP Integrity Checker")
    st.caption("Graph RAG • Clinical Quality Systems")
    st.divider()

    st.divider()

    # Legend
    st.markdown("**Graph Legend**")
    st.markdown("🔵 Normal SOP")
    st.markdown("🟠 Selected SOP")
    st.markdown("🟢 Impacted SOP")
    st.markdown("🟣 Orphan SOP")
    st.markdown("⬛ Ghost (not in library)")
    st.markdown("🔴 Broken reference edge")
    st.markdown("🔵 Valid reference edge")
    st.markdown("🟣 Supersedes edge")

    st.divider()
    if st.session_state.processing_done:
        st.success(f"✅ {len(st.session_state.entities)} SOPs loaded")
        if st.button("🔄 Reset & Start Over", use_container_width=True):
            for key in ["graph", "entities", "processing_done",
                        "raw_texts", "edited_texts", "chat_history"]:
                st.session_state[key] = {} if "texts" in key else (
                    [] if key in ["entities", "chat_history"] else None
                )
                if key == "processing_done":
                    st.session_state[key] = False
            st.rerun()


# ── Main title ─────────────────────────────────────────────────────────────
st.markdown("## 🔬 SOP Cross-Reference Integrity Checker")
st.markdown("Upload your SOPs → AI builds a knowledge graph → Detects broken links, orphans, and impact chains")
st.divider()


# ════════════════════════════════════════════════════════════════════════════
# TAB LAYOUT
# ════════════════════════════════════════════════════════════════════════════
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "📤 Upload & Process",
    "🕸️ Graph View",
    "🔍 Validation Report",
    "⚡ Impact Analysis",
    "💬 Q&A + Live Editor",
])


# ════════════════════════════════════════════════════════════════════════════
# TAB 1 — UPLOAD & PROCESS
# ════════════════════════════════════════════════════════════════════════════
with tab1:
    st.markdown('<div class="section-header">Step 1 — Upload SOP Documents</div>', unsafe_allow_html=True)
    st.markdown("Upload multiple PDF or DOCX files. The AI will extract entities and build the knowledge graph.")

    uploaded_files = st.file_uploader(
        "Drop your SOP files here",
        type=["pdf", "docx"],
        accept_multiple_files=True,
        help="Upload 2 or more SOPs to see cross-reference relationships",
    )

    if uploaded_files:
        st.success(f"📁 {len(uploaded_files)} file(s) selected")
        for f in uploaded_files:
            size_kb = len(f.getvalue()) / 1024
            st.markdown(f"&nbsp;&nbsp;• **{f.name}** ({size_kb:.0f} KB)")

    st.divider()
    st.markdown('<div class="section-header">Step 2 — Extract & Build Graph</div>', unsafe_allow_html=True)

    col_btn, col_info = st.columns([1, 3])
    with col_btn:
        run_btn = st.button(
            "🚀 Run Analysis",
            type="primary",
            use_container_width=True,
            disabled=(not uploaded_files or not GEMINI_API_KEY),
        )

    with col_info:
        if not uploaded_files:
            st.info("Upload at least 2 SOP files to begin")
        else:
            st.info("Ready! Click **Run Analysis** to start.")

    if run_btn and uploaded_files and GEMINI_API_KEY:
        from ingestion.parser import extract_text
        from ingestion.extractor import extract_graph_entities
        from graph.builder import build_graph

        entities = []
        raw_texts = {}

        progress = st.progress(0, text="Starting...")
        status = st.empty()

        for i, uploaded_file in enumerate(uploaded_files):
            file_bytes = uploaded_file.getvalue()
            filename = uploaded_file.name

            # Derive SOP ID from filename - strip revision suffix like rA, rI, rN, rC, rAP
            sop_id = re.sub(r'[_\s].*$', '', filename.replace('.docx', '').replace('.pdf', ''))
            sop_id = re.sub(r'r[A-Z]+$', '', sop_id).strip()  # remove trailing rA, rI, rN, rC etc

            status.markdown(f"📄 Parsing **{filename}**...")
            try:
                text = extract_text(file_bytes, filename)
                raw_texts[sop_id] = text
            except Exception as e:
                st.error(f"Failed to parse {filename}: {e}")
                continue

            progress.progress((i * 2 + 1) / (len(uploaded_files) * 2),
                              text=f"Extracting entities from {sop_id}...")
            status.markdown(f"🤖 Gemini extracting entities from **{sop_id}**...")

            try:
                entity = extract_graph_entities(text, sop_id, GEMINI_API_KEY)
                entities.append(entity)
                status.markdown(f"✅ **{sop_id}** — found {len(entity.get('references', []))} references, "
                                f"{len(entity.get('sections', []))} sections")
            except Exception as e:
                st.error(f"Extraction failed for {sop_id}: {e}")
                continue

            progress.progress((i * 2 + 2) / (len(uploaded_files) * 2),
                              text=f"Done: {sop_id}")

        progress.progress(1.0, text="Building knowledge graph...")
        status.markdown("🕸️ Building knowledge graph...")

        G = build_graph(entities)
        st.session_state.graph = G
        st.session_state.entities = entities
        st.session_state.raw_texts = raw_texts
        st.session_state.edited_texts = {k: v for k, v in raw_texts.items()}
        st.session_state.processing_done = True
        st.session_state.chat_history = []
        # Snapshot original refs per SOP — used for accurate diff in live editor
        import re as _re
        def _is_sop(s):
            """Only include actual SOP IDs, not forms (QCF, F, E, PUR002 etc.)"""
            return bool(_re.match(r'^(QAP|MAN|MP|SOP|QCP|QSP)', s, _re.IGNORECASE))

        st.session_state.original_refs = {
            e["sop_id"]: set(
                (r.get("target_sop","").strip(), r.get("target_section","").strip())
                for r in e.get("references", [])
                if r.get("target_sop","").strip() and _is_sop(r.get("target_sop","").strip())
            )
            for e in entities
        }

        progress.empty()
        status.empty()
        st.success(f"✅ Graph built with {G.number_of_nodes()} nodes and {G.number_of_edges()} edges!")

    # Show metrics if done
    if st.session_state.processing_done and st.session_state.graph:
        from graph.builder import get_graph_metrics
        metrics = get_graph_metrics(st.session_state.graph)

        st.divider()
        st.markdown('<div class="section-header">📊 Graph Summary</div>', unsafe_allow_html=True)

        c1, c2, c3, c4, c5 = st.columns(5)
        health = metrics["health_score"]
        health_color = "#27AE60" if health >= 80 else ("#F39C12" if health >= 60 else "#E74C3C")

        with c1:
            st.markdown(f"""<div class="metric-card">
                <div class="metric-value" style="color:#3498DB">{metrics['total_sops']}</div>
                <div class="metric-label">Total SOPs</div></div>""", unsafe_allow_html=True)
        with c2:
            st.markdown(f"""<div class="metric-card">
                <div class="metric-value" style="color:#3498DB">{metrics['total_refs']}</div>
                <div class="metric-label">Total References</div></div>""", unsafe_allow_html=True)
        with c3:
            st.markdown(f"""<div class="metric-card">
                <div class="metric-value" style="color:#E74C3C">{metrics['broken_refs']}</div>
                <div class="metric-label">🔴 Broken Refs</div></div>""", unsafe_allow_html=True)
        with c4:
            st.markdown(f"""<div class="metric-card">
                <div class="metric-value" style="color:#8E44AD">{len(metrics['orphans'])}</div>
                <div class="metric-label">🟣 Orphan SOPs</div></div>""", unsafe_allow_html=True)
        with c5:
            st.markdown(f"""<div class="metric-card">
                <div class="metric-value" style="color:{health_color}">{health}%</div>
                <div class="metric-label">Health Score</div></div>""", unsafe_allow_html=True)


# ════════════════════════════════════════════════════════════════════════════
# TAB 2 — GRAPH VIEW
# ════════════════════════════════════════════════════════════════════════════
with tab2:
    if not st.session_state.processing_done:
        st.info("Upload and process SOPs in the **Upload & Process** tab first.")
    else:
        from viz.graph_viz import build_pyvis_graph
        import streamlit.components.v1 as components

        G = st.session_state.graph

        # Controls row
        ctrl_col1, ctrl_col2 = st.columns([3, 1])
        with ctrl_col1:
            st.markdown('<div class="section-header">🕸️ SOP Dependency Graph</div>', unsafe_allow_html=True)
            st.caption("Click any node or arrow to see details on the right. 🔴 Red dashed = broken. 🟣 Purple = orphan.")
        with ctrl_col2:
            show_ghosts = st.toggle("Show external refs", value=False,
                                    help="Show SOPs referenced but not in your library")

        # Single self-contained HTML — graph (75%) + detail panel (25%) inside one iframe
        html = build_pyvis_graph(G, show_ghosts=show_ghosts)
        components.html(html, height=565, scrolling=False)

        # Reference table
        st.divider()
        st.markdown('<div class="section-header">📋 All References</div>', unsafe_allow_html=True)
        rows = []
        for src, tgt, data in G.edges(data=True):
            if not show_ghosts and G.nodes.get(tgt, {}).get("type") == "GHOST":
                continue
            src_title = G.nodes.get(src, {}).get("title", "")[:35]
            tgt_title = G.nodes.get(tgt, {}).get("title", "")[:35]
            rows.append({
                "From": f"{src} — {src_title}",
                "To":   f"{tgt} — {tgt_title}",
                "From Section": data.get("source_section", ""),
                "To Section":   data.get("target_section", ""),
                "Status": "🔴 BROKEN" if data.get("broken") else "✅ Valid",
            })
        if rows:
            df = pd.DataFrame(rows)
            st.dataframe(df, use_container_width=True, hide_index=True)


# ════════════════════════════════════════════════════════════════════════════
# TAB 3 — VALIDATION REPORT
# ════════════════════════════════════════════════════════════════════════════
with tab3:
    if not st.session_state.processing_done:
        st.info("Upload and process SOPs in the **Upload & Process** tab first.")
    else:
        from graph.validator import validate_graph
        G = st.session_state.graph
        issues = validate_graph(G)

        # ── Broken References ──
        st.markdown('<div class="section-header">🔴 Broken References</div>', unsafe_allow_html=True)
        broken = issues["broken_refs"]
        if not broken:
            st.success("✅ No broken references found!")
        else:
            st.error(f"Found **{len(broken)}** broken reference(s)")
            for b in broken:
                src_title = G.nodes.get(b["source_sop"], {}).get("title", "")
                tgt_title = G.nodes.get(b["target_sop"], {}).get("title", "")
                src_label = f"{b['source_sop']} — {src_title[:35]}" if src_title else b["source_sop"]
                tgt_label = f"{b['target_sop']} — {tgt_title[:35]}" if tgt_title else b["target_sop"]
                with st.expander(
                    f"🔴 **{src_label}** → **{tgt_label}** — {b['reason']}",
                    expanded=True
                ):
                    col1, col2, col3 = st.columns(3)
                    col1.metric("Source SOP", src_label)
                    col2.metric("Target SOP", tgt_label)
                    col3.metric("Reason", b["reason"])
                    if b.get("source_section"):
                        st.caption(f"Referenced from: Section {b['source_section']}")
                    if b.get("target_section"):
                        st.caption(f"Points to: Section {b['target_section']}")

        st.divider()

        # ── Orphan SOPs ──
        st.markdown('<div class="section-header">🟣 Orphan SOPs</div>', unsafe_allow_html=True)
        orphans = issues["orphans"]
        if not orphans:
            st.success("✅ No orphan SOPs — all SOPs are referenced!")
        else:
            st.warning(f"Found **{len(orphans)}** orphan SOP(s) — not referenced by any other document")
            for o in orphans:
                node_data = G.nodes.get(o, {})
                title = node_data.get("title", "")
                st.markdown(
                    f"🟣 **{o}**{f' — {title}' if title else ''} "
                    f"<span class='orphan-badge'>ORPHAN</span>",
                    unsafe_allow_html=True
                )

        st.divider()

        # ── Circular References / Cycles ──
        st.markdown('<div class="section-header">🔄 Circular References</div>', unsafe_allow_html=True)
        cycles = issues["cycles"]
        if not cycles:
            st.success("✅ No circular references found!")
        else:
            st.warning(f"Found **{len(cycles)}** circular reference chain(s)")
            for cycle in cycles:
                def _cycle_label(sop_id):
                    t = G.nodes.get(sop_id, {}).get("title", "")
                    return f"{sop_id} ({t[:25]})" if t else sop_id
                chain = " → ".join(_cycle_label(c) for c in cycle) + f" → {_cycle_label(cycle[0])}"
                st.markdown(f"🔄 {chain}")

        st.divider()

        # ── Concept Drift ──
        st.markdown('<div class="section-header">⚠️ Concept Drift (Same Term, Different Definitions)</div>',
                    unsafe_allow_html=True)
        drift = issues["concept_drift"]
        if not drift:
            st.success("✅ No concept drift detected!")
        else:
            st.warning(f"Found **{len(drift)}** term(s) with conflicting definitions")
            for d in drift:
                with st.expander(f"⚠️ Term: **{d['term']}**"):
                    for entry in d["entries"]:
                        st.markdown(f"**{entry['sop']}:** {entry['definition']}")

        st.divider()

        # ── Export Report ──
        st.markdown('<div class="section-header">📥 Export Integrity Report</div>', unsafe_allow_html=True)

        from graph.builder import get_graph_metrics
        metrics = get_graph_metrics(G)

        report_lines = [
            "SOP INTEGRITY REPORT",
            "=" * 50,
            f"Total SOPs: {metrics['total_sops']}",
            f"Total References: {metrics['total_refs']}",
            f"Broken References: {metrics['broken_refs']}",
            f"Orphan SOPs: {len(metrics['orphans'])}",
            f"Health Score: {metrics['health_score']}%",
            "",
            "BROKEN REFERENCES:",
        ]
        for b in broken:
            src_t = G.nodes.get(b["source_sop"], {}).get("title", "")
            tgt_t = G.nodes.get(b["target_sop"], {}).get("title", "")
            report_lines.append(
                f"  {b['source_sop']} ({src_t[:30]}) → {b['target_sop']} ({tgt_t[:30]}) "
                f"§{b['target_section']} | {b['reason']}"
            )
        report_lines += ["", "ORPHAN SOPs:"]
        for o in orphans:
            t = G.nodes.get(o, {}).get("title", "")
            report_lines.append(f"  {o} — {t}")
        report_lines += ["", "CIRCULAR REFERENCES:"]
        for cycle in cycles:
            def _rl(s): t = G.nodes.get(s,{}).get("title",""); return f"{s} ({t[:20]})" if t else s
            report_lines.append("  " + " → ".join(_rl(c) for c in cycle))

        report_text = "\n".join(report_lines)
        st.download_button(
            "📥 Download Integrity Report (.txt)",
            data=report_text,
            file_name="sop_integrity_report.txt",
            mime="text/plain",
            use_container_width=True,
        )


# ════════════════════════════════════════════════════════════════════════════
# TAB 4 — IMPACT ANALYSIS
# ════════════════════════════════════════════════════════════════════════════
with tab4:
    if not st.session_state.processing_done:
        st.info("Upload and process SOPs in the **Upload & Process** tab first.")
    else:
        from graph.traversal import get_impact_subgraph
        from viz.graph_viz import build_pyvis_graph
        import streamlit.components.v1 as components

        st.markdown('<div class="section-header">⚡ Impact Analysis</div>', unsafe_allow_html=True)
        st.markdown("Select an SOP to see what gets affected if you modify or delete it.")

        G = st.session_state.graph
        real_sops = sorted([n for n, d in G.nodes(data=True) if d.get("type") == "SOP"])

        # Auto-select last edited SOP if coming from Live Editor
        last_edited = st.session_state.get("last_edited_sop", "")
        default_idx = real_sops.index(last_edited) if last_edited in real_sops else 0

        selected_sop = st.selectbox(
            "Select SOP to analyze",
            options=real_sops,
            index=default_idx,
            format_func=lambda x: (
                f"{x} — {G.nodes[x].get('title', '')[:65]}"
                if G.nodes[x].get("title") else x
            ),
        )

        # Show detailed change banner if coming from Live Editor
        if last_edited and last_edited == selected_sop:
            detail_items = st.session_state.get("last_edit_detail", [])
            if detail_items:
                sop_title = G.nodes.get(last_edited, {}).get("title", "")
                st.markdown(
                    f"**📝 Reference changes after editing "
                    f"{last_edited}" +
                    (f" — {sop_title[:50]}" if sop_title else "") + ":**",
                    unsafe_allow_html=True
                )
                for item in detail_items:
                    if item["type"] == "added":
                        st.success(f"{item['icon']} {item['text']}")
                    elif item["type"] == "added_broken":
                        st.error(f"{item['icon']} {item['text']}")
                    elif item["type"] == "removed":
                        st.warning(f"{item['icon']} {item['text']}")
                    else:
                        st.info(f"{item['icon']} {item['text']}")
                st.divider()
                # Clear after showing
                st.session_state["last_edited_sop"] = ""
                st.session_state["last_edit_detail"] = []

        if selected_sop:
            impact = get_impact_subgraph(G, selected_sop)

            # Metrics row
            # direct_in  = SOPs that reference this one → they BREAK if you modify this SOP
            # direct_out = SOPs this one depends on → NOT affected by your edit, you depend on them
            # at_risk    = direct_in only (real SOPs, not ghosts)
            real_nodes_set = set(n for n, d in G.nodes(data=True) if d.get("type") == "SOP")
            at_risk = [s for s in impact["direct_in"] if s in real_nodes_set]

            _, c1, c2, _ = st.columns([1, 2, 2, 1])
            with c1:
                st.markdown(f"""<div class="metric-card">
                    <div class="metric-value" style="color:#E74C3C">{len(at_risk)}</div>
                    <div class="metric-label">SOPs referencing this</div></div>""",
                    unsafe_allow_html=True)
            with c2:
                st.markdown(f"""<div class="metric-card">
                    <div class="metric-value" style="color:#F39C12">{len(impact['direct_out'])}</div>
                    <div class="metric-label">SOPs this references</div></div>""",
                    unsafe_allow_html=True)

            st.markdown("")

            # Impact subgraph visualization — only show relevant nodes
            all_affected_ids = impact["all_affected"]
            # filter = selected SOP + its direct connections only (no unrelated SOPs)
            impact_filter = set([selected_sop] + impact["direct_in"] + impact["direct_out"])
            sub_html = build_pyvis_graph(
                G,
                highlight_node=selected_sop,
                highlight_subgraph_nodes=all_affected_ids,
                filter_nodes=impact_filter,
            )
            components.html(sub_html, height=480, scrolling=False)

            # Details
            col_left, col_right = st.columns(2)

            with col_left:
                st.markdown("**📥 SOPs that reference this SOP (will break if you rename/delete):**")
                if impact["direct_in"]:
                    for sop in impact["direct_in"]:
                        node_data = G.nodes.get(sop, {})
                        title = node_data.get("title", "")
                        display = f"🔴 **{sop}**"
                        if title:
                            display += f" — {title}"
                        st.markdown(display)
                else:
                    st.success("No SOPs reference this one directly")

            with col_right:
                st.markdown("**📤 SOPs this SOP references:**")
                if impact["direct_out"]:
                    for sop in impact["direct_out"]:
                        node_data = G.nodes.get(sop, {})
                        title = node_data.get("title", "")
                        node_type = node_data.get("type", "SOP")
                        icon = "⬛" if node_type == "GHOST" else "🔵"
                        sec_info = ""
                        for _, tgt, edata in G.out_edges(selected_sop, data=True):
                            if tgt == sop:
                                s = edata.get("target_section", "")
                                if s:
                                    sec_info = f" §{s}"
                        display = f"{icon} **{sop}**{sec_info}"
                        if title:
                            display += f" — {title}"
                        st.markdown(display)
                else:
                    st.success("This SOP has no outgoing references")


# ════════════════════════════════════════════════════════════════════════════
# TAB 5 — Q&A + LIVE EDITOR
# ════════════════════════════════════════════════════════════════════════════
with tab5:
    if not st.session_state.processing_done:
        st.info("Upload and process SOPs in the **Upload & Process** tab first.")
    else:
        G = st.session_state.graph

        qa_tab, editor_tab = st.tabs(["💬 Graph RAG Q&A", "✏️ Live SOP Editor"])

        # ── Q&A ──────────────────────────────────────────────────────────
        with qa_tab:
            st.markdown('<div class="section-header">💬 Ask Questions About Your SOPs</div>',
                        unsafe_allow_html=True)
            st.caption("The AI answers using your SOP knowledge graph — not general knowledge.")

            # Suggested questions
            st.markdown("**💡 Try these:**")
            q_cols = st.columns(3)
            suggestions = [
                "Which SOPs depend on QAP601?",
                "What SOPs have broken references?",
                "Which SOPs are orphans?",
                "What does QAP1002 reference?",
                "List all circular dependencies",
                "What is the health score?",
            ]
            for i, q in enumerate(suggestions):
                with q_cols[i % 3]:
                    if st.button(q, key=f"sug_{i}", use_container_width=True):
                        st.session_state["prefill_q"] = q

            st.divider()

            # Display chat history
            for msg in st.session_state.chat_history:
                role = "user" if msg["role"] == "user" else "assistant"
                with st.chat_message(role):
                    st.markdown(msg["content"])

            # Chat input
            prefill = st.session_state.pop("prefill_q", "")
            user_input = st.chat_input("Ask anything about your SOP library...")

            if prefill and not user_input:
                user_input = prefill

            if user_input:
                st.session_state.chat_history.append({"role": "user", "content": user_input})
                with st.chat_message("user"):
                    st.markdown(user_input)

                with st.chat_message("assistant"):
                    with st.spinner("Searching graph and generating answer..."):
                        from rag.query import graph_rag_query
                        try:
                            answer = graph_rag_query(
                                G,
                                user_input,
                                GEMINI_API_KEY,
                            )
                        except Exception as e:
                            answer = f"❌ Error: {e}"
                    st.markdown(answer)

                st.session_state.chat_history.append({"role": "assistant", "content": answer})

            if st.session_state.chat_history:
                if st.button("🗑️ Clear Chat", key="clear_chat"):
                    st.session_state.chat_history = []
                    st.rerun()

        # ── LIVE EDITOR ───────────────────────────────────────────────────
        with editor_tab:
            st.markdown('<div class="section-header">✏️ Live SOP Editor</div>', unsafe_allow_html=True)
            st.markdown(
                "Edit an SOP's content below. Click **Save & Re-Analyze** — "
                "the graph will update and show what changed."
            )
            st.caption("ℹ️ The editor works on extracted text. After re-analysis, "
                       "check the Validation and Impact tabs to see the updated results.")

            real_sops = sorted([n for n, d in G.nodes(data=True) if d.get("type") == "SOP"])
            edit_sop = st.selectbox("Select SOP to edit", real_sops, key="editor_sop_select")

            if edit_sop:
                current_text = st.session_state.edited_texts.get(
                    edit_sop,
                    st.session_state.raw_texts.get(edit_sop, "")
                )

                edited = st.text_area(
                    f"Editing: {edit_sop}",
                    value=current_text,
                    height=380,
                    key=f"editor_{edit_sop}",
                    help="Edit the SOP text. Add or change cross-references like 'refer to QAP601 Section 6.4'",
                )

                col_save, col_reset = st.columns([2, 1])
                with col_save:
                    save_btn = st.button(
                        "💾 Save & Re-Analyze",
                        type="primary",
                        use_container_width=True,
                        key="save_reanalyze",
                    )
                with col_reset:
                    if st.button("↩️ Reset to Original", use_container_width=True, key="reset_edit"):
                        st.session_state.edited_texts[edit_sop] = \
                            st.session_state.raw_texts.get(edit_sop, "")
                        st.rerun()

                if save_btn and edited:
                    st.session_state.edited_texts[edit_sop] = edited

                    with st.spinner(f"Re-extracting entities from {edit_sop}..."):
                        from ingestion.extractor import extract_graph_entities
                        from graph.builder import build_graph

                        try:
                            # Re-extract this SOP
                            new_entity = extract_graph_entities(
                                edited, edit_sop, GEMINI_API_KEY
                            )

                            # Replace in entities list
                            updated_entities = [
                                e for e in st.session_state.entities
                                if e["sop_id"] != edit_sop
                            ]
                            updated_entities.append(new_entity)
                            st.session_state.entities = updated_entities

                            # ── Diff against ORIGINAL extraction (not graph edges) ──
                            # This avoids noise from Gemini re-extracting things slightly
                            # differently each run. We only show what YOU changed.
                            old_ref_set = st.session_state.get(
                                "original_refs", {}
                            ).get(edit_sop, set())

                            # Rebuild graph
                            new_G = build_graph(updated_entities)
                            st.session_state.graph = new_G

                            # Get new refs from new entity — SOP IDs only, not forms
                            import re as _re2
                            def _is_sop2(s):
                                return bool(_re2.match(r'^(QAP|MAN|MP|SOP|QCP|QSP)', s, _re2.IGNORECASE))
                            new_ref_set = set()
                            for ref in new_entity.get("references", []):
                                tgt = ref.get("target_sop", "").strip()
                                sec = ref.get("target_section", "").strip()
                                if tgt and _is_sop2(tgt):
                                    new_ref_set.add((tgt, sec))

                            added_refs   = new_ref_set - old_ref_set
                            removed_refs = old_ref_set - new_ref_set

                            # NOTE: original_refs snapshot is NOT updated here.
                            # It stays locked to what was extracted on first upload
                            # so the diff always shows changes relative to the original.

                            # Helper to get SOP title
                            def ref_label(tgt, sec):
                                title = new_G.nodes.get(tgt, {}).get("title", "")
                                label = f"**{tgt}**"
                                if title:
                                    label += f" — {title}"
                                if sec:
                                    label += f" §{sec}"
                                return label

                            # Build detailed change items
                            detail_items = []
                            for tgt, sec in sorted(added_refs):
                                broken = new_G.nodes.get(tgt, {}).get("type") == "GHOST"
                                icon = "🔴" if broken else "➕"
                                status = " — ⚠️ SOP not in library" if broken else ""
                                detail_items.append({
                                    "icon": icon,
                                    "text": f"Reference added → {ref_label(tgt, sec)}{status}",
                                    "type": "added_broken" if broken else "added",
                                })
                            for tgt, sec in sorted(removed_refs):
                                detail_items.append({
                                    "icon": "➖",
                                    "text": f"Reference removed → {ref_label(tgt, sec)}",
                                    "type": "removed",
                                })
                            if not detail_items:
                                detail_items.append({
                                    "icon": "↔️",
                                    "text": "No reference changes detected — content may have changed",
                                    "type": "none",
                                })

                            st.session_state["last_edit_msg"] = f"✅ **{edit_sop}** re-analyzed"
                            st.session_state["last_edited_sop"] = edit_sop
                            st.session_state["last_edit_detail"] = detail_items
                            st.session_state["show_impact_hint"] = True
                            st.rerun()

                        except Exception as e:
                            st.error(f"Re-analysis failed: {e}")

                # Show result message after rerun
                if st.session_state.get("last_edit_msg"):
                    st.success(st.session_state["last_edit_msg"])
                    st.session_state["last_edit_msg"] = ""
                if st.session_state.get("show_impact_hint"):
                    st.info("👉 Go to the **Impact Analysis** tab to see the updated graph and understand what changed.")
                    st.session_state["show_impact_hint"] = False