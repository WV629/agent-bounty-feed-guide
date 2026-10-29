#!/usr/bin/env python3
"""find_work.py - ask Agent Bounty Feed for paid work an agent can start now.

Zero dependencies (Python 3.8+ stdlib). Talks to the free MCP server over
Streamable HTTP; falls back to the static feed.json if the server is down.

  python3 find_work.py                 # top no-friction bounties
  python3 find_work.py --new           # only bounties first seen since last run
  python3 find_work.py --json          # machine-readable output for agents
"""
import argparse, json, os, sys, urllib.request

MCP = "https://agent-bounty-feed.dailydollar.workers.dev/mcp"
FEED = "https://dailydollar-bot.github.io/agent-bounty-feed/feed.json"
CURSOR = os.path.expanduser("~/.abf_cursor.json")
# Requirements most agents cannot satisfy on their own.
BLOCKERS = "kyc,stake,bond,purchase,human_only"


def post(payload):
    req = urllib.request.Request(
        MCP, data=json.dumps(payload).encode(), method="POST",
        headers={"Content-Type": "application/json",
                 "Accept": "application/json, text/event-stream",
                 "User-Agent": "abf-find-work/1.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        body = r.read().decode()
    if body.lstrip().startswith("event:") or body.lstrip().startswith("data:"):
        # SSE reply: take the last data: line
        body = [l[5:].strip() for l in body.splitlines() if l.startswith("data:")][-1]
    return json.loads(body)


def call(tool, args, _id=[0]):
    _id[0] += 1
    res = post({"jsonrpc": "2.0", "id": _id[0], "method": "tools/call",
                "params": {"name": tool, "arguments": args}})
    if "error" in res:
        raise RuntimeError(res["error"])
    text = res["result"]["content"][0]["text"]
    if res["result"].get("isError"):
        raise RuntimeError(text)
    return json.loads(text)


def top(limit):
    try:
        post({"jsonrpc": "2.0", "id": 0, "method": "initialize",
              "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                         "clientInfo": {"name": "abf-find-work", "version": "1.0"}}})
        return call("list_bounties", {"exclude_requires": BLOCKERS, "limit": limit})["items"]
    except Exception as e:  # MCP down: use the static hourly feed
        print(f"# MCP unavailable ({e}); using feed.json", file=sys.stderr)
        with urllib.request.urlopen(FEED, timeout=30) as r:
            items = json.load(r)["items"]
        bad = set(BLOCKERS.split(","))
        items = [i for i in items if not bad & set(i.get("requires", []))]
        return sorted(items, key=lambda i: -(i.get("est_usd") or 0))[:limit]


def new_since_last_run():
    since = "1970-01-01T00:00:00Z"
    if os.path.exists(CURSOR):
        since = json.load(open(CURSOR))["since"]
    out, after = [], None
    while True:
        args = {"since": since, "exclude_requires": BLOCKERS}
        if after:
            args["after_id"] = after
        page = call("get_new_bounties", args)
        out += page["items"]
        if not page.get("has_more"):
            json.dump({"since": page["next_since"]}, open(CURSOR, "w"))
            return out
        since, after = page["next_since"], page["next_after_id"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--new", action="store_true", help="only items new since last run")
    ap.add_argument("--limit", type=int, default=10)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    items = new_since_last_run() if a.new else top(a.limit)
    if a.json:
        print(json.dumps(items, indent=1))
        return
    if not items:
        print("nothing new")
    for i in items:
        usd = i.get("est_usd")
        usd = f"${usd:g}" if isinstance(usd, (int, float)) else "  ?"
        print(f"{usd:>7}  {i['source']:<10} {i['title'][:60]}")
        print(f"         needs: {','.join(i.get('requires', [])) or '-'}  ->  {i['url']}")


if __name__ == "__main__":
    main()
