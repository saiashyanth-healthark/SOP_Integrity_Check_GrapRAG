# SOP Cross-Reference Integrity Checker — Graph RAG POC

## Project Structure

```
sop_graphrag/
├── app.py                    # Main Streamlit app (run this)
├── requirements.txt
├── ingestion/
│   ├── parser.py             # PDF/DOCX → plain text
│   └── extractor.py          # Gemini API → entities + relationships JSON
├── graph/
│   ├── builder.py            # NetworkX DiGraph construction
│   ├── validator.py          # Broken refs, orphans, cycles, concept drift
│   └── traversal.py          # Impact analysis + RAG context builder
├── rag/
│   └── query.py              # Gemini-powered Graph RAG Q&A
└── viz/
    └── graph_viz.py          # Pyvis interactive graph renderer
```

## Setup

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Run the app
streamlit run app.py
```

## What to test in the UI

### Tab 1 — Upload & Process
2. Upload all 6 SOP files from SOP_POC_TestData.zip
3. Click "Run Analysis" — watch each SOP get processed
4. Check the 5-metric dashboard at the bottom

### Tab 2 — Graph View
- See the full SOP dependency graph
- Red dashed lines = broken references
- Purple nodes = orphan SOPs (QAP1702 should appear as orphan)
- Grey diamond nodes = ghost SOPs (QAP1099, QAP888, etc. — not in library)
- Hover over edges to see source/target section info
- Scroll down to see the full edge reference table

### Tab 3 — Validation Report
Expected findings from the test data:
- 5 broken references (QAP1099, QAP601§7.99, MAN0025768§9.1, QAP502rZ, QAP888)
- 1 orphan SOP (QAP1702)
- 1+ circular reference (MP709 ↔ QAP1002)
- Download the integrity report as .txt

### Tab 4 — Impact Analysis
- Select MAN0025768 → should show it affects QAP601, QAP607, QAP1002
- Select QAP1002 → should show circular dependency with MP709
- Select QAP1702 → should show 0 SOPs reference it (orphan)
- Orange node = selected SOP, Green nodes = affected SOPs

### Tab 5 — Q&A + Live Editor

#### Q&A (suggested questions to try):
- "Which SOPs depend on QAP601?"
- "What are all the broken references in the library?"
- "Which SOPs are orphans and why is that a risk?"
- "If I update MAN0025768 Section 7.4, what breaks?"
- "What does QAP607 reference?"

#### Live Editor:
1. Select any SOP (e.g. QAP607)
2. Add a new reference in the text: "refer to QAP1702 Section 3.0"
3. Click "Save & Re-Analyze"
4. Go back to Impact Analysis — QAP1702 should no longer be an orphan
5. Try removing an existing reference and see broken count change
