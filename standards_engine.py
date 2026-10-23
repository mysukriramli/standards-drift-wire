import os
import json
import hashlib
import duckdb
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

DB_FILE = "data/standards_drift.db"
HISTORY_DIR = "data/history"
EXPORT_DIR = "public"
API_DIR = os.path.join(EXPORT_DIR, "v1")
RFC_INDEX_URL = "https://www.rfc-editor.org/rfc-index.xml"
XML_NS = {"r": "https://www.rfc-editor.org/rfc-index"}

def compute_hash(payload: dict) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()

def get_xml_text(element, tag_name):
    if element is None:
        return ""
    child = element.find(f"r:{tag_name}", XML_NS)
    return child.text.strip() if child is not None and child.text else ""

def get_xml_list(element, rel_tag):
    if element is None:
        return []
    rel_container = element.find(f"r:{rel_tag}", XML_NS)
    if rel_container is None:
        return []
    return [doc_id.text.strip() for doc_id in rel_container.findall("r:doc-id", XML_NS) if doc_id.text]

def fetch_rfc_index():
    headers = {"User-Agent": "StandardsDriftWire/1.0 (Machine-First Temporal Knowledge Infrastructure)"}
    resp = requests.get(RFC_INDEX_URL, headers=headers, timeout=60)
    if resp.status_code != 200:
        return []
    
    root = ET.fromstring(resp.content)
    standards = []
    
    for entry in root.findall("r:rfc-entry", XML_NS):
        doc_id = get_xml_text(entry, "doc-id")
        title = get_xml_text(entry, "title")
        status = get_xml_text(entry, "current-status")
        stream = get_xml_text(entry, "stream")
        area = get_xml_text(entry, "area")
        
        date_el = entry.find("r:date", XML_NS)
        month = get_xml_text(date_el, "month")
        year_str = get_xml_text(date_el, "year")
        year = int(year_str) if year_str.isdigit() else 0
        
        obsoletes = get_xml_list(entry, "obsoletes")
        obsoleted_by = get_xml_list(entry, "obsoleted-by")
        updates = get_xml_list(entry, "updates")
        updated_by = get_xml_list(entry, "updated-by")
        
        state_repr = {
            "doc_id": doc_id,
            "title": title,
            "current_status": status,
            "stream": stream,
            "area": area,
            "obsoletes": obsoletes,
            "obsoleted_by": obsoleted_by,
            "updates": updates,
            "updated_by": updated_by
        }
        
        standards.append({
            "doc_id": doc_id,
            "title": title,
            "current_status": status,
            "publication_year": year,
            "publication_month": month,
            "stream": stream,
            "area": area,
            "obsoletes": obsoletes,
            "obsoleted_by": obsoleted_by,
            "updates": updates,
            "updated_by": updated_by,
            "content_hash": compute_hash(state_repr)
        })
        
    return standards

def serialize_row(row: dict) -> dict:
    out = {}
    for k, v in row.items():
        if k.endswith("_json") and isinstance(v, str):
            try:
                out[k[:-5]] = json.loads(v)
            except Exception:
                out[k[:-5]] = v
        else:
            out[k] = v
    return out

