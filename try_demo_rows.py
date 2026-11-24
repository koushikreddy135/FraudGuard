"""
Sends rows from demo_rows.json to the running service and prints what it decides.
Start the service first:  python -m uvicorn serve:app --port 8000
Then:                     python try_demo_rows.py
Saves every response to demo_results.json (use it for screenshots / the report).
"""
import json, sys, urllib.request

URL = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8001/score"
rows = json.load(open("demo_rows.json"))


def call(r):
    body = json.dumps({"amount": r["amount"], "features": r["features"]}).encode()
    req = urllib.request.Request(URL, data=body, headers={"content-type": "application/json"})
    return json.load(urllib.request.urlopen(req))


groups = {"normal": rows["normal"], "suspicious": rows["suspicious"],
          **{f"by_decision/{k}": v for k, v in rows["by_decision"].items()}}
saved = {}
print(f"{'group':20s} {'label':6s} {'amount':>12s} {'p':>7s}  decision")
for name, items in groups.items():
    for r in items[:3]:
        b = call(r)
        print(f"{name:20s} {r['label']:6s} {r['amount']:12,.0f} {b['fraud_probability']:7.4f}  {b['decision']}")
        saved.setdefault(name, []).append({"request": {"amount": r["amount"], "features": r["features"]}, "response": b})

json.dump(saved, open("demo_results.json", "w"), indent=1)
print("\nsaved demo_results.json")