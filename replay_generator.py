#!/usr/bin/env python3
"""
FraudGuard replay generator (SRS 3.2.1.3.11): streams historical PaySim transactions to the
Ingest API as individual HTTP POSTs, at a rate you can change while it runs.

Quick start
  python replay_generator.py --csv "Fraud detection Dataset.csv" --dry-run --limit 5     # just show payloads
  python replay_generator.py --csv ... --url http://localhost:8080/api/transactions --rate 200 --duration 60
  python replay_generator.py --csv ... --url ... --profile loadtest --nominal-rate 400    # SRS 3.3.1.6 profile

Rate profiles
  --rate N                constant N transactions/second (for --duration seconds, default: until data ends)
  --profile loadtest      nominal -> ramp up -> HOLD at 5x -> ramp down -> nominal (SRS section 4 load test)
  --control-file rate.txt change the rate LIVE: write a number into this file while the generator runs

Arrivals are Poisson (bursty, not metronome-regular), because uniform arrivals cannot show autoscaling.
Failed requests are retried with the SAME transactionId, so the Ingest API's idempotency is exercised.
Each second is written to replay_stats.csv for your latency / throughput charts.
"""
import argparse, asyncio, csv, hashlib, json, sys, time, uuid
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

# PaySim has no merchant category / channel, so we derive plausible ones from the transaction type.
TYPE_TO_MCC = {"TRANSFER": "4829", "CASH_OUT": "6011", "CASH_IN": "6010", "PAYMENT": "5999", "DEBIT": "6012"}
TYPE_TO_CHANNEL = {"TRANSFER": "MOBILE", "CASH_OUT": "ATM", "CASH_IN": "ATM", "PAYMENT": "ONLINE", "DEBIT": "CARD_PRESENT"}
MAX_AMOUNT = 10_000_000          # SRS 3.1.1 upper bound (minor currency units)
USECOLS = ["step", "type", "amount", "nameOrig", "nameDest", "oldbalanceOrg", "oldbalanceDest"]


# ----------------------------------------------------------------------------- payloads
def det_uuid4(seed, pass_no, row_no):
    """Deterministic UUID v4: the same row always gets the same id, so re-running = idempotent retry."""
    h = bytearray(hashlib.md5(f"{seed}:{pass_no}:{row_no}".encode()).digest())
    h[6] = (h[6] & 0x0F) | 0x40
    h[8] = (h[8] & 0x3F) | 0x80
    return str(uuid.UUID(bytes=bytes(h)))


def build_payload(r, pass_no, args):
    """r = (row_no, step, type, amount, nameOrig, nameDest, oldbalanceOrg, oldbalanceDest)"""
    row_no, step, typ, amount, orig, dest, bal_o, bal_d = r
    p = {
        "transactionId": det_uuid4(args.seed, pass_no, row_no),
        # The API only accepts timestamps within 24h in the past / 60s in the future, so we stamp "now".
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
        "customerId": orig,
        "merchantId": dest,
        "amount": int(round(amount)),
        "currency": args.currency,
        "merchantCategory": TYPE_TO_MCC[typ],
        "channel": TYPE_TO_CHANNEL[typ],
    }
    if args.schema == "extended":
        # Fields the trained model needs but the original 14-field schema does not carry.
        p["transactionType"] = typ
        p["senderBalance"] = float(bal_o)
        p["receiverBalance"] = float(bal_d)
    if args.include_step:
        p["replayStep"] = int(step)       # dataset hour index, in case the backend wants simulated time
    return p


def load_rows(args):
    df = pd.read_csv(args.csv, nrows=args.nrows, usecols=USECOLS)
    n0 = len(df)
    if args.types:
        df = df[df.type.isin(args.types.split(","))]
    bad = (df.amount <= 0) | (df.amount.round() > MAX_AMOUNT) | (df.amount.round() < 1)
    skipped = int(bad.sum())
    df = df[~bad].reset_index()                       # 'index' = original row number
    rows = list(zip(df["index"], df.step, df.type, df.amount, df.nameOrig, df.nameDest,
                    df.oldbalanceOrg, df.oldbalanceDest))
    if args.shard:
        i, n = (int(x) for x in args.shard.split("/"))
        rows = rows[i::n]
    print(f"loaded {n0:,} rows -> {len(rows):,} to replay "
          f"({skipped:,} skipped: amount outside 1..{MAX_AMOUNT:,})", file=sys.stderr)
    return rows


# ----------------------------------------------------------------------------- rate schedule
def make_schedule(args):
    r, m = args.nominal_rate if args.profile == "loadtest" else args.rate, args.burst_mult
    if args.profile == "loadtest":
        stages = [("nominal", args.t_nominal, r, r), ("ramp-up", args.t_ramp, r, r * m),
                  ("burst", args.t_hold, r * m, r * m), ("ramp-down", args.t_ramp, r * m, r),
                  ("nominal", args.t_nominal, r, r)]
    else:
        stages = [("constant", args.duration if args.duration else float("inf"), r, r)]
    total = sum(s[1] for s in stages)

    def rate_at(t):
        acc = 0.0
        for name, dur, a, b in stages:
            if t < acc + dur:
                return name, a + (b - a) * ((t - acc) / dur if dur not in (0, float("inf")) else 0)
            acc += dur
        return None
    return rate_at, total


def read_control(path, current):
    try:
        v = float(Path(path).read_text().strip())
        return v if v >= 0 else current
    except Exception:
        return current


# ----------------------------------------------------------------------------- stats
class Stats:
    def __init__(self):
        self.sent = self.ok = self.rejected = self.failed = self.retries = self.skipped_late = 0
        self.throttled = self.abandoned = 0
        self.codes = {}
        self.lat = []                       # (second, latency_ms) for successful requests
        self.sec = {}                       # second -> [target, sent, ok, err]

    def bucket(self, s):
        return self.sec.setdefault(s, [0.0, 0, 0, 0])

    def pct(self, lo, hi, q):
        v = [l for s, l in self.lat if lo <= s < hi]
        return float(np.percentile(v, q)) if v else float("nan")


async def send(session, url, payload_fn, args, stats, t0):
    import aiohttp
    payload = payload_fn()
    body = json.dumps(payload)
    stats.sent += 1
    stats.bucket(int(time.monotonic() - t0))[1] += 1
    for attempt in range(args.retries + 1):
        start = time.monotonic()
        try:
            async with session.post(url, data=body) as resp:
                code = resp.status
                await resp.read()
                stats.codes[code] = stats.codes.get(code, 0) + 1
                if code in (200, 202):
                    ms = (time.monotonic() - start) * 1000
                    s = int(time.monotonic() - t0)
                    stats.ok += 1
                    stats.lat.append((s, ms))
                    stats.bucket(s)[2] += 1
                    return
                if code in (400, 401, 403, 409, 422):           # our fault: retrying will not help
                    stats.rejected += 1
                    stats.bucket(int(time.monotonic() - t0))[3] += 1
                    return
                if code == 429:
                    await asyncio.sleep(float(resp.headers.get("Retry-After", 1)))
        except (aiohttp.ClientError, asyncio.TimeoutError):
            stats.codes["conn/timeout"] = stats.codes.get("conn/timeout", 0) + 1
        except Exception as e:                       # never let one bad request kill the run
            stats.codes[type(e).__name__] = stats.codes.get(type(e).__name__, 0) + 1
        if attempt < args.retries:
            stats.retries += 1
            await asyncio.sleep(min(0.1 * 2 ** attempt, 2.0))     # bounded exponential backoff
    stats.failed += 1
    stats.bucket(int(time.monotonic() - t0))[3] += 1


async def run(args, rows):
    import aiohttp
    rng = np.random.default_rng(args.seed)
    rate_at, total = make_schedule(args)
    stats = Stats()
    headers = {"Content-Type": "application/json"}
    if args.token:
        headers["Authorization"] = f"Bearer {args.token}"
    conn = aiohttp.TCPConnector(limit=args.concurrency, ttl_dns_cache=300)
    timeout = aiohttp.ClientTimeout(total=args.timeout)
    pending, idx, pass_no, carry, override = set(), 0, 0, 0.0, None
    last_report, last_sent = 0.0, 0

    print(f"{'t(s)':>6} {'stage':>10} {'target/s':>9} {'sent/s':>8} {'ok':>8} {'rej':>5} {'fail':>5} "
          f"{'inflight':>8} {'p50ms':>7} {'p95ms':>7} {'p99ms':>7}", file=sys.stderr)
    async with aiohttp.ClientSession(connector=conn, headers=headers, timeout=timeout) as session:
        t0 = time.monotonic()
        next_tick = t0
        exhausted = False
        try:
            while not exhausted:
                t = time.monotonic() - t0
                sched = rate_at(t)
                if sched is None:
                    break
                stage, rate = sched
                if args.control_file:
                    override = read_control(args.control_file, override)
                    if override is not None:
                        stage, rate = "override", override
                stats.bucket(int(t))[0] = rate
                expect = rate * args.tick + carry
                n = int(rng.poisson(rate * args.tick)) if args.poisson else int(expect)
                carry = 0.0 if args.poisson else expect - n
                # Back-pressure: if the server is not keeping up, do NOT pile up unlimited requests.
                room = max(args.max_inflight - len(pending), 0)
                if n > room:
                    stats.throttled += n - room
                    n = room
                for _ in range(n):
                    if idx >= len(rows):
                        if args.loop:
                            idx, pass_no = 0, pass_no + 1
                        else:
                            exhausted = True
                            break
                    r = rows[idx]; idx += 1
                    task = asyncio.create_task(send(session, args.url, lambda r=r, p=pass_no: build_payload(r, p, args),
                                                    args, stats, t0))
                    pending.add(task); task.add_done_callback(pending.discard)
                next_tick += args.tick
                delay = next_tick - time.monotonic()
                if delay > 0:
                    await asyncio.sleep(delay)
                elif delay < -1.0:
                    stats.skipped_late += 1
                    next_tick = time.monotonic()              # generator itself is too slow: do not spiral
                if t - last_report >= args.report_every:
                    lo = int(last_report)
                    hi = int(t)
                    print(f"{t:6.0f} {stage:>10} {rate:9.0f} {(stats.sent - last_sent) / max(t - last_report, 1e-9):8.0f} "
                          f"{stats.ok:8d} {stats.rejected:5d} {stats.failed:5d} {len(pending):8d} "
                          f"{stats.pct(lo, hi, 50):7.1f} {stats.pct(lo, hi, 95):7.1f} {stats.pct(lo, hi, 99):7.1f}",
                          file=sys.stderr)
                    last_report, last_sent = t, stats.sent
            if pending:                                       # let in-flight requests finish (bounded wait)
                await asyncio.wait(pending, timeout=args.timeout + 5)
        finally:
            # Always cancel whatever is left BEFORE the session closes (also on Ctrl+C), so nothing
            # tries to use a closed session.
            leftovers = [t for t in pending if not t.done()]
            stats.abandoned += len(leftovers)
            for t in leftovers:
                t.cancel()
            if leftovers:
                await asyncio.gather(*leftovers, return_exceptions=True)
        elapsed = time.monotonic() - t0
    return stats, elapsed


def summarize(stats, elapsed, args):
    print("\n" + "=" * 62 + "\nREPLAY SUMMARY\n" + "=" * 62, file=sys.stderr)
    print(f"duration            {elapsed:.1f}s", file=sys.stderr)
    print(f"sent                {stats.sent:,}   ({stats.sent / elapsed:,.0f}/s average)", file=sys.stderr)
    print(f"accepted (200/202)  {stats.ok:,}", file=sys.stderr)
    print(f"rejected (4xx)      {stats.rejected:,}", file=sys.stderr)
    print(f"failed after retry  {stats.failed:,}   (retries used: {stats.retries:,})", file=sys.stderr)
    print(f"response codes      {stats.codes}", file=sys.stderr)
    if stats.lat:
        v = [l for _, l in stats.lat]
        print(f"ingest latency ms   p50 {np.percentile(v, 50):.1f}   p95 {np.percentile(v, 95):.1f}   "
              f"p99 {np.percentile(v, 99):.1f}   max {max(v):.1f}", file=sys.stderr)
    if stats.throttled or stats.abandoned:
        print(f"throttled           {stats.throttled:,} requests were NOT sent because {args.max_inflight:,} were already in flight; "
              f"{stats.abandoned:,} still unfinished at the end were cancelled", file=sys.stderr)
        print("WARNING: the server could not keep up with the target rate. Lower --rate / --nominal-rate, "
              "or test against a faster server.", file=sys.stderr)
    if stats.skipped_late:
        print(f"WARNING: generator fell behind {stats.skipped_late} times; it may be the bottleneck. "
              "Run two copies with --shard 0/2 and --shard 1/2 at half the rate each.", file=sys.stderr)
    with open(args.stats_csv, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["second", "target_rate", "sent", "accepted", "errors", "p50_ms", "p95_ms", "p99_ms"])
        for s in sorted(stats.sec):
            tr, sent, ok, err = stats.sec[s]
            w.writerow([s, f"{tr:.1f}", sent, ok, err, f"{stats.pct(s, s + 1, 50):.2f}",
                        f"{stats.pct(s, s + 1, 95):.2f}", f"{stats.pct(s, s + 1, 99):.2f}"])
    print(f"per-second stats    {args.stats_csv}", file=sys.stderr)


