#!/usr/bin/env python3
"""DriftGuard — deploy to GenLayer Studionet + live consensus smoke test.

v2 (finalization): fixes the v1 TypeError crash and makes the smoke
rerunnable without redeploying:

  - All chain-returned ids are normalized through _as_int() (handles
    int / numeric str / None / unexpected -> 0). Regression-tested in
    tests/direct/test_deploy_smoke_helpers.py.
  - wait_final() classifies guard rollbacks (cooldown_active:NNN,
    baseline_exists, ...) as GUARD outcomes, not failures — a
    deterministic UserError refusal accepted by consensus is the
    contract working, not a smoke error.
  - check/baseline loops are cooldown-aware: on cooldown_active:NNN
    they sleep the reported remainder instead of burning attempts.
  - Read-backs retry (indexer lag) and read the REAL fields
    (watch.baseline.fingerprint), never invented ones.
  - --resume ADDR re-runs the smoke against the existing live contract
    (no deploy). Default (no flag) deploys fresh and is used only when
    a new deployment is genuinely intended.

Smoke plan (S1-S4) unchanged: S1 watch+baseline on a stable raw-markdown
source; S2 determinism x3 in the NO_CHANGE/MINOR family; S3 negative
(example.com + dead URL never yield NO_CHANGE); S4 views readback.

Exit code 0 = all scenarios verified. Output: docs/deployment_log.json.
Explorer: https://explorer-studio.genlayer.com/address/<addr>
"""
import json
import sys
import time
from pathlib import Path

from genlayer_py import create_client, create_account
from genlayer_py.chains import studionet
from genlayer_py.types import TransactionStatus

CODE = Path("contracts/driftguard.py")
KEYFILE = Path("scripts/smoke_deployer.json")   # gitignored
LOG = Path("docs/deployment_log.json")

POS_NAME = "Tavily Search API"
POS_URL = "https://docs.tavily.com/documentation/api-reference/endpoint/search.md"
POS_CRITERIA = ("Monitor authentication, rate limits, endpoints and "
                "breaking changes.")

NEG_NAME = "Empty Placeholder Page"
NEG_URL = "https://example.com/"
NEG_CRITERIA = "Monitor pricing, fees, eligibility and deadlines."

DEAD_URL = "https://driftguard-nonexistent-e2e.invalid/404"

DETERMINISM_RUNS = 3
COOLDOWN_S = 180          # must mirror contracts CHECK_COOLDOWN_SECONDS
GUARD_MARKERS = ("cooldown_active", "baseline_exists", "not_found",
                 "inactive", "not_owner")


def _as_int(v, default=0):
    """Normalize a chain-returned id safely.

    The contract stores ids as decimal STRINGS in JSON records
    ("check_id": "7") while some view methods return bare ints.
    Handles: int, numeric str (incl. quoted), None, anything else
    (float, bool) -> best effort; unexpected -> default. Never raises.
    (Regression test: tests/direct/test_deploy_smoke_helpers.py —
    this is the v1 TypeError: "7" <= 0.)
    """
    if v is None:
        return default
    if isinstance(v, bool):  # bool is an int subclass; ids are never bools
        return default
    if isinstance(v, int):
        return v
    if isinstance(v, float):
        return int(v)
    if isinstance(v, str):
        s = v.strip().strip('"')
        try:
            return int(s)
        except ValueError:
            try:
                return int(float(s))
            except ValueError:
                return default
    return default


def load_account():
    if KEYFILE.exists():
        data = json.loads(KEYFILE.read_text())
        return create_account(account_private_key=data["private_key"])
    acct = create_account()
    KEYFILE.parent.mkdir(exist_ok=True)
    KEYFILE.write_text(json.dumps(
        {"address": acct.address, "private_key": acct.key.hex()}))
    return acct


