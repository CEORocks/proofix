#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, math, sys, time, urllib.error, urllib.request
THRESHOLDS={"http_5xx_rate_lt":0.001,"p95_latency_ms_lt":200.0,"consecutive_windows":3}
def hit(url: str) -> tuple[int,float]:
    started=time.perf_counter()
    try:
        with urllib.request.urlopen(url,timeout=1) as r: r.read(); status=r.status
    except urllib.error.HTTPError as e: status=e.code
    except OSError: status=0
    return status,(time.perf_counter()-started)*1000
def main() -> int:
    p=argparse.ArgumentParser(); p.add_argument("--base-url",default="http://127.0.0.1:30114"); p.add_argument("--requests",type=int,default=100); a=p.parse_args(); out=[]
    for w in range(1,4):
        rows=[hit(f"{a.base_url.rstrip('/')}/read?w={w}&n={n}") for n in range(a.requests)]; codes,lats=zip(*rows); ordered=sorted(lats)
        bad=sum(c!=200 for c in codes); fives=sum(500<=c<600 for c in codes); p95=ordered[math.ceil(.95*len(ordered))-1]; rate=fives/len(codes)
        out.append({"window":w,"http_5xx_rate":rate,"p95_latency_ms":p95,"failures":bad,"passed":bad==0 and rate<.001 and p95<200})
    result={"thresholds":THRESHOLDS,"windows":out,"passed":all(x["passed"] for x in out) and len(out)==3}; print(json.dumps(result,indent=2)); return 0 if result["passed"] else 1
if __name__=="__main__": sys.exit(main())
