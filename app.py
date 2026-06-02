import atexit
import os
from pathlib import Path
from dotenv import load_dotenv
from flask import Flask, render_template, request, jsonify, redirect, session, url_for
from werkzeug.utils import secure_filename
from werkzeug.middleware.proxy_fix import ProxyFix
from hyperspell import Hyperspell
from langfuse import get_client, observe

from auth import init_auth, oauth, current_user, login_required, role_required

load_dotenv()

app = Flask(__name__)

# Behind Vercel's proxy, honor X-Forwarded-Proto/Host so url_for(_external=True)
# generates https:// URLs — required for the Keycloak OIDC redirect_uri to match.
if os.environ.get("VERCEL"):
    app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)
    app.config["PREFERRED_URL_SCHEME"] = "https"

init_auth(app)
client = Hyperspell(api_key=os.environ["HYPERSPELL_API_KEY"])

langfuse = get_client()
atexit.register(langfuse.flush)

BRANDS = {
    "nexorel":   {"label": "Nexorel (nexoratinib)",       "ta": "Oncology · EGFR+ NSCLC",          "company": "Aether Oncology (fictional)"},
    "keytruda":  {"label": "Keytruda (pembrolizumab)",    "ta": "Oncology · PD-1 inhibitor",        "company": "Merck"},
    "humira":    {"label": "Humira (adalimumab)",         "ta": "Immunology · Rheumatology",        "company": "AbbVie"},
    "ozempic":   {"label": "Ozempic (semaglutide)",       "ta": "Diabetes · Obesity · GLP-1",       "company": "Novo Nordisk"},
    "eliquis":   {"label": "Eliquis (apixaban)",          "ta": "Cardiology · Anticoagulation",     "company": "BMS / Pfizer"},
    "dupixent":  {"label": "Dupixent (dupilumab)",        "ta": "Dermatology · Type 2 inflammation","company": "Sanofi / Regeneron"},
    "tagrisso":  {"label": "Tagrisso (osimertinib)",      "ta": "Oncology · EGFR+ NSCLC",          "company": "AstraZeneca"},
    "entresto":  {"label": "Entresto (sacubitril/val.)",  "ta": "Cardiology · Heart Failure",       "company": "Novartis"},
    "skyrizi":   {"label": "Skyrizi (risankizumab)",      "ta": "Dermatology · Gastroenterology",   "company": "AbbVie"},
    "ibrance":   {"label": "Ibrance (palbociclib)",       "ta": "Oncology · HR+/HER2- Breast",      "company": "Pfizer"},
    "jardiance": {"label": "Jardiance (empagliflozin)",   "ta": "Diabetes · Cardiovascular",        "company": "Boehringer Ingelheim / Lilly"},
}