def build_static_api(conn):
    os.makedirs(API_DIR, exist_ok=True)
    now_iso = datetime.now(timezone.utc).isoformat()
    
    # 1. Obsoleted / Superseded Standards
    cur = conn.execute("SELECT * FROM standards WHERE obsoleted_by_json != '[]' ORDER BY publication_year DESC LIMIT 100")
    cols = [desc[0] for desc in cur.description]
    obsoleted = [serialize_row(dict(zip(cols, row))) for row in cur.fetchall()]
    
    with open(os.path.join(API_DIR, "obsoleted.json"), "w", encoding="utf-8") as f:
        json.dump({"metadata": {"updated_at": now_iso, "count": len(obsoleted)}, "obsoleted_standards": obsoleted}, f, indent=2)

    # 2. Latest Published Standards (Current Year)
    current_year = datetime.now(timezone.utc).year
    cur = conn.execute(f"SELECT * FROM standards WHERE publication_year >= {current_year - 1} ORDER BY publication_year DESC, doc_id DESC LIMIT 100")
    recent = [serialize_row(dict(zip(cols, row))) for row in cur.fetchall()]
    
    with open(os.path.join(API_DIR, "recent-standards.json"), "w", encoding="utf-8") as f:
        json.dump({"metadata": {"updated_at": now_iso, "count": len(recent)}, "standards": recent}, f, indent=2)

    # 3. LLM Digest
    lines = [
        "# Standards Drift Wire",
        f"> Last Sync: {now_iso} UTC",
        "> Source: Official RFC Editor Registry",
        "",
        "## Recent Standards & Protocol Transitions"
    ]
    for s in recent[:20]:
        obs_note = f" (OBSOLETED BY: {', '.join(s['obsoleted_by'])})" if s["obsoleted_by"] else ""
        upd_note = f" (UPDATED BY: {', '.join(s['updated_by'])})" if s["updated_by"] else ""
        lines.append(f"- **{s['doc_id']}**: {s['title']} [{s['current_status']}]{obs_note}{upd_note}")
        
    with open(os.path.join(EXPORT_DIR, "llms.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    # 4. HTML Dashboard
    html = f"""<!DOCTYPE html><html><head><title>Standards Drift Wire</title></head>
    <body style='font-family:system-ui,sans-serif;max-width:850px;margin:2rem auto;line-height:1.6;padding:0 1rem;'>
    <h1>📜 Standards Drift Wire</h1>
    <p>Machine-first temporal wire tracking RFC lifecycles, protocol obsoletions, and standard deprecations.</p>
    <h3>Machine Feeds</h3>
    <ul>
      <li><a href='v1/recent-standards.json'>/v1/recent-standards.json</a></li>
      <li><a href='v1/obsoleted.json'>/v1/obsoleted.json</a></li>
      <li><a href='llms.txt'>llms.txt</a> (Token-Efficient Digest)</li>
      <li><a href='standards.parquet'>standards.parquet</a> (Columnar Parquet Snapshot)</li>
    </ul></body></html>"""
    with open(os.path.join(EXPORT_DIR, "index.html"), "w", encoding="utf-8") as f:
        f.write(html)

def run():
    os.makedirs("data", exist_ok=True)
    os.makedirs(HISTORY_DIR, exist_ok=True)
    os.makedirs(EXPORT_DIR, exist_ok=True)
    
    conn = duckdb.connect(DB_FILE)
    with open("schema.sql", "r", encoding="utf-8") as f:
        conn.execute(f.read())

    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()
    date_str = now.strftime("%Y-%m-%d")
    year_str = now.strftime("%Y")
    month_str = now.strftime("%m")

    standards = fetch_rfc_index()
    if not standards:
        conn.close()
        return

    month_dir = os.path.join(HISTORY_DIR, year_str, month_str)
    os.makedirs(month_dir, exist_ok=True)
    daily_history_file = os.path.join(month_dir, f"{date_str}.jsonl")

    conn.execute("BEGIN TRANSACTION")

    for s in standards:
        doc_id = s["doc_id"]
        title = s["title"].replace("'", "''")
        status = s["current_status"].replace("'", "''")
        year = s["publication_year"]
        month = s["publication_month"].replace("'", "''")
        stream = s["stream"].replace("'", "''")
        area = s["area"].replace("'", "''")
        
        obsoletes_json = json.dumps(s["obsoletes"]).replace("'", "''")
        obsoleted_by_json = json.dumps(s["obsoleted_by"]).replace("'", "''")
        updates_json = json.dumps(s["updates"]).replace("'", "''")
        updated_by_json = json.dumps(s["updated_by"]).replace("'", "''")
        content_hash = s["content_hash"]

        existing = conn.execute(f"SELECT current_status, content_hash FROM standards WHERE doc_id = '{doc_id}'").fetchone()

        if not existing:
            conn.execute(f"""
                INSERT INTO standards (
                    doc_id, title, current_status, publication_year, publication_month,
                    stream, area, obsoletes_json, obsoleted_by_json, updates_json, updated_by_json,
                    content_hash, last_updated_utc
                ) VALUES (
                    '{doc_id}', '{title}', '{status}', {year}, '{month}',
                    '{stream}', '{area}', '{obsoletes_json}', '{obsoleted_by_json}', '{updates_json}', '{updated_by_json}',
                    '{content_hash}', '{now_iso}'
                )
            """)
        elif existing[1] != content_hash:
            old_status = existing[0]
            conn.execute(f"""
                UPDATE standards SET
                    title = '{title}',
                    current_status = '{status}',
                    publication_year = {year},
                    publication_month = '{month}',
                    stream = '{stream}',
                    area = '{area}',
                    obsoletes_json = '{obsoletes_json}',
                    obsoleted_by_json = '{obsoleted_by_json}',
                    updates_json = '{updates_json}',
                    updated_by_json = '{updated_by_json}',
                    content_hash = '{content_hash}',
                    last_updated_utc = '{now_iso}'
                WHERE doc_id = '{doc_id}'
            """)
            
            commit_id = conn.execute("SELECT nextval('seq_commit_id')").fetchone()[0]
            obs_by_str = ",".join(s["obsoleted_by"]).replace("'", "''")
            conn.execute(f"""
                INSERT INTO ledger (commit_id, timestamp_utc, operation, doc_id, old_status, new_status, obsoleted_by)
                VALUES ({commit_id}, '{now_iso}', 'STATUS_DRIFT', '{doc_id}', '{old_status}', '{status}', '{obs_by_str}')
            """)

            ledger_entry = {
                "commit_id": commit_id,
                "timestamp_utc": now_iso,
                "operation": "STATUS_DRIFT",
                "doc_id": doc_id,
                "old_status": old_status,
                "new_status": status,
                "obsoleted_by": s["obsoleted_by"],
                "content_hash": content_hash
            }
            with open(daily_history_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(ledger_entry) + "\n")

    conn.execute("COMMIT")

    conn.execute(f"COPY (SELECT * FROM standards) TO '{EXPORT_DIR}/standards.parquet' (FORMAT PARQUET)")
    build_static_api(conn)
    conn.close()

if __name__ == "__main__":
    run()
