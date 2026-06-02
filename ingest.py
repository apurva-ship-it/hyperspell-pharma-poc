"""
Ingest pharma brand intelligence docs into a Hyperspell memory layer.

Usage:
    pip install hyperspell python-dotenv langfuse
    export HYPERSPELL_API_KEY="your_key_here"

    # Ingest all brands (Nexorel + 10 real brands)
    python ingest.py

    # Ingest a specific brand
    python ingest.py --brand keytruda

    # Ingest then run a test query
    python ingest.py --brand ozempic --query "What CV outcomes data does Ozempic have?"

    # Query only (skip ingestion)
    python ingest.py --query-only "How does Tagrisso compare to Lazertinib?" --brand tagrisso
"""

import argparse
import atexit
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from hyperspell import Hyperspell
from langfuse import get_client, observe

load_dotenv()

DOCS_DIR = Path(__file__).parent

langfuse = get_client()
atexit.register(langfuse.flush)

# Nexorel fictional brand — multi-file setup
NEXOREL_DOCS = {
    "brand_plan_2026.md":         {"title": "Nexorel Annual Brand Plan 2026",           "doc_type": "brand_plan"},
    "competitive_intelligence.md":{"title": "Nexorel Competitive Intelligence Report",  "doc_type": "competitive_intelligence"},
    "key_messages.md":            {"title": "Nexorel MLR-Approved Key Messages",         "doc_type": "key_messages"},
    "patient_journey.md":         {"title": "EGFR+ NSCLC Patient Journey Map",          "doc_type": "patient_journey"},
    "hcp_segmentation.md":        {"title": "Nexorel HCP Segmentation & Targeting Guide","doc_type": "hcp_segmentation"},
    "medical_affairs_strategy.md":{"title": "Nexorel Medical Affairs Strategy",          "doc_type": "medical_affairs"},
    "market_research_insights.md":{"title": "Nexorel Market Research & Brand Tracker",  "doc_type": "market_research"},
    "field_force_briefing.md":    {"title": "Nexorel Q2 2026 Field Force Briefing",     "doc_type": "field_briefing"},
}

# Real brands — single comprehensive file per brand
REAL_BRANDS = {
    "keytruda":  {"title": "Keytruda (pembrolizumab) Brand Intelligence",   "company": "Merck",               "ta": "oncology"},
    "humira":    {"title": "Humira (adalimumab) Brand Intelligence",        "company": "AbbVie",              "ta": "immunology"},
    "ozempic":   {"title": "Ozempic (semaglutide) Brand Intelligence",      "company": "Novo Nordisk",        "ta": "diabetes"},
    "eliquis":   {"title": "Eliquis (apixaban) Brand Intelligence",         "company": "BMS/Pfizer",          "ta": "cardiology"},
    "dupixent":  {"title": "Dupixent (dupilumab) Brand Intelligence",       "company": "Sanofi/Regeneron",    "ta": "dermatology"},
    "tagrisso":  {"title": "Tagrisso (osimertinib) Brand Intelligence",     "company": "AstraZeneca",         "ta": "oncology"},
    "entresto":  {"title": "Entresto (sacubitril/valsartan) Brand Intelligence","company": "Novartis",        "ta": "cardiology"},
    "skyrizi":   {"title": "Skyrizi (risankizumab) Brand Intelligence",     "company": "AbbVie",              "ta": "dermatology"},
    "ibrance":   {"title": "Ibrance (palbociclib) Brand Intelligence",      "company": "Pfizer",              "ta": "oncology"},
    "jardiance": {"title": "Jardiance (empagliflozin) Brand Intelligence",  "company": "Boehringer Ingelheim","ta": "diabetes"},
}


@observe(name="cli-ingest-nexorel", capture_input=False, capture_output=False)
def ingest_nexorel(client: Hyperspell):
    items = []
    for filename, meta in NEXOREL_DOCS.items():
        path = DOCS_DIR / filename
        if not path.exists():
            print(f"  WARNING: {filename} not found, skipping")
            continue
        items.append({
            "text": path.read_text(encoding="utf-8"),
            "title": meta["title"],
            "metadata": {**meta, "brand": "nexorel", "therapeutic_area": "oncology"},
        })
    if not items:
        print("  No Nexorel docs found.")
        langfuse.update_current_trace(
            input={"brand": "nexorel"},
            output={"count": 0},
            tags=["brand:nexorel", "ingest", "cli"],
            metadata={"reason": "no docs found"},
        )
        return

    titles = [item["title"] for item in items]
    langfuse.update_current_trace(
        input={"brand": "nexorel", "item_count": len(items), "titles": titles},
        tags=["brand:nexorel", "ingest", "cli"],
    )

    with langfuse.start_as_current_observation(
        as_type="span",
        name="hyperspell.memories.add_bulk",
        input={"brand": "nexorel", "titles": titles, "item_count": len(items)},
    ) as add_span:
        response = client.memories.add_bulk(items=items)
        add_span.update(
            output={"count": response.count},
            metadata={"item_statuses": [getattr(r, "status", "?") for r in response.items]},
        )

    print(f"\n  nexorel — {response.count} docs queued:")
    for result, item in zip(response.items, items):
        print(f"    [{getattr(result,'status','?'):>10}]  {item['title']}")

    langfuse.update_current_trace(output={"count": response.count, "titles": titles})