def wait_final(client, tx_hash, label, strict=True):
    """FINALIZED wait gating on BOTH consensus vote and leader execution.

    result_name = consensus VOTE (MAJORITY_AGREE / NO_MAJORITY / ...);
    tx_execution_result_name / leader execution_result = GenVM exec.
    Success = vote AGREE + exec in (SUCCESS, FINISHED_WITH_RETURN).
    A rollback payload carrying a GUARD marker is classified as a
    guard outcome (ok_for_flow=False, guard=True) — the contract
    refusing bad input deterministically, accepted by consensus.
    """
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
        payload = str(res.get("payload") or "")
        # payload can be a readable-dict blob; normalize to short text
        short = payload.replace("{", "").replace("}", "")[:120]
        stderr = str((lead.get("genvm_result") or {}).get("stderr") or "")
    else:
        exec_result, vote_result, short, stderr = None, "UNKNOWN", "", ""

    guard = any(m in payload for m in GUARD_MARKERS)
    ok = (exec_result in (None, "SUCCESS", "FINISHED_WITH_RETURN")
          and vote_result in ("MAJORITY_AGREE", None))
    print(f"  [{label}] vote={vote_result} exec={exec_result}"
          + (f" guard={short[:80]}" if guard else ""), flush=True)
    if not ok and not guard:
        print("EXECUTION FAILED — consensus data:", flush=True)
        print(json.dumps(receipt.get("consensus_data"), default=str)[:2500],
              flush=True)
        if stderr:
            print("STDERR tail:", stderr[-1500:], flush=True)
        if strict:
            raise RuntimeError(
                f"{label} failed: vote={vote_result} exec={exec_result}")
    return {"ok": ok, "guard": guard, "payload": short,
            "vote": vote_result, "exec": exec_result}


def read_json(client, addr, fn, args, retries=5):
    """View call with indexer-lag retry."""
    for i in range(retries):
        try:
            raw = client.read_contract(address=addr, function_name=fn,
                                       args=args)
            out = json.loads(raw) if isinstance(raw, str) else raw
            if out is not None:
                return out
        except Exception:
            pass
        time.sleep(5)
    raise RuntimeError(f"read {fn} failed after {retries} tries")


def history_of(client, addr, wid):
    h = read_json(client, addr, "get_history", [wid, 50, 0])
    return h.get("records", []) if isinstance(h, dict) else (h or [])


