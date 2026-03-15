"""
NEXUS Core – Tool test suite
Runs against the live streamable-http server on http://127.0.0.1:8765/mcp
"""
import json
import sys

import httpx

BASE = "http://127.0.0.1:8765/mcp"
HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json, text/event-stream",
}
TIMEOUT = 90

_req_id = 0


def jrpc(method, params=None):
    global _req_id
    _req_id += 1
    return {"jsonrpc": "2.0", "id": _req_id, "method": method, "params": params or {}}


def parse_response(r: httpx.Response) -> dict:
    ct = r.headers.get("content-type", "")
    if "application/json" in ct:
        return r.json()
    # SSE stream – pick the last data: line that contains a full JSON object
    for line in reversed(r.text.splitlines()):
        line = line.strip()
        if line.startswith("data:"):
            candidate = line[5:].strip()
            if candidate and candidate != "[DONE]":
                try:
                    return json.loads(candidate)
                except json.JSONDecodeError:
                    continue
    raise ValueError(f"Could not parse response:\n{r.text[:500]}")


def call_tool(name: str, args: dict) -> dict:
    r = httpx.post(
        BASE,
        json=jrpc("tools/call", {"name": name, "arguments": args}),
        headers=HEADERS,
        timeout=TIMEOUT,
    )
    r.raise_for_status()
    envelope = parse_response(r)
    result = envelope.get("result", {})
    content = result.get("content", [])
    if content:
        try:
            return json.loads(content[0].get("text", "{}"))
        except json.JSONDecodeError:
            return {"raw": content[0].get("text", "")}
    return result


def section(title: str):
    print(f"\n{'═'*60}")
    print(f"  {title}")
    print('═'*60)


ok = 0
fail = 0

# ── 1. tools/list ─────────────────────────────────────────────────────────────
section("1 · tools/list")
r = httpx.post(BASE, json=jrpc("tools/list"), headers=HEADERS, timeout=15)
r.raise_for_status()
data = parse_response(r)
tools = data.get("result", {}).get("tools", [])
names = [t["name"] for t in tools]
print(f"  Registered tools ({len(tools)}):")
for n in names:
    print(f"    ✓ {n}")
expected = {
    "nexus_discover_source", "nexus_ingest_and_clean",
    "nexus_semantic_query", "nexus_hybrid_lookup",
    "nexus_verify_compliance", "nexus_get_index_metadata",
    "nexus_refresh_index",
}
missing = expected - set(names)
if missing:
    print(f"  ✗ MISSING: {missing}")
    fail += 1
else:
    print("  ✓ All 7 tools registered")
    ok += 1

# ── 2. nexus_get_index_metadata (empty) ───────────────────────────────────────
section("2 · nexus_get_index_metadata (empty index)")
res = call_tool("nexus_get_index_metadata", {})
print(f"  Response: {json.dumps(res, indent=2)[:300]}")
if "error" in res or "sources" in res:
    print("  ✓ Deterministic empty-index response")
    ok += 1
else:
    print("  ✗ Unexpected response shape")
    fail += 1

# ── 3. nexus_discover_source ─────────────────────────────────────────────────
section("3 · nexus_discover_source('fastapi')")
res = call_tool("nexus_discover_source", {"framework": "fastapi"})
if "error" in res:
    print(f"  ✗ Error: {res['error']}")
    fail += 1
else:
    url = res.get("recommended_url", "")
    count = len(res.get("all_candidates", []))
    print(f"  recommended_url : {url}")
    print(f"  candidates found: {count}")
    if url:
        print("  ✓ Discovery succeeded")
        ok += 1
    else:
        print("  ✗ No URL returned")
        fail += 1

# ── 4. nexus_ingest_and_clean ────────────────────────────────────────────────
section("4 · nexus_ingest_and_clean('fastapi', FastAPI docs)")
DOC_URL = "https://fastapi.tiangolo.com/tutorial/body/"
print(f"  URL: {DOC_URL}")
res = call_tool("nexus_ingest_and_clean", {"framework": "fastapi", "url": DOC_URL})
status = res.get("status", "")
print(f"  status      : {status}")
print(f"  chunk_count : {res.get('chunk_count', '?')}")
print(f"  checksum    : {res.get('checksum', '?')[:16]}…")
if status in ("ingested", "unchanged") and not res.get("error"):
    print("  ✓ Ingest succeeded")
    ok += 1
