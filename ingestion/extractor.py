"""
extractor.py — Use Gemini to extract entities and relationships from SOP text.
Returns structured JSON ready for graph construction.
"""
import json
import re
import google.generativeai as genai


def extract_graph_entities(sop_text: str, sop_id: str, api_key: str) -> dict:
    """
    Call Gemini to extract a knowledge graph from one SOP.
    Returns a dict with: sop_id, title, sections, defined_terms,
    regulatory_refs, references, supersedes.
    """
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("gemini-2.5-flash")

    prompt = f"""You are a clinical quality system analyst. Extract a knowledge graph from this SOP document.

Return ONLY a valid JSON object — no markdown, no explanation, no backticks.

The JSON must follow this exact schema:
{{
  "sop_id": "{sop_id}",
  "title": "<full title of the SOP>",
  "version": "<revision letter or number, e.g. rC, rI, N>",
  "effective_date": "<most recent effective date if found>",
  "sections": [
    {{"id": "1.0", "title": "Purpose"}},
    {{"id": "2.0", "title": "Scope"}},
    {{"id": "3.0", "title": "Materials"}}
  ],
  "defined_terms": [
    {{"term": "<term>", "definition": "<definition>"}}
  ],
  "regulatory_refs": ["ICH E6", "21 CFR Part 11"],
  "references": [
    {{
      "target_sop": "<SOP ID like QAP601 or MAN0025768>",
      "target_section": "<section like 6.4 or empty string if not specified>",
      "target_version": "<version if mentioned, else empty string>",
      "source_section": "<which section of THIS SOP mentions this reference>"
    }}
  ],
  "supersedes": "<SOP ID this supersedes, or empty string>"
}}

Rules:
- Extract ALL cross-references to other SOPs/procedures (e.g. QAP601, MAN0025768, MP709, QAP1002)
- Include references found in "Materials, Equipment or Documents Associated" sections
- Include references found in procedure body text
- Extract all numbered sections (1.0, 1.1, 2.0, 4.2.1 etc.)
- For defined_terms, only include if there is an explicit definition, not just a mention
- regulatory_refs: include ISO standards, CFR references, EU directives etc.
- Keep arrays empty [] if nothing found, never null

SOP Content (first 6000 chars):
{sop_text[:6000]}
"""

    response = model.generate_content(prompt)
    raw = response.text.strip()

    # Strip markdown code fences if present
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        # Fallback: return minimal structure so the app doesn't crash
        data = {
            "sop_id": sop_id,
            "title": sop_id,
            "version": "",
            "effective_date": "",
            "sections": [],
            "defined_terms": [],
            "regulatory_refs": [],
            "references": [],
            "supersedes": "",
        }

    # Ensure sop_id is always set correctly
    data["sop_id"] = sop_id
    return data