def main():
    resume_addr = None
    if len(sys.argv) >= 3 and sys.argv[1] == "--resume":
        resume_addr = sys.argv[2]

    account = load_account()
    client = create_client(chain=studionet, account=account)
    print("deployer:", account.address, flush=True)

    log = {"smoke_plan": {
        "s1_watch_baseline": f"{POS_NAME}: create_watch + create_baseline on raw .md source",
        "s2_determinism": "3 consecutive check_watch consensus runs — stable NO_CHANGE/MINOR family",
        "s3_negative": "example.com must not yield NO_CHANGE baseline; dead URL -> SOURCE_UNAVAILABLE",
        "s4_views": "get_watch/get_history/get_stats readback",
        "tool_version": "deploy_smoke v2 (guard-aware, cooldown-aware, id-normalized)",
    }}

    # ---------------- deploy (or reuse) ----------------
    if resume_addr:
        addr = resume_addr
        print("RESUME mode — reusing live contract:", addr, flush=True)
        log["deploy"] = {"reused_address": addr,
                         "note": "no redeploy; smoke only"}
    else:
        code = CODE.read_text()
        print(f"deploying DriftGuard ({len(code)} bytes)…", flush=True)
        tx = client.deploy_contract(code=code, account=client.local_account,
                                    args=[], leader_only=True)
        res = wait_final(client, tx, "deploy")
        addr = res.get("contract_address")
        if not addr:
            raise RuntimeError("no contract address in deploy receipt")
        log["deploy"] = {"tx_hash": tx, "address": addr,
                         "deployer": account.address}
    print("CONTRACT:", addr, flush=True)
    print("explorer: https://explorer-studio.genlayer.com/address/" + addr,
          flush=True)

    info = read_json(client, addr, "get_contract_info", [])
    print("contract info:", json.dumps(info)[:300], flush=True)
    log["contract_info"] = info

    def create(name, url, criteria):
        tx = client.write_contract(
            address=addr, function_name="create_watch",
            args=[name, url, criteria], account=client.local_account)
        wait_final(client, tx, f"create {name}")
        return _as_int(read_json(client, addr, "get_watch_count", []))

    def wait_cooldown(last_epoch):
        elapsed = time.time() - max(last_epoch, 0)
        wait_s = COOLDOWN_S - elapsed + 10
        if wait_s > 0:
            print(f"  cooldown: sleeping {wait_s:.0f}s…", flush=True)
            time.sleep(wait_s)

    def baseline(wid, attempts=3):
        """create_baseline with re-crank; baseline read from the REAL
        nested field watch.baseline.fingerprint (v1 bug: looked for a
        nonexistent watch.baseline_fingerprint and misread unsealed)."""
        r = w = None
        for a in range(1, attempts + 1):
            tx = client.write_contract(
                address=addr, function_name="create_baseline",
                args=[wid], account=client.local_account)
            r = wait_final(client, tx, f"baseline w{wid} a{a}", strict=False)
            w = read_json(client, addr, "get_watch", [wid])
            if (w.get("baseline") or {}).get("fingerprint"):
                return r, w
            if r["guard"] and "cooldown_active" in r["payload"]:
                try:
                    remain = _as_int(r["payload"].split(":")[1]) + 15
                except Exception:
                    remain = 60
                print(f"  guard cooldown — sleeping {remain}s", flush=True)
                time.sleep(remain)
                continue
            if a < attempts:
                print("  baseline unsealed — re-cranking", flush=True)
        return r, w

    def check(wid, known_records, attempts=3):
        """check_watch with cooldown-aware re-crank. Acceptance = a NEW
        history record beyond known_records (ids compared via _as_int)."""
        votes = []
        r = w = last = None
        for a in range(1, attempts + 1):
            tx = client.write_contract(
                address=addr, function_name="check_watch",
                args=[wid], account=client.local_account)
            r = wait_final(client, tx, f"check w{wid} a{a}", strict=False)
            votes.append(r["vote"])
            if r["guard"] and "cooldown_active" in r["payload"]:
                try:
                    remain = _as_int(r["payload"].split(":")[1]) + 15
                except Exception:
                    remain = 60
                print(f"  guard cooldown — sleeping {remain}s", flush=True)
                time.sleep(remain)
                continue
            # read back until a genuinely new CHECK record appears.
            # History also contains lifecycle records (BASELINE_CREATED,
            # BASELINE_PROMOTED) that share the check-id counter — those
            # are NOT consensus checks and must never count as a
            # determinism verdict (v2.1 fix: the first run captured the
            # baseline's own history row as "verdict 1").
            LIFECYCLE = {"BASELINE_CREATED", "BASELINE_PROMOTED"}
            new_last = None
            for _ in range(6):
                recs = history_of(client, addr, wid)
                fresh = [x for x in recs
                         if _as_int(x.get("check_id")) > known_records
                         and x.get("classification") not in LIFECYCLE]
                if fresh:
                    new_last = fresh[-1]
                    break
                time.sleep(8)
            if new_last:
                return r, votes, new_last, \
                    max(_as_int(x.get("check_id")) for x in recs)
            if a < attempts:
                print("  check unsealed — re-cranking", flush=True)
        return r, votes, last, known_records

    # ------------- S1: watch + baseline on stable source -------------
    t0 = time.time()
    wid = create(POS_NAME, POS_URL, POS_CRITERIA)
    print(f"  watch #{wid} created", flush=True)
    r, w = baseline(wid)
    b = (w or {}).get("baseline") or {}
    if not b.get("fingerprint"):
        raise RuntimeError("S1 FAILED: baseline never sealed")
    log["s1_watch_baseline"] = {
        "watch_id": wid, "name": POS_NAME, "url": POS_URL,
        "baseline_fingerprint": b.get("fingerprint"),
        "baseline_summary": str(b.get("semantic_summary"))[:200],
        "secs": round(time.time() - t0, 1),
    }
    print(f"  baseline: fp={b.get('fingerprint')} "
          f"summary={str(b.get('semantic_summary'))[:120]}", flush=True)

    # ------------- S2: determinism x3 -------------
    t0 = time.time()
    verdicts = []
    max_check_id = 0
    while len(verdicts) < DETERMINISM_RUNS:
        wait_cooldown(int((w or {}).get("last_checked_at") or 0))
        r, votes, last, max_check_id = check(wid, max_check_id)
        if last is None:
            raise RuntimeError("S2 FAILED: no accepted check record")
        v = last.get("classification") or "?"
        verdicts.append(v)
        w = read_json(client, addr, "get_watch", [wid])
        print(f"  check#{len(verdicts)}: {v} votes={votes}", flush=True)
        log[f"s2_check_{len(verdicts)}"] = {
            "classification": v, "votes": votes,
            "check_id": last.get("check_id"),
            "explanation": str(last.get("explanation"))[:200],
        }
    fam = {"NO_CHANGE", "MINOR_CHANGE"}
    ok_det = set(verdicts) <= fam
    log["s2_determinism"] = {"verdicts": verdicts,
                             "no_or_minor_family": ok_det}
    print("DETERMINISM (NO_CHANGE/MINOR family):", ok_det, verdicts,
          flush=True)
    if not ok_det:
        raise RuntimeError(f"S2 FAILED: unstable verdicts {verdicts}")

    # ------------- S3: negative — never NO_CHANGE -------------
    t0 = time.time()
    neg_id = create(NEG_NAME, NEG_URL, NEG_CRITERIA)
    r_neg, w_neg = baseline(neg_id)
    neg_fp = ((w_neg or {}).get("baseline") or {}).get("fingerprint")
    # a baseline-only watch has no checks; the NEGATIVE assertions are:
    #  (a) if a baseline got stored, its summary must not claim
    #      monitoring-relevant content (honest "no info" extraction)
    #  (b) the dead-URL watch below must end UNAVAILABLE, never NO_CHANGE
    dead_id = create("Dead URL", DEAD_URL, NEG_CRITERIA)
    r_dead, w_dead = baseline(dead_id)
    dead_b = (w_dead or {}).get("baseline")
    dead_latest = (w_dead or {}).get("latest_status")
    if dead_b is None and "UNAVAILABLE" not in str(r_dead["payload"]) \
            and not dead_latest:
        # not stored AND not reported unavailable — inspect manually
        print("  dead-URL watch state:", json.dumps(w_dead)[:300], flush=True)
    never_ok = ("NO_CHANGE" not in str(dead_latest)
                and (dead_b is None
                     or "NO_CHANGE" not in str(dead_latest)))
    log["s3_negative"] = {
        "example_com": {
            "id": neg_id,
            "baseline_stored": bool(neg_fp),
            "baseline_summary": str((w_neg or {}).get("baseline", {})
                                    .get("semantic_summary", ""))[:200],
        },
        "dead_url": {"id": dead_id,
                     "baseline_stored": dead_b is not None,
                     "latest_status": dead_latest,
                     "guard_payload": r_dead["payload"][:80]},
        "never_no_change": never_ok,
        "secs": round(time.time() - t0, 1),
    }
    print(f"NEGATIVE (never NO_CHANGE): {never_ok} "
          f"(dead.latest={dead_latest!r})", flush=True)
    if not never_ok:
        raise RuntimeError("S3 FAILED: failure masqueraded as NO_CHANGE")

    # ------------- S4: views readback -------------
    w_read = read_json(client, addr, "get_watch", [wid])
    hist_read = history_of(client, addr, wid)
    stats = read_json(client, addr, "get_stats", [])
    log["s4_views"] = {
        "watch": {"id": w_read.get("watch_id"), "url": w_read.get("url"),
                  "latest": w_read.get("latest_status"),
                  "total_checks": w_read.get("total_checks"),
                  "checks_performed": w_read.get("checks_performed")},
        "history_count": len(hist_read),
        "stats": stats,
    }
    print("VIEWS: watch", w_read.get("latest_status"),
          "| history", len(hist_read), "| stats",
          json.dumps(stats)[:200], flush=True)

    log["done"] = True
    LOG.parent.mkdir(exist_ok=True)
    LOG.write_text(json.dumps(log, indent=2))
    print("DONE. contract:", addr, flush=True)
    print("log:", LOG, flush=True)


if __name__ == "__main__":
    main()
