"""Langfuse UI client (tRPC, logged in as the init admin) — what the UI itself calls."""
import http.cookiejar, json, os, urllib.parse, urllib.request
B = os.environ.get("LF_UI", "https://langfuse.tail6d0ed4.ts.net")
jar = http.cookiejar.CookieJar()
op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))

def login():
    csrf = json.load(op.open(B + "/api/auth/csrf"))["csrfToken"]
    data = urllib.parse.urlencode({"email": os.environ["LANGFUSE_INIT_USER_EMAIL"], "password": os.environ["LANGFUSE_INIT_USER_PASSWORD"],
                                   "csrfToken": csrf, "json": "true"}).encode()
    op.open(urllib.request.Request(B + "/api/auth/callback/credentials", data=data))

def trpc(proc, inp, mutation=True):
    if mutation:
        req = urllib.request.Request(f"{B}/api/trpc/{proc}?batch=1", data=json.dumps({"0": {"json": inp}}).encode(),
                                     headers={"Content-Type": "application/json"}, method="POST")
    else:
        q = urllib.parse.quote(json.dumps({"0": {"json": inp}}))
        req = urllib.request.Request(f"{B}/api/trpc/{proc}?batch=1&input={q}")
    try:
        r = json.load(op.open(req))[0]
    except urllib.error.HTTPError as e:
        r = json.loads(e.read())[0]
    if "error" in r:
        raise RuntimeError(json.dumps(r["error"]["json"].get("message"))[:3000])
    return r["result"]["data"]["json"]
