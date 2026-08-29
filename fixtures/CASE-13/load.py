#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,math,sys,time,urllib.error,urllib.request
T={"http_5xx_rate_lt":0.001,"p95_latency_ms_lt":200.0,"consecutive_windows":3}
def hit(u: str)->tuple[int,float]:
 s=time.perf_counter()
 try:
  with urllib.request.urlopen(u,timeout=1) as r:r.read();c=r.status
 except urllib.error.HTTPError as e:c=e.code
 except OSError:c=0
 return c,(time.perf_counter()-s)*1000
def main()->int:
 p=argparse.ArgumentParser();p.add_argument("--base-url",default="http://127.0.0.1:30113");p.add_argument("--requests",type=int,default=100);a=p.parse_args();ws=[]
 for w in range(1,4):
  rows=[hit(f"{a.base_url.rstrip('/')}/ledger?w={w}&n={n}") for n in range(a.requests)];cs,ls=zip(*rows);p95=sorted(ls)[math.ceil(.95*len(ls))-1];f=sum(500<=c<600 for c in cs);bad=sum(c!=200 for c in cs);rate=f/len(cs);ws.append({"window":w,"http_5xx_rate":rate,"p95_latency_ms":p95,"failures":bad,"passed":bad==0 and rate<.001 and p95<200})
 out={"thresholds":T,"windows":ws,"passed":len(ws)==3 and all(w["passed"] for w in ws)};print(json.dumps(out,indent=2));return 0 if out["passed"] else 1
if __name__=="__main__":sys.exit(main())