else:
    print(f"  ✗ Ingest failed: {res.get('error', res)}")
    fail += 1

# ── 5. nexus_get_index_metadata (post-ingest) ────────────────────────────────
section("5 · nexus_get_index_metadata('fastapi') after ingest")
res = call_tool("nexus_get_index_metadata", {"framework": "fastapi"})
sources = res.get("sources", [])
print(f"  total_sources: {res.get('total_sources', 0)}")
for s in sources:
    print(f"    url={s.get('url','?')}  chunks={s.get('chunk_count','?')}")
if sources:
    print("  ✓ Metadata recorded")
    ok += 1
else:
    print("  ✗ No metadata found")
    fail += 1

# ── 6. nexus_semantic_query ──────────────────────────────────────────────────
section("6 · nexus_semantic_query('fastapi', 'POST request with Pydantic body')")
res = call_tool("nexus_semantic_query", {
    "framework": "fastapi",
    "query": "POST request with Pydantic body model",
    "k": 3,
})
results = res.get("results", [])
# unwrap sentinel "no results" message
if results and isinstance(results[0], dict) and "message" in results[0] and not results[0].get("content"):
    results = []
print(f"  threshold : {res.get('threshold', '?')}")
print(f"  results   : {len(results)}")
for r2 in results[:2]:
    score = r2.get("similarity_score", "?")
    preview = r2.get("content", "")[:80].replace("\n", " ")
    print(f"    [{score}] {preview}…")
if results:
    print("  ✓ Semantic search returned results")
    ok += 1
else:
    print("  ✗ No results above threshold (model may still be loading)")
    fail += 1

# ── 7. nexus_hybrid_lookup ───────────────────────────────────────────────────
section("7 · nexus_hybrid_lookup('fastapi', 'BaseModel')")
res = call_tool("nexus_hybrid_lookup", {
    "framework": "fastapi",
    "query": "BaseModel",
    "k": 3,
})
total = res.get("total", 0)
results = res.get("results", [])
print(f"  total results: {total}")
for r2 in results[:2]:
    mtype = r2.get("match_type", "?")
    preview = r2.get("content", "")[:80].replace("\n", " ")
    print(f"    [{mtype}] {preview}…")
if total > 0:
    print("  ✓ Hybrid lookup returned results")
    ok += 1
else:
    print("  ✗ No hybrid results")
    fail += 1

# ── 8. nexus_refresh_index (unchanged) ───────────────────────────────────────
section("8 · nexus_refresh_index (same URL → no-change)")
res = call_tool("nexus_refresh_index", {"framework": "fastapi", "url": DOC_URL})
action = res.get("refresh_action", "")
print(f"  refresh_action: {action}")
print(f"  message       : {res.get('message', '')}")
if action == "no_change":
    print("  ✓ Checksum guard works correctly")
    ok += 1
else:
    print(f"  ✗ Expected 'no_change', got '{action}'")
    fail += 1

# ── 9. nexus_verify_compliance ───────────────────────────────────────────────
section("9 · nexus_verify_compliance('fastapi', sample code)")
CODE = """
from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()

class Item(BaseModel):
    name: str
    price: float

@app.post("/items/")
async def create_item(item: Item):
    return item
"""
res = call_tool("nexus_verify_compliance", {"framework": "fastapi", "code_snippet": CODE})
result_text = res.get("verification_result", "")
sources = res.get("sources_consulted", [])
print(f"  sources_consulted : {len(sources)}")
verdict_line = next((line for line in result_text.splitlines() if "VERDICT" in line), result_text[:120])
print(f"  verdict           : {verdict_line.strip()}")
if result_text:
    print("  ✓ Compliance check ran")
    ok += 1
else:
    print("  ✗ No verification result")
    fail += 1

# ── Summary ──────────────────────────────────────────────────────────────────
print(f"\n{'═'*60}")
print(f"  RESULTS: {ok} passed · {fail} failed")
print('═'*60)
sys.exit(0 if fail == 0 else 1)