@observe(name="cli-ingest-brand", capture_input=False, capture_output=False)
def ingest_real_brand(client: Hyperspell, brand: str):
    meta = REAL_BRANDS[brand]
    path = DOCS_DIR / "brands" / f"{brand}.md"
    if not path.exists():
        print(f"  WARNING: brands/{brand}.md not found")
        langfuse.update_current_trace(
            input={"brand": brand},
            tags=[f"brand:{brand}", "ingest", "cli"],
        )
        langfuse.update_current_span(level="WARNING", status_message=f"brands/{brand}.md not found")
        return

    langfuse.update_current_trace(
        input={"brand": brand, "title": meta["title"]},
        tags=[f"brand:{brand}", "ingest", "cli"],
        metadata={"company": meta["company"], "therapeutic_area": meta["ta"]},
    )

    with langfuse.start_as_current_observation(
        as_type="span",
        name="hyperspell.memories.add_bulk",
        input={"brand": brand, "title": meta["title"]},
    ) as add_span:
        response = client.memories.add_bulk(items=[{
            "text": path.read_text(encoding="utf-8"),
            "title": meta["title"],
            "metadata": {
                "brand": brand,
                "doc_type": "brand_intelligence",
                "therapeutic_area": meta["ta"],
                "company": meta["company"],
            },
        }])
        add_span.update(
            output={"count": response.count},
            metadata={"item_statuses": [getattr(r, "status", "?") for r in response.items]},
        )

    for result in response.items:
        print(f"  [{getattr(result,'status','?'):>10}]  {meta['title']}")

    langfuse.update_current_trace(output={"count": response.count, "title": meta["title"]})


@observe(name="cli-query", capture_input=False, capture_output=False)
def query_brand(client: Hyperspell, question: str, brand: str):
    print(f"\nQuery ({brand}): {question}\n")

    langfuse.update_current_trace(
        input={"question": question, "brand": brand},
        tags=[f"brand:{brand}", "query", "cli"],
    )

    with langfuse.start_as_current_observation(
        as_type="span",
        name="hyperspell.memories.search",
        input={"query": question, "brand": brand, "sources": ["vault"]},
    ) as search_span:
        response = client.memories.search(
            query=question,
            sources=["vault"],
            answer=True,
            options={"filter": {"brand": brand}},
        )
        sources = []
        for doc in (response.documents or []):
            title = getattr(doc, "title", None) or getattr(doc, "resource_id", "—")
            sources.append(title)
        search_span.update(
            output={"sources": sources[:3], "answer_length": len(response.answer or "")},
            metadata={"document_count": len(response.documents or [])},
        )

    print(f"Answer:\n{response.answer}\n")
    if response.documents:
        print("Sources:")
        for doc in response.documents[:3]:
            title = getattr(doc, "title", None) or getattr(doc, "resource_id", "—")
            print(f"  - {title}")

    langfuse.update_current_trace(output={"answer": response.answer, "sources": sources[:3]})


def main():
    parser = argparse.ArgumentParser(description="Ingest pharma brand docs into Hyperspell")
    parser.add_argument("--brand", "-b", help="Brand to ingest (e.g. keytruda, nexorel, or 'all')", default="all")
    parser.add_argument("--query", "-q", help="Run a test query after ingestion")
    parser.add_argument("--query-only", help="Skip ingestion, just run a query")
    args = parser.parse_args()

    api_key = os.environ.get("HYPERSPELL_API_KEY")
    if not api_key:
        print("ERROR: HYPERSPELL_API_KEY is not set.")
        sys.exit(1)

    client = Hyperspell(api_key=api_key)

    if not args.query_only:
        brand = args.brand.lower()
        if brand == "all":
            print("Ingesting Nexorel (fictional)...")
            ingest_nexorel(client)
            print("\nIngesting 10 real brands...")
            for b in REAL_BRANDS:
                ingest_real_brand(client, b)
        elif brand == "nexorel":
            print("Ingesting Nexorel...")
            ingest_nexorel(client)
        elif brand in REAL_BRANDS:
            print(f"Ingesting {brand}...")
            ingest_real_brand(client, brand)
        else:
            print(f"Unknown brand: {brand}. Options: nexorel, {', '.join(REAL_BRANDS)}, all")
            sys.exit(1)
        print("\nDone. Docs processing in Hyperspell (~10s before queryable).")

    question = args.query_only or args.query
    if question:
        brand = args.brand if args.brand != "all" else "nexorel"
        query_brand(client, question, brand)


if __name__ == "__main__":
    main()
