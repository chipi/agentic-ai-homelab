#!/usr/bin/env python3
"""Case 1 read servers (docs, tasks) driven with flotilla's own MCP client (runtime/mcp_client.py): the way the reads worker calls them.
Runs against the throwaway proof (mcp-proof/run.sh) or, with the real URLs and token files, against the mini's n8n.

  PYTHONPATH=<flotilla checkout>/runtime \\
  MCP_DOCS_URL=http://n8n:5678/mcp/case1-docs MCP_DOCS_TOKEN_FILE=~/flotilla/config/mcp/docs.token \\
  MCP_TASKS_URL=http://n8n:5678/mcp/case1-tasks MCP_TASKS_TOKEN_FILE=~/flotilla/config/mcp/tasks.token \\
  python3 test_mcp.py

Optional: TEST_QUERY (words the folder surely has, default "meeting"), OUTSIDE_ID (a real Drive id outside the folder and not the
decisions doc: its refusal then names the folder rule), EXPECT_TASKS (open tasks at least, default 1; 0 accepts an empty list).
Proof only: STUB_LOG_URL (the stub's /__log) adds the checks on what n8n sent Google. Reads only: nothing here writes anywhere.
Prints PASS/FAIL per check and `N of M PASS`; exit 1 on any FAIL. Never prints a token or the text of a document beyond 60 characters.
"""
import json
import os
import sys
import tempfile
import urllib.request

try:
    import mcp_client as mc
except ImportError:
    sys.exit("mcp_client.py not on PYTHONPATH: PYTHONPATH=<flotilla checkout>/runtime")

env = os.environ.get
DOCS_URL, DOCS_TOKEN = env("MCP_DOCS_URL"), env("MCP_DOCS_TOKEN_FILE")
TASKS_URL, TASKS_TOKEN = env("MCP_TASKS_URL"), env("MCP_TASKS_TOKEN_FILE")
if not (DOCS_URL and DOCS_TOKEN and TASKS_URL and TASKS_TOKEN):
    sys.exit("set MCP_DOCS_URL, MCP_DOCS_TOKEN_FILE, MCP_TASKS_URL, MCP_TASKS_TOKEN_FILE")
QUERY, OUTSIDE, STUB = env("TEST_QUERY", "meeting"), env("OUTSIDE_ID"), env("STUB_LOG_URL")
MIN_TASKS = int(env("EXPECT_TASKS", "1"))
results = []


def check(name, ok, detail=""):
    results.append(bool(ok))
    print(("PASS " if ok else "FAIL ") + name + (": " + str(detail)[:300] if detail != "" and (not ok or len(str(detail)) < 120) else ""))
    return ok


def call(client, tool, args):
    """(isError, text) of a tools/call; an McpError is (None, its text)."""
    try:
        r = client.call_tool(tool, args)
        return bool(r.get("isError")), mc.text(r)
    except mc.McpError as e:
        return None, str(e)


def rows(text):
    try:
        v = json.loads(text)
        return v if isinstance(v, list) else []
    except ValueError:
        return []


docs, tasks = mc.McpClient(DOCS_URL, DOCS_TOKEN, timeout=60), mc.McpClient(TASKS_URL, TASKS_TOKEN, timeout=60)

# the session and the tool list: exactly the read tools, with the argument names the station's spec uses
try:
    dt = {t["name"]: t for t in docs.list_tools()}
    tt = {t["name"]: t for t in tasks.list_tools()}
except mc.McpError as e:
    check("initialize and tools/list on both servers", False, e)
    sys.exit(1)
check("docs initialize + tools/list: exactly search and read", sorted(dt) == ["read", "search"], sorted(dt))
check("docs.search takes query (required), docs.read takes id (required)",
      dt["search"]["inputSchema"].get("required") == ["query"] and dt["read"]["inputSchema"].get("required") == ["id"]
      and list(dt["search"]["inputSchema"]["properties"]) == ["query"] and list(dt["read"]["inputSchema"]["properties"]) == ["id"])
check("tasks initialize + tools/list: exactly list", sorted(tt) == ["list"], sorted(tt))
check("tasks.list has no required argument", not tt["list"]["inputSchema"].get("required"))

# search: ids and links in the result text, verbatim
err, text = call(docs, "search", {"query": QUERY})
hits = [h for h in rows(text) if h.get("id")]
check("docs.search '%s' succeeds and returns documents" % QUERY, err is False and hits, text[:120])
check("every hit carries its id and its webViewLink (a Google link, in the text as given)",
      hits and all(h.get("webViewLink", "").startswith("https://") and h["webViewLink"] in text for h in hits))

# read: a hit's text, starting with the title and the link
first = next((h for h in hits if h.get("webViewLink")), None)
if first:
    err, text = call(docs, "read", {"id": first["id"]})
    doc = (rows(text) or [{}])[0]
    check("docs.read of a hit returns its text, with title and the same webViewLink",
          err is False and doc.get("text") and doc.get("title") == first["name"] and doc.get("webViewLink") == first["webViewLink"],
          "%r..." % (doc.get("text") or text)[:60])
    check("the answer starts with title then webViewLink", list(doc)[:2] == ["title", "webViewLink"], list(doc)[:2])
