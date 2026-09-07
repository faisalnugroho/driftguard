#!/usr/bin/env python3
"""DriftGuard smoke RESUME — continue S2 determinism + S3 negative on the
LIVE contract 0xAc908C41B2326CE515a746292908BAc35f7AB6B6.

Lessons applied from the first run:
- check_watch has a 180s cooldown; retry only when the rollback payload is
  NOT cooldown_active, else sleep out the window.
- history check_id is a STRING — compare with int() casts.
- read AFTER finalized consensus can still race the indexer; re-read with
  a short retry loop.
- a consensus round with exec ERROR + rollback payload = contract guard
  fired (good), not a smoke failure.
"""
import json
import time
from pathlib import Path

from genlayer_py import create_client, create_account
from genlayer_py.chains import studionet
from genlayer_py.types import TransactionStatus

ADDR = "0xAc908C41B2326CE515a746292908BAc35f7AB6B6"
KEYFILE = Path("scripts/smoke_deployer.json")
LOG = Path("docs/deployment_log.json")

DETERMINISM_RUNS = 3   # total checks including the one already accepted
COOLDOWN_S = 180
POLL_S = 30


def load_account():
    data = json.loads(KEYFILE.read_text())
    return create_account(account_private_key=data["private_key"])


def wait_final(client, tx_hash, label, strict=True):
    last_err = None
    for _ in range(6):
        try:
            receipt = client.wait_for_transaction_receipt(
                transaction_hash=tx_hash,
                status=TransactionStatus.FINALIZED,
                retries=100, interval=3000)
            break
        except Exception as e:
            last_err = e
            print(f"  [{label}] rpc error: {str(e)[:150]} — backoff 15s",
                  flush=True)
            time.sleep(15)
    else:
        raise RuntimeError(f"{label} rpc failed: {last_err}")
    if isinstance(receipt, dict):
        leader = (receipt.get("consensus_data") or {}).get(
            "leader_receipt", [{}])
        lead = leader[0] if leader else {}
        exec_result = receipt.get("tx_execution_result_name") \
            or lead.get("execution_result")
        vote_result = receipt.get("result_name") or "UNKNOWN"
        res = (lead.get("result") or {})
        payload = str(res.get("payload") or "")[:120]
        stderr = str((lead.get("genvm_result") or {}).get("stderr") or "")
    else:
        exec_result, vote_result, payload, stderr = None, "UNKNOWN", "", ""
    print(f"  [{label}] vote={vote_result} exec={exec_result} "
          f"payload={payload}", flush=True)
    ok = (exec_result in (None, "SUCCESS", "FINISHED_WITH_RETURN")
          and vote_result == "MAJORITY_AGREE")
    guard = "rollback" in payload or "cooldown_active" in payload
    if not ok and not guard and strict:
        raise RuntimeError(f"{label}: vote={vote_result} exec={exec_result}")
    if stderr:
        print("STDERR tail:", stderr[-1200:], flush=True)
    return {"ok": ok, "guard": guard, "payload": payload,
            "vote": vote_result, "exec": exec_result}


def read_json(client, fn, args, retries=5):
    for i in range(retries):
        try:
            raw = client.read_contract(address=ADDR, function_name=fn,
                                       args=args)
            return json.loads(raw) if isinstance(raw, str) else raw
        except Exception as e:
            if i == retries - 1:
                raise
            time.sleep(5)
    return None


def history_len(client, wid):
    h = read_json(client, "get_history", [wid, 50, 0])
    recs = h.get("records", []) if isinstance(h, dict) else (h or [])
    return recs