SAMPLE_QUESTIONS = {
    "nexorel":   ["What is Nexorel's market share target for 2026?", "How does Nexorel compare to Tagrisso in CNS efficacy?", "What are the top prescribing barriers for Nexorel?", "What was the intracranial PFS in NEXUS-1?"],
    "keytruda":  ["What are Keytruda's key approved indications?", "What was the OS benefit in KEYNOTE-024?", "How does Keytruda compare to Opdivo?", "What are the immune-related AEs to monitor?"],
    "humira":    ["What biosimilars are competing with Humira?", "What is Humira's MOA and approved indications?", "How does Humira compare to Skyrizi in psoriasis?", "What are the key safety warnings for Humira?"],
    "ozempic":   ["What is Ozempic's HbA1c reduction vs comparators?", "How does Ozempic compare to Mounjaro for weight loss?", "What cardiovascular outcomes data does Ozempic have?", "What are the GI side effects of semaglutide?"],
    "eliquis":   ["How does Eliquis compare to Xarelto in AF stroke prevention?", "What is Eliquis's bleeding risk profile?", "What were the ARISTOTLE trial key outcomes?", "What is Eliquis's market share vs other NOACs?"],
    "dupixent":  ["What is Dupixent's EASI-75 response rate in atopic dermatitis?", "How does Dupixent work in type 2 inflammation?", "What new indications has Dupixent expanded into?", "How does Dupixent compare to JAK inhibitors?"],
    "tagrisso":  ["What was OS benefit in ADAURA for adjuvant Tagrisso?", "How does Tagrisso handle T790M resistance?", "What are Tagrisso's CNS penetration data?", "What are the key AEs with osimertinib?"],
    "entresto":  ["What was the mortality benefit in PARADIGM-HF?", "How does Entresto compare to ACE inhibitors in HFrEF?", "What is Entresto's mechanism and dosing?", "What are the key contraindications for Entresto?"],
    "skyrizi":   ["What are Skyrizi's PASI 90 rates vs Humira?", "How does Skyrizi perform in Crohn's disease?", "What is Skyrizi's MOA vs other IL-23 inhibitors?", "How does Skyrizi compare to Tremfya?"],
    "ibrance":   ["What was PFS in PALOMA-2 for Ibrance?", "How does Ibrance compare to Kisqali and Verzenio?", "What are the neutropenia rates with palbociclib?", "What biomarkers predict response to Ibrance?"],
    "jardiance": ["What was the CV death reduction in EMPA-REG OUTCOME?", "How does Jardiance compare to Farxiga in heart failure?", "What are the key safety signals with SGLT2 inhibitors?", "What is Jardiance's mechanism in HFrEF?"],
}

GLOBAL_SAMPLE_QUESTIONS = [
    "What is the Q2 2026 campaign theme?",
    "Which brands target oncology / EGFR+ NSCLC?",
    "Compare the cardiovascular outcomes data across the diabetes brands.",
    "Which brands face biosimilar or generic competition?",
    "Summarize the key safety warnings mentioned across all brands.",
    "Who are the top KOLs mentioned across the portfolio?",
]


# ──────────────────────────────────────────────────────────────────────────────
# Citation helpers
# ──────────────────────────────────────────────────────────────────────────────

# Reverse lookup: brand display name (first word of label) → brand key
BRAND_NAME_TO_KEY = {b["label"].split(" (")[0].lower(): key for key, b in BRANDS.items()}


def _infer_brand(title):
    """Best-effort: figure out which brand a document title belongs to."""
    if not title:
        return None
    t = title.lower()
    for name, key in BRAND_NAME_TO_KEY.items():
        if name in t:
            return BRANDS[key]["label"].split(" (")[0]
    return None


def _build_citations(documents):
    """Turn Hyperspell search documents into deduped, ranked citation objects."""
    citations = []
    seen = set()
    for doc in (documents or []):
        title = getattr(doc, "title", None) or getattr(doc, "resource_id", None)
        if not title or title in seen:
            continue
        seen.add(title)
        score = getattr(doc, "score", None)
        citations.append({
            "title": title,
            "score": round(float(score), 3) if score is not None else None,
            "brand": _infer_brand(title),
            "resource_id": getattr(doc, "resource_id", None),
        })
    return citations


# ──────────────────────────────────────────────────────────────────────────────
# Auth routes
# ──────────────────────────────────────────────────────────────────────────────

@app.route("/login")
def login():
    next_url = request.args.get("next")
    if next_url:
        session["next"] = next_url
    redirect_uri = url_for("auth_callback", _external=True)
    try:
        return oauth.keycloak.authorize_redirect(redirect_uri)
    except Exception as e:
        # Keycloak not reachable/configured yet (e.g. placeholder KEYCLOAK_URL on a
        # fresh deploy). Show a clear setup message instead of a raw 500.
        kc = os.environ.get("KEYCLOAK_URL", "")
        return (
            "<html><body style='font-family:-apple-system,sans-serif;background:#0b0e18;"
            "color:#e2e8f0;display:flex;align-items:center;justify-content:center;"
            "min-height:100vh;margin:0'><div style='max-width:560px;padding:40px;"
            "border:1px solid #232b3e;border-radius:16px;background:#131726'>"
            "<h2 style='margin:0 0 12px'>🔐 Authentication not configured yet</h2>"
            "<p style='color:#94a3b8;line-height:1.7'>The app is deployed, but it can't reach "
            f"the Keycloak identity server at <code style='color:#a5b4fc'>{kc}</code>.</p>"
            "<p style='color:#94a3b8;line-height:1.7'>Set the <code style='color:#a5b4fc'>"
            "KEYCLOAK_URL</code> and <code style='color:#a5b4fc'>KEYCLOAK_CLIENT_SECRET</code> "
            "environment variables to your public Keycloak instance, then redeploy.</p>"
            f"<p style='color:#475569;font-size:12px;margin-top:20px'>{type(e).__name__}: {e}</p>"
            "</div></body></html>",
            503,
        )