else:
    check("docs.read of a hit", False, "no hit to read")

# the refusals: an MCP tool error (isError), never a result
err, text = call(docs, "read", {"id": OUTSIDE or "0000000000000000000000000000000000"})
check("docs.read of an id outside the folder is refused (isError)%s" % (" naming the folder rule" if OUTSIDE else ""),
      err is True and (not OUTSIDE or "not in the documents folder" in text), text)
err, text = call(docs, "read", {"id": "../../etc/passwd"})
check("docs.read of an id that is not a Drive id is refused before any call", err is True and "document id" in text, text)
err, text = call(docs, "search", {"query": "   "})
check("docs.search with an empty query is refused", err is True, text)

# the token: wrong and absent are 401/403 (the client reports 'unauthorised')
with tempfile.NamedTemporaryFile("w", suffix=".token") as f:
    f.write("not-the-token-" + "x" * 30)
    f.flush()
    err, text = call(mc.McpClient(DOCS_URL, f.name, timeout=20), "search", {"query": QUERY})
    check("a wrong bearer token is refused (401/403)", err is None and "unauthorised" in text, text)
err, text = call(mc.McpClient(TASKS_URL, None, timeout=20), "list", {})
check("no token is refused (401/403)", err is None and "unauthorised" in text, text)
with open(TASKS_TOKEN) as a, open(DOCS_TOKEN) as b:
    if a.read().strip() != b.read().strip():
        err, text = call(mc.McpClient(TASKS_URL, DOCS_TOKEN, timeout=20), "list", {})
        check("the docs token does not open the tasks server", err is None and "unauthorised" in text, text)

# tasks
err, text = call(tasks, "list", {})
items = [t for t in rows(text) if t.get("title")]
check("tasks.list returns the open tasks (title, due, notes, ref)", err is False and len(items) >= MIN_TASKS and all(t.get("ref") for t in items),
      "%d task(s)" % len(items))
check("a task's notes are cut", all(len(t.get("notes") or "") <= 303 for t in items))

# the proof's fixtures: what n8n sent Google, and the edges of the flow
if STUB:
    log = json.load(urllib.request.urlopen(STUB, timeout=10))
    err, text = call(docs, "search", {"query": "O'Brien"})
    check("a quote in the query is escaped in Drive's q, and still finds the file", err is False and [h["id"] for h in rows(text)] == ["docB"], text[:120])
    err, text = call(docs, "search", {"query": "back\\slash"})
    check("a backslash in the query is escaped, and still finds the file", err is False and [h["id"] for h in rows(text)] == ["docB"], text[:120])
    err, text = call(docs, "search", {"query": "x' or name contains '"})
    check("a query that tries to break out of the q literal finds nothing (no 400 from Drive)", err is False and rows(text)[0].get("matches") == 0, text[:160])
    err, text = call(docs, "search", {"query": "pricing"})
    ids = [h["id"] for h in rows(text)]
    check("search finds the decisions doc too, and not the file outside the folder or the trashed one",
          "1uzHJ3t00ZdVsUlyLHQdYLo05z-Ugd5FnRLU8V4BW0os" in ids and "outside" not in ids and "trash" not in ids, ids)
    err, text = call(docs, "read", {"id": "1uzHJ3t00ZdVsUlyLHQdYLo05z-Ugd5FnRLU8V4BW0os"})
    check("docs.read reads the decisions doc", err is False and "pricing stays flat" in text, text[:100])
    err, text = call(docs, "read", {"id": "outside"})
    check("docs.read of a real file outside the folder is refused, naming the rule", err is True and "not in the documents folder" in text, text)
    err, text = call(docs, "read", {"id": "big"})
    d = (rows(text) or [{}])[0]
    check("docs.read cuts a long document at 60000 characters and says so", err is False and d.get("truncated") is True
          and "[cut:" in d.get("text", "") and 60000 < len(d["text"]) < 60200, len(d.get("text", "")))
    log = json.load(urllib.request.urlopen(STUB, timeout=10))
    qs = [e["query"]["q"] for e in log if e["path"] == "/drive/v3/files"]
    check("Drive's q was always: '<folder>' in parents and fullText contains '<escaped>' and trashed = false",
          qs and all(q.startswith("'19-16sCI6H6egNTbB1G6RJx6cdVdJnq5Q' in parents and fullText contains '") and q.endswith("' and trashed = false") for q in qs), qs[-3:])
    check("every Google call carried the credential's bearer token", log and all(e["auth"] for e in log), len(log))
    check("no call went to 'outside' (the gate refuses on the metadata, before any text)", not any(e["path"].endswith("/outside/export") or e["query"].get("alt") == "media" and "outside" in e["path"] for e in log))
    check("only the read endpoints were called (Drive files, Tasks list)", all(e["path"].startswith(("/drive/v3/files", "/tasks/v1/lists/")) for e in log))

print("%d of %d PASS" % (sum(results), len(results)))
sys.exit(0 if all(results) else 1)