def main():
    account = load_account()
    client = create_client(chain=studionet, account=account)
    log = json.loads(LOG.read_text()) if LOG.exists() else {}
    log.setdefault("resume_runs", [])

    def create(name, url, criteria):
        tx = client.write_contract(
            address=ADDR, function_name="create_watch",
            args=[name, url, criteria], account=client.local_account)
        wait_final(client, tx, f"create {name}")
        return int(read_json(client, "get_watch_count", []))

    # ---------------- S2: determinism — need 2 more accepted checks -------
    wid = 1
    verdicts = ["NO_CHANGE"]  # check#1 already accepted on-chain
    last_check_at = int(read_json(client, "get_watch", [wid])
                        .get("last_checked_at") or 0)
    while len(verdicts) < DETERMINISM_RUNS:
        w = read_json(client, "get_watch", [wid])
        elapsed = time.time() - max(last_check_at, 0)
        wait_s = COOLDOWN_S - elapsed + 10
        if wait_s > 0:
            print(f"cooldown: sleeping {wait_s:.0f}s…", flush=True)
            time.sleep(wait_s)
        tx = client.write_contract(
            address=ADDR, function_name="check_watch",
            args=[wid], account=client.local_account)
        r = wait_final(client, tx, f"check w{wid} v{len(verdicts)+1}",
                       strict=False)
        if r["guard"] and "cooldown_active" in r["payload"]:
            # sleep the reported remainder and retry
            try:
                remain = int(r["payload"].split(":")[1]) + 15
            except Exception:
                remain = 60
            print(f"  guard cooldown — sleeping {remain}s", flush=True)
            time.sleep(remain)
            continue
        # accepted? re-read history until a new record appears
        for _ in range(6):
            recs = history_len(client, wid)
            if len(recs) > len(verdicts) + 0 and \
                    recs[-1].get("classification") not in (None, ""):
                new = [x for x in recs
                       if x.get("classification") != "BASELINE_CREATED"]
                if len(new) >= len(verdicts) + 1:
                    last = new[-1]
                    verdicts.append(last.get("classification"))
                    last_check_at = int(last.get("checked_at") or 0)
                    print(f"  accepted: {last.get('classification')} "
                          f"(fp {last.get('current_fingerprint')})", flush=True)
                    log["resume_runs"].append({
                        "classification": last.get("classification"),
                        "tx": tx, "vote": r["vote"],
                        "fingerprint": last.get("current_fingerprint"),
                        "explanation": str(last.get("explanation"))[:200],
                    })
                    break
            time.sleep(8)
        else:
            print("  no new history record — retrying", flush=True)
    fam = {"NO_CHANGE", "MINOR_CHANGE"}
    ok_det = set(verdicts) <= fam
    log["s2_determinism"] = {"verdicts": verdicts,
                             "no_or_minor_family": ok_det}
    print("DETERMINISM:", ok_det, verdicts, flush=True)

    # ---------------- S3: negative — example.com + dead URL -------------
    neg_id = create("Empty Placeholder Page", "https://example.com/",
                    "Monitor pricing, fees, eligibility and deadlines.")
    tx = client.write_contract(
        address=ADDR, function_name="create_baseline", args=[neg_id],
        account=client.local_account)
    r_neg = wait_final(client, tx, f"baseline w{neg_id}", strict=False)
    w_neg = read_json(client, "get_watch", [neg_id])
    neg_fp = (w_neg.get("baseline") or {}).get("fingerprint")
    neg_latest = w_neg.get("latest_status")
    print(f"  example.com baseline: fp={'SET' if neg_fp else 'NONE'} "
          f"latest={neg_latest} payload={r_neg['payload']}", flush=True)

    dead_id = create("Dead URL",
                     "https://driftguard-nonexistent-e2e.invalid/404",
                     "Monitor pricing, fees, eligibility and deadlines.")
    tx = client.write_contract(
        address=ADDR, function_name="create_baseline", args=[dead_id],
        account=client.local_account)
    r_dead = wait_final(client, tx, f"baseline w{dead_id}", strict=False)
    w_dead = read_json(client, "get_watch", [dead_id])
    dead_latest = w_dead.get("latest_status")
    print(f"  dead-URL baseline: latest={dead_latest} "
          f"payload={r_dead['payload']}", flush=True)

    never_ok = ("NO_CHANGE" not in str(neg_latest)
                and "NO_CHANGE" not in str(dead_latest))
    log["s3_negative"] = {
        "example_com": {"id": neg_id, "baseline": bool(neg_fp),
                        "latest": neg_latest},
        "dead_url": {"id": dead_id, "latest": dead_latest},
        "never_no_change": never_ok,
    }
    print("NEGATIVE (never NO_CHANGE):", never_ok, flush=True)

    # ---------------- S4: views readback ----------------
    stats = read_json(client, "get_stats", [])
    hist = history_len(client, wid)
    log["s4_views"] = {"stats": stats,
                       "watch1_history": len(hist)}
    print("STATS:", json.dumps(stats), flush=True)
    print("watch#1 history records:", len(hist), flush=True)

    log["resume_done"] = True
    LOG.write_text(json.dumps(log, indent=2))
    print("DONE — log updated:", LOG, flush=True)


if __name__ == "__main__":
    main()
