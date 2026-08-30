#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, subprocess, sys, time
NS="proofix-case-13"; PVC="ledger-data"
def get(*args: str) -> dict:
    return json.loads(subprocess.check_output(["kubectl","get",*args,"-o","json"],text=True))
def support() -> int:
    nodes=[n for n in get("nodes")["items"] if any(c["type"]=="Ready" and c["status"]=="True" for c in n["status"]["conditions"])]
    pvc=get("pvc",PVC,"-n",NS); sc_name=pvc["spec"]["storageClassName"]; sc=get("storageclass",sc_name); driver=sc["provisioner"]
    try: csi=get("csidriver",driver); attach=csi.get("spec",{}).get("attachRequired",True)
    except subprocess.CalledProcessError: attach=False
    reasons=[]
    if len(nodes)<2: reasons.append("requires at least two Ready Kubernetes nodes")
    if not attach: reasons.append(f"StorageClass provisioner {driver} has no attach-required CSIDriver")
    payload={"case_id":"CASE-13","status":"SUPPORTED" if not reasons else "UNSUPPORTED_INFRASTRUCTURE","ready_nodes":len(nodes),"storage_class":sc_name,"provisioner":driver,"attach_required":attach,"reasons":reasons}
    print(json.dumps(payload,sort_keys=True)); return 0 if not reasons else 3
def fault(timeout: int) -> int:
    pv=get("pvc",PVC,"-n",NS)["spec"]["volumeName"]
    end=time.time()+timeout
    while time.time()<end:
        events=get("events","-n",NS)["items"]; attachments=get("volumeattachments.storage.k8s.io")["items"]
        replacement_events=[e for e in events if e.get("involvedObject",{}).get("name")=="ledger-replacement"]
        messages=[e.get("message","") for e in replacement_events]
        reasons=[e.get("reason","") for e in replacement_events]
        relevant=[a for a in attachments if a.get("spec",{}).get("source",{}).get("persistentVolumeName")==pv]
        attachment_conflict=any(
            "multi-attach" in message.lower()
            or ("already" in message.lower() and "attach" in message.lower())
            or ("waiting for detach" in message.lower() and "already used" in message.lower())
            for message in messages
        ) or any(reason == "FailedAttachVolume" for reason in reasons)
        if attachment_conflict and relevant:
            print(json.dumps({"case_id":"CASE-13","status":"FAULT_VERIFIED","pv":pv,"events":messages,"event_reasons":reasons,"volumeattachments":relevant},sort_keys=True)); return 0
        time.sleep(2)
    print(json.dumps({"case_id":"CASE-13","status":"FAULT_NOT_OBSERVED","pv":pv},sort_keys=True)); return 1
def main() -> int:
    p=argparse.ArgumentParser(); p.add_argument("mode",choices=("support","fault")); p.add_argument("--timeout",type=int,default=90); a=p.parse_args()
    return support() if a.mode=="support" else fault(a.timeout)
if __name__=="__main__": sys.exit(main())