@app.route("/auth/callback")
def auth_callback():
    token = oauth.keycloak.authorize_access_token()
    userinfo = token.get("userinfo") or {}
    session["user"] = {
        "email": userinfo.get("email"),
        "name": userinfo.get("name") or userinfo.get("preferred_username") or userinfo.get("email"),
        "roles": userinfo.get("roles", []),
        "sub": userinfo.get("sub"),
    }
    session["id_token"] = token.get("id_token")
    next_url = session.pop("next", None) or url_for("index")
    return redirect(next_url)


@app.route("/logout")
def logout():
    id_token = session.get("id_token")
    session.clear()
    kc = os.environ.get("KEYCLOAK_URL")
    realm = os.environ.get("KEYCLOAK_REALM")
    if id_token and kc and realm:
        post_logout = url_for("index", _external=True)
        return redirect(
            f"{kc}/realms/{realm}/protocol/openid-connect/logout"
            f"?id_token_hint={id_token}&post_logout_redirect_uri={post_logout}"
        )
    return redirect(url_for("index"))


@app.route("/me")
def me():
    user = current_user()
    if not user:
        return jsonify({"authenticated": False}), 401
    return jsonify({"authenticated": True, **user})


# ──────────────────────────────────────────────────────────────────────────────
# App routes
# ──────────────────────────────────────────────────────────────────────────────

@app.route("/")
@login_required
def index():
    return render_template("index.html", brands=BRANDS, user=current_user())


@app.route("/brands")
@login_required
def get_brands():
    return jsonify(BRANDS)


@app.route("/query", methods=["POST"])
@login_required
@observe(name="brand-query", capture_input=False, capture_output=False)
def query():
    body = request.json or {}
    question = body.get("question", "").strip()
    brand = body.get("brand", "nexorel").strip()
    user = current_user()

    langfuse.update_current_trace(
        input={"question": question, "brand": brand},
        user_id=user["email"],
        tags=[f"brand:{brand}", "query", f"role:{'admin' if 'admin' in user['roles'] else 'viewer'}"],
        metadata={"endpoint": "/query", "user_roles": user["roles"]},
    )

    if not question:
        langfuse.update_current_span(level="WARNING", status_message="No question provided")
        return jsonify({"error": "No question provided"}), 400
    if brand not in BRANDS:
        langfuse.update_current_span(level="WARNING", status_message=f"Unknown brand: {brand}")
        return jsonify({"error": f"Unknown brand: {brand}"}), 400

    try:
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

            citations = _build_citations(response.documents)
            sources = [c["title"] for c in citations]

            search_span.update(
                output={"sources": sources, "answer_length": len(response.answer or "")},
                metadata={"document_count": len(response.documents or []), "source_count": len(sources)},
            )

        result = {
            "answer": response.answer or "No answer found.",
            "sources": sources,
            "citations": citations,
            "document_count": len(response.documents or []),
            "brand": BRANDS[brand]["label"],
        }
        langfuse.update_current_trace(output=result)
        return jsonify(result)

    except Exception as e:
        langfuse.update_current_span(level="ERROR", status_message=str(e))
        return jsonify({"error": str(e)}), 500