# ----------------------------------------------------------------------------- main
def parse():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--csv", required=True, help="PaySim csv")
    ap.add_argument("--nrows", type=int, default=None)
    ap.add_argument("--url", default="http://localhost:8080/api/transactions")
    ap.add_argument("--token", default=None, help="Bearer token if the API requires one")
    ap.add_argument("--rate", type=float, default=100, help="transactions/second (constant mode)")
    ap.add_argument("--duration", type=float, default=None, help="seconds (constant mode); default until data ends")
    ap.add_argument("--profile", choices=["constant", "loadtest"], default="constant")
    ap.add_argument("--nominal-rate", type=float, default=100, help="loadtest: nominal tx/s (peak = this x burst-mult)")
    ap.add_argument("--burst-mult", type=float, default=5, help="loadtest: burst = nominal x this (SRS: 5)")
    ap.add_argument("--t-nominal", type=float, default=60, help="loadtest: seconds at nominal (start and end)")
    ap.add_argument("--t-ramp", type=float, default=30, help="loadtest: seconds ramping up and down")
    ap.add_argument("--t-hold", type=float, default=60, help="loadtest: seconds held at the burst rate (SRS: >= 60)")
    ap.add_argument("--control-file", default=None, help="file containing a tx/s number; edit it to change rate live")
    ap.add_argument("--poisson", dest="poisson", action="store_true", default=True)
    ap.add_argument("--uniform", dest="poisson", action="store_false", help="evenly spaced arrivals instead of Poisson")
    ap.add_argument("--loop", action="store_true", help="start over when the data ends (new ids per pass)")
    ap.add_argument("--types", default=None, help="e.g. TRANSFER,CASH_OUT (default: all types, so history is complete)")
    ap.add_argument("--schema", choices=["extended", "strict"], default="extended",
                    help="extended adds transactionType/senderBalance/receiverBalance that the model needs")
    ap.add_argument("--include-step", action="store_true", help="add replayStep (dataset hour) to each payload")
    ap.add_argument("--currency", default="INR")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--shard", default=None, help="i/n: replay only every n-th row (run n generators in parallel)")
    ap.add_argument("--concurrency", type=int, default=500, help="max simultaneous HTTP connections")
    ap.add_argument("--max-inflight", type=int, default=2000,
                    help="max requests waiting for a response; above this the generator throttles itself")
    ap.add_argument("--retries", type=int, default=3)
    ap.add_argument("--timeout", type=float, default=10)
    ap.add_argument("--tick", type=float, default=0.05, help="scheduling granularity in seconds")
    ap.add_argument("--report-every", type=float, default=5)
    ap.add_argument("--stats-csv", default="replay_stats.csv")
    ap.add_argument("--dry-run", action="store_true", help="print payloads, send nothing")
    ap.add_argument("--limit", type=int, default=5, help="dry-run: how many payloads to print")
    return ap.parse_args()


def main():
    args = parse()
    rows = load_rows(args)
    if not rows:
        sys.exit("No rows to replay.")
    if args.dry_run:
        for r in rows[:args.limit]:
            print(json.dumps(build_payload(r, 0, args), indent=2))
        return
    try:
        import aiohttp  # noqa: F401
    except ImportError:
        sys.exit("aiohttp is required: pip install aiohttp")
    try:
        stats, elapsed = asyncio.run(run(args, rows))
    except KeyboardInterrupt:
        sys.exit("\nStopped by user (Ctrl+C). In-flight requests were cancelled cleanly.")
    summarize(stats, elapsed, args)


if __name__ == "__main__":
    main()