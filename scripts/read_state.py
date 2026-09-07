#!/usr/bin/env python3
"""Read live DriftGuard contract state directly from Studionet.

Verifies the actual on-chain state after the smoke run: watch #1 baseline
fingerprint, latest classification, history records, stats. Read-only.
"""
import json
import sys
from pathlib import Path

from genlayer_py import create_client, create_account
from genlayer_py.chains import studionet

ADDR = sys.argv[1] if len(sys.argv) > 1 else "0xAc908C41B2326CE515a746292908BAc35f7AB6B6"
KEYFILE = Path("scripts/smoke_deployer.json")


def main():
    data = json.loads(KEYFILE.read_text())
    account = create_account(account_private_key=data["private_key"])
    client = create_client(chain=studionet, account=account)

    def rj(fn, args):
        raw = client.read_contract(address=ADDR, function_name=fn, args=args)
        return json.loads(raw) if isinstance(raw, str) else raw

    print("contract:", ADDR)
    cnt = rj("get_watch_count", [])
    print("watch_count:", cnt)
    stats = rj("get_stats", [])
    print("stats:", json.dumps(stats, indent=2)[:800])
    for wid in range(1, int(cnt) + 1):
        w = rj("get_watch", [wid])
        print(f"\n--- watch #{wid} ---")
        print(json.dumps(w, indent=2)[:1200])
        hist = rj("get_history", [wid, 50, 0])
        recs = hist.get("records", []) if isinstance(hist, dict) else hist
        print(f"history ({len(recs)}):")
        for rec in recs:
            print(" ", json.dumps(rec)[:400])


if __name__ == "__main__":
    main()