@app.route("/global-query", methods=["POST"])
@login_required
@observe(name="global-query", capture_input=False, capture_output=False)
def global_query():
    """Cross-brand chat: searches the whole vault with NO brand filter."""
    body = request.json or {}
    question = body.get("question", "").strip()
    user = current_user()

    langfuse.update_current_trace(
        input={"question": question},
        user_id=user["email"],
        tags=["global", "query", f"role:{'admin' if 'admin' in user['roles'] else 'viewer'}"],
        metadata={"endpoint": "/global-query", "scope": "all-brands"},
    )

    if not question:
        langfuse.update_current_span(level="WARNING", status_message="No question provided")
        return jsonify({"error": "No question provided"}), 400

    try:
        with langfuse.start_as_current_observation(
            as_type="span",
            name="hyperspell.memories.search",
            input={"query": question, "sources": ["vault"], "scope": "global"},
        ) as search_span:
            response = client.memories.search(
                query=question,
                sources=["vault"],
                answer=True,
            )

            citations = _build_citations(response.documents)
            sources = [c["title"] for c in citations]
            brands_hit = sorted({c["brand"] for c in citations if c["brand"]})

            search_span.update(
                output={"sources": sources, "answer_length": len(response.answer or "")},
                metadata={
                    "document_count": len(response.documents or []),
                    "source_count": len(sources),
                    "brands_hit": brands_hit,
                },
            )

        result = {
            "answer": response.answer or "No answer found.",
            "sources": sources,
            "citations": citations,
            "document_count": len(response.documents or []),
            "brands_hit": brands_hit,
        }
        langfuse.update_current_trace(output=result)
        return jsonify(result)

    except Exception as e:
        langfuse.update_current_span(level="ERROR", status_message=str(e))
        return jsonify({"error": str(e)}), 500


@app.route("/sample-questions/<brand>")
@login_required
def sample_questions(brand):
    if brand == "global":
        return jsonify(GLOBAL_SAMPLE_QUESTIONS)
    return jsonify(SAMPLE_QUESTIONS.get(brand, []))


@app.route("/ingest", methods=["POST"])
@role_required("admin")
@observe(name="brand-ingest", capture_input=False, capture_output=False)
def ingest():
    brand = (request.json or {}).get("brand", "").strip()
    user = current_user()

    langfuse.update_current_trace(
        input={"brand": brand},
        user_id=user["email"],
        tags=[f"brand:{brand}", "ingest", "role:admin"],
        metadata={"endpoint": "/ingest"},
    )

    if brand not in BRANDS:
        langfuse.update_current_span(level="WARNING", status_message=f"Unknown brand: {brand}")
        return jsonify({"error": f"Unknown brand: {brand}"}), 400

    brands_dir = Path(__file__).parent / "brands"
    root_dir = Path(__file__).parent

    # Nexorel uses multiple files; real brands use one file each
    NEXOREL_DOCS = {
        "brand_plan_2026.md":          "Nexorel Annual Brand Plan 2026",
        "competitive_intelligence.md": "Nexorel Competitive Intelligence Report",
        "key_messages.md":             "Nexorel MLR-Approved Key Messages",
        "patient_journey.md":          "EGFR+ NSCLC Patient Journey Map",
        "hcp_segmentation.md":         "Nexorel HCP Segmentation & Targeting Guide",
        "medical_affairs_strategy.md": "Nexorel Medical Affairs Strategy",
        "market_research_insights.md": "Nexorel Market Research & Brand Tracker",
        "field_force_briefing.md":     "Nexorel Q2 2026 Field Force Briefing",
    }

    try:
        if brand == "nexorel":
            items = []
            for filename, title in NEXOREL_DOCS.items():
                path = root_dir / filename
                if path.exists():
                    items.append({
                        "text": path.read_text(encoding="utf-8"),
                        "title": title,
                        "metadata": {"brand": "nexorel", "therapeutic_area": "oncology"},
                    })
        else:
            path = brands_dir / f"{brand}.md"
            if not path.exists():
                langfuse.update_current_span(level="WARNING", status_message=f"brands/{brand}.md not found")
                return jsonify({"error": f"brands/{brand}.md not found"}), 404
            b = BRANDS[brand]
            items = [{
                "text": path.read_text(encoding="utf-8"),
                "title": b["label"],
                "metadata": {"brand": brand, "therapeutic_area": b["ta"], "company": b["company"]},
            }]

        if not items:
            langfuse.update_current_span(level="WARNING", status_message="No documents found to ingest")
            return jsonify({"error": "No documents found to ingest"}), 404

        titles = [item["title"] for item in items]
        with langfuse.start_as_current_observation(
            as_type="span",
            name="hyperspell.memories.add_bulk",
            input={"brand": brand, "titles": titles, "item_count": len(items)},
        ) as add_span:
            response = client.memories.add_bulk(items=items)
            add_span.update(
                output={"count": response.count, "success": response.success},
                metadata={"titles": titles},
            )

        result = {"count": response.count, "brand": brand, "success": response.success}
        langfuse.update_current_trace(output=result)
        return jsonify(result)

    except Exception as e:
        langfuse.update_current_span(level="ERROR", status_message=str(e))
        return jsonify({"error": str(e)}), 500


# Text-based document types we can read and push into the memory layer
ALLOWED_UPLOAD_EXT = {".md", ".txt", ".markdown", ".csv", ".json", ".text"}


@app.route("/upload", methods=["POST"])
@role_required("admin")
@observe(name="brand-upload", capture_input=False, capture_output=False)
def upload():
    """Upload an arbitrary document (file or pasted text) into a brand's memory layer."""
    brand = (request.form.get("brand") or "").strip()
    title = (request.form.get("title") or "").strip()
    pasted = (request.form.get("text") or "").strip()
    user = current_user()

    langfuse.update_current_trace(
        input={"brand": brand, "title": title},
        user_id=user["email"],
        tags=[f"brand:{brand}", "upload", "role:admin"],
        metadata={"endpoint": "/upload"},
    )

    if brand not in BRANDS:
        langfuse.update_current_span(level="WARNING", status_message=f"Unknown brand: {brand}")
        return jsonify({"error": f"Unknown brand: {brand}"}), 400

    # Pull text from an uploaded file or a pasted body
    text = ""
    filename = None
    upload_file = request.files.get("file")
    if upload_file and upload_file.filename:
        filename = secure_filename(upload_file.filename)
        ext = Path(filename).suffix.lower()
        if ext and ext not in ALLOWED_UPLOAD_EXT:
            msg = f"Unsupported file type '{ext}'. Allowed: {', '.join(sorted(ALLOWED_UPLOAD_EXT))}"
            langfuse.update_current_span(level="WARNING", status_message=msg)
            return jsonify({"error": msg}), 400
        raw = upload_file.read()
        text = raw.decode("utf-8", errors="ignore")
        if not title:
            title = Path(filename).stem
    elif pasted:
        text = pasted

    if not text.strip():
        langfuse.update_current_span(level="WARNING", status_message="No document content provided")
        return jsonify({"error": "No document content — attach a file or paste text."}), 400

    b = BRANDS[brand]
    if not title:
        title = f"{b['label']} — uploaded document"

    item = {
        "text": text,
        "title": title,
        "metadata": {
            "brand": brand,
            "therapeutic_area": b["ta"],
            "company": b["company"],
            "source_type": "upload",
            "uploaded_by": user["email"],
            "original_filename": filename,
        },
    }

    try:
        with langfuse.start_as_current_observation(
            as_type="span",
            name="hyperspell.memories.add_bulk",
            input={"brand": brand, "title": title, "char_count": len(text)},
        ) as add_span:
            response = client.memories.add_bulk(items=[item])
            add_span.update(
                output={"count": response.count, "success": response.success},
                metadata={"title": title, "filename": filename},
            )

        result = {
            "count": response.count,
            "brand": brand,
            "title": title,
            "success": response.success,
        }
        langfuse.update_current_trace(output=result)
        return jsonify(result)

    except Exception as e:
        langfuse.update_current_span(level="ERROR", status_message=str(e))
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(debug=True, port=5001)
