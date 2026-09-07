"""DriftGuard direct-mode test suite.

Covers the full spec matrix + adversarial cases + validator-equivalence
semantics + deterministic-contract unit tests:

  Watch creation: valid registration, invalid URL schemes (file://,
    javascript:, data:), empty name/criteria, private/SSRF hosts,
    length bounds, ownership binding.
  Baseline: creation, immutable history entry, double-baseline
    refused, owner-only, unavailable source -> no baseline,
    empty page -> no baseline.
  Checks: NO_CHANGE, MINOR_CHANGE, MATERIAL_CHANGE (30->14 days),
    SOURCE_UNAVAILABLE (404/500/network), UNCERTAIN (empty page,
    malformed LLM), reworded "thirty (30) days" -> NO_CHANGE,
    cooldown enforcement, history append + counters.
  Baseline policy: baseline does NOT move after MATERIAL_CHANGE;
    promote_baseline (owner-only) moves it; check after promote tracks
    against the NEW baseline.
  Access control: deactivate/activate/update_criteria owner-only.
  Validator semantics (run_validator tamper tests): well-formed lies
    rejected, classification matrix exactness, baseline-integrity
    agreement, prompt injection resistance.
  Deterministic units: _strip_html, _canon_topic/_canon_value,
    _topic_match, _fnv1a, _fingerprint, _parse_iso_epoch, matrix.
"""
import json

import pytest

import helpers as H
from helpers import (
    CONTRACT, WATCH_URL, POLICY_30D, POLICY_14D, POLICY_30D_REWORDED,
    POLICY_MINOR, EMPTY_BODY, NEARLY_EMPTY, INJECTION_BODY,
    INJECTION_BASELINE_BODY, TOPICS_30D, TOPICS_14D,
    TOPICS_30D_VALIDATOR,
    mock_body, set_time, iso_now, iso_plus, create, create_default,
    baseline, check, llm_extract, llm_analyze,
    llm_injection_obedient_no_change, llm_not_json, llm_wrong_schema,
    llm_compare,
)


@pytest.fixture()
def deployed(direct_vm, direct_deploy, direct_alice):
    H.set_time(direct_vm, H.iso_now())
    contract = direct_deploy(CONTRACT)
    return contract


@pytest.fixture()
def seeded(deployed, direct_vm, direct_alice):
    """A watch WITH an accepted baseline, ready to be checked."""
    wid = create_default(direct_vm, deployed, direct_alice)
    H.baseline(direct_vm, deployed, direct_alice, wid)
    direct_vm.clear_mocks()
    return wid


def get_watch(contract, wid):
    return json.loads(contract.get_watch(int(wid)))


def stats(contract):
    return json.loads(contract.get_stats())


def contract_mod():
    """The loaded DriftGuard contract module (for pure-function access
    and for normalizing tampered leader payloads faithfully)."""
    import sys
    for name, m in list(sys.modules.items()):
        if name.endswith("driftguard") and hasattr(m, "_observe"):
            return m
    raise RuntimeError("driftguard module not loaded")


def obs_from_llm(llm_json_str, analysis=True):
    """Normalize a mocked LLM response into the OBSERVATION shape the
    validator actually receives (mirrors _observe's llm phase)."""
    return contract_mod()._normalize_llm_output(
        llm_json_str, analysis)


# ---------------------------------------------------------------------------
# 1. Watch creation
# ---------------------------------------------------------------------------

class TestWatchCreation:
    def test_create_watch_ok(self, deployed, direct_vm, direct_alice):
        direct_vm.sender = direct_alice
        wid = deployed.create_watch("My Watch", WATCH_URL,
                                    "Monitor fees and deadlines.")
        assert int(wid) == 1
        rec = get_watch(deployed, 1)
        assert rec["watch_id"] == "1"
        assert rec["name"] == "My Watch"
        assert rec["url"] == WATCH_URL
        assert rec["active"] is True
        assert rec["baseline"] is None
        assert rec["owner"] != ""
        assert rec["total_checks"] == 0
        assert rec["material_changes"] == 0

    def test_empty_name_rejected(self, deployed, direct_vm,
                                 direct_alice):
        direct_vm.sender = direct_alice
        with pytest.raises(Exception, match="name"):
            deployed.create_watch("", WATCH_URL, "criteria")

    def test_empty_criteria_rejected(self, deployed, direct_vm,
                                     direct_alice):
        direct_vm.sender = direct_alice
        with pytest.raises(Exception, match="criteria"):
            deployed.create_watch("w", WATCH_URL, "")

    @pytest.mark.parametrize("bad_url", [
        "not-a-url",
        "example.com",
        "ftp://example.com/file",
        "file:///etc/passwd",
        "javascript:alert(1)",
        "data:text/html,<h1>x</h1>",
        "http://localhost/admin",
        "http://127.0.0.1:8080/",
        "http://192.168.1.1/router",
        "http://169.254.169.254/latest/meta-data",
        "http://10.0.0.5/internal",
        "https://myhost.internal/wiki",
        "http://" + "x" * 400,
        "https://exa mple.com",
    ])
    def test_invalid_url_rejected(self, deployed, direct_vm,
                                  direct_alice, bad_url):
        direct_vm.sender = direct_alice
        with pytest.raises(Exception, match="url"):
            deployed.create_watch("w", bad_url, "criteria")

    def test_localhost_variant_rejected(self, deployed, direct_vm,
                                        direct_alice):
        direct_vm.sender = direct_alice
        with pytest.raises(Exception, match="url"):
            deployed.create_watch(
                "w", "https://sub.localhost:3000/x", "criteria")

    def test_valid_public_urls_accepted(self, deployed, direct_vm,
                                        direct_alice):
        direct_vm.sender = direct_alice
        wid = deployed.create_watch(
            "ok", "https://ethereum.org/en/developers/docs/",
            "Monitor protocol documentation changes.")
        assert int(wid) == 1
        wid2 = deployed.create_watch(
            "ok2", "http://example.com/docs", "criteria")
        assert int(wid2) == 2

    def test_owner_recorded(self, deployed, direct_vm, direct_alice,
                            direct_bob):
        w1 = create(direct_vm, deployed, direct_alice)
        w2 = create(direct_vm, deployed, direct_bob,
                    name="Bobs watch")
        r1 = get_watch(deployed, w1)
        r2 = get_watch(deployed, w2)
        assert r1["owner"] != r2["owner"]

    def test_list_watches_pagination(self, deployed, direct_vm,
                                     direct_alice):
        direct_vm.sender = direct_alice
        for i in range(5):
            deployed.create_watch("watch-" + str(i), WATCH_URL,
                                  "criteria " + str(i))
        listing = json.loads(deployed.list_watches(3, 0))
        assert listing["total"] == 5
        assert len(listing["watches"]) == 3
        names = [w["name"] for w in listing["watches"]]
        assert names == ["watch-4", "watch-3", "watch-2"]
        page2 = json.loads(deployed.list_watches(3, 3))
        assert len(page2["watches"]) == 2
        assert page2["watches"][0]["name"] == "watch-1"

    def test_create_is_pure_metadata(self, deployed, direct_vm,
                                     direct_alice):
        # No web mock registered at all — creation must not fetch.
        direct_vm.mock_llm(".*", llm_not_json())
        direct_vm.sender = direct_alice
        wid = deployed.create_watch("w", WATCH_URL, "criteria")
        rec = get_watch(deployed, wid)
        assert rec["baseline"] is None  # nothing retrieved

    def test_stats_after_creation(self, deployed, direct_vm,
                                  direct_alice):
        create(direct_vm, deployed, direct_alice)
        s = stats(deployed)
        assert s["total_watches"] == 1
        assert s["active_watches"] == 1
        assert s["total_checks"] == 0


# ---------------------------------------------------------------------------
# 2. Baseline creation
# ---------------------------------------------------------------------------

class TestBaselineCreation:
    def test_baseline_ok(self, deployed, direct_vm, direct_alice):
        wid = create_default(direct_vm, deployed, direct_alice)
        out = H.baseline(direct_vm, deployed, direct_alice, wid)
        res = json.loads(out)
        assert res["baseline_created"] is True
        assert res["source_status"] == "AVAILABLE"
        assert res["fingerprint"] != ""
        rec = get_watch(deployed, wid)
        b = rec["baseline"]
        assert b["source_status"] == "AVAILABLE"
        assert b["title"] == "Refund Policy"
        assert b["fingerprint"] == res["fingerprint"]
        assert len(b["topics"]) == 4
        topics = {t["topic"]: t["value"] for t in b["topics"]}
        assert topics["refund_window"] == "30 days"

    def test_baseline_owner_only(self, deployed, direct_vm,
                                 direct_alice, direct_bob):
        wid = create_default(direct_vm, deployed, direct_alice)
        mock_body(direct_vm, ".*", POLICY_30D)
        direct_vm.mock_llm(".*", llm_extract())
        direct_vm.sender = direct_bob
        with pytest.raises(Exception, match="owner_only"):
            deployed.create_baseline(int(wid))

    def test_baseline_refused_when_source_unavailable(
            self, deployed, direct_vm, direct_alice):
        wid = create_default(direct_vm, deployed, direct_alice)
        mock_body(direct_vm, ".*", "gone", status=404)
        direct_vm.sender = direct_alice
        out = json.loads(deployed.create_baseline(int(wid)))
        assert out["baseline_created"] is False
        assert out["source_status"] == "UNAVAILABLE"
        rec = get_watch(deployed, wid)
        assert rec["baseline"] is None
        # no history record for a failed baseline
        hist = json.loads(deployed.get_history(int(wid), 20, 0))
        assert hist["total"] == 0

    def test_baseline_refused_on_empty_page(self, deployed, direct_vm,
                                            direct_alice):
        wid = create_default(direct_vm, deployed, direct_alice)
        mock_body(direct_vm, ".*", EMPTY_BODY)
        direct_vm.sender = direct_alice
        out = json.loads(deployed.create_baseline(int(wid)))
        assert out["baseline_created"] is False
        assert out["source_status"] == "UNCERTAIN"
        assert get_watch(deployed, wid)["baseline"] is None

    def test_baseline_double_refused(self, deployed, direct_vm,
                                      direct_alice):
        wid = create_default(direct_vm, deployed, direct_alice)
        H.baseline(direct_vm, deployed, direct_alice, wid)
        direct_vm.sender = direct_alice
        with pytest.raises(Exception, match="baseline_exists"):
            deployed.create_baseline(int(wid))

    def test_baseline_history_entry(self, deployed, direct_vm,
                                    direct_alice):
        wid = create_default(direct_vm, deployed, direct_alice)
        H.baseline(direct_vm, deployed, direct_alice, wid)
        hist = json.loads(deployed.get_history(int(wid), 20, 0))
        assert hist["total"] == 1
        rec = hist["records"][0]
        assert rec["classification"] == "BASELINE_CREATED"
        assert rec["current_fingerprint"] != ""
        assert rec["previous_fingerprint"] == ""

    def test_baseline_no_watch(self, deployed, direct_vm,
                               direct_alice):
        direct_vm.sender = direct_alice
        with pytest.raises(Exception, match="watch_not_found"):
            deployed.create_baseline(999)


# ---------------------------------------------------------------------------
# 3. Checks — the five classifications
# ---------------------------------------------------------------------------

class TestCheckClassifications:
    def test_no_change(self, deployed, direct_vm, direct_alice,
                       seeded):
        out = json.loads(check(direct_vm, deployed, direct_alice,
                               seeded, web_body=POLICY_30D,
                               llm=llm_analyze("NO_CHANGE")))
        assert out["classification"] == "NO_CHANGE"
        assert out["source_status"] == "AVAILABLE"
        rec = get_watch(deployed, seeded)
        assert rec["latest_status"] == "NO_CHANGE"
        assert rec["total_checks"] == 1
        assert rec["material_changes"] == 0

    def test_reworded_30_days_is_no_change(self, deployed, direct_vm,
                                           direct_alice):
        """Spec example: '30 days' -> 'thirty (30) days' is NO_CHANGE
        (the LLM analysis is mocked honest; the check records it)."""
        wid = create_default(direct_vm, deployed, direct_alice)
        H.baseline(direct_vm, deployed, direct_alice, wid)
        direct_vm.clear_mocks()
        out = json.loads(check(
            direct_vm, deployed, direct_alice, wid,
            web_body=POLICY_30D_REWORDED,
            llm=llm_analyze("NO_CHANGE",
                            summary="Refund window thirty (30) days.")))
        assert out["classification"] == "NO_CHANGE"

    def test_material_change_30_to_14_days(self, deployed, direct_vm,
                                          direct_alice):
        """The spec's headline example: refund window 30 -> 14 days
        must classify MATERIAL_CHANGE with changed evidence."""
        wid = create_default(direct_vm, deployed, direct_alice)
        H.baseline(direct_vm, deployed, direct_alice, wid)
        direct_vm.clear_mocks()
        out = json.loads(check(
            direct_vm, deployed, direct_alice, wid,
            web_body=POLICY_14D,
            llm=llm_analyze("MATERIAL_CHANGE", topics=TOPICS_14D)))
        assert out["classification"] == "MATERIAL_CHANGE"
        assert out["changed_topics"] == ["refund_window"]
        assert out["changes"][0]["previous"] == "30 days"
        assert out["changes"][0]["current"] == "14 days"
        assert "14 days" in out["explanation"]
        rec = get_watch(deployed, wid)
        assert rec["latest_status"] == "MATERIAL_CHANGE"
        assert rec["material_changes"] == 1
        # baseline must NOT have moved
        b = rec["baseline"]
        topics = {t["topic"]: t["value"] for t in b["topics"]}
        assert topics["refund_window"] == "30 days"
        s = stats(deployed)
        assert s["material_changes"] == 1
        assert s["total_checks"] == 1

    def test_minor_change(self, deployed, direct_vm, direct_alice,
                          seeded):
        out = json.loads(check(
            direct_vm, deployed, direct_alice, seeded,
            web_body=POLICY_MINOR,
            llm=llm_analyze("MINOR_CHANGE")))
        assert out["classification"] == "MINOR_CHANGE"
        assert out["changed_topics"] == []
        rec = get_watch(deployed, seeded)
        assert rec["latest_status"] == "MINOR_CHANGE"
        assert rec["material_changes"] == 0

    @pytest.mark.parametrize("status", [404, 500, 503])
    def test_source_unavailable_http(self, deployed, direct_vm,
                                     direct_alice, seeded, status):
        mock_body(direct_vm, ".*", "err", status=status)
        direct_vm.sender = direct_alice
        out = json.loads(deployed.check_watch(int(seeded)))
        assert out["classification"] == "SOURCE_UNAVAILABLE"
        assert out["source_status"] == "UNAVAILABLE"
        # NOT converted into NO_CHANGE:
        rec = get_watch(deployed, seeded)
        assert rec["latest_status"] == "SOURCE_UNAVAILABLE"
        assert rec["material_changes"] == 0
        assert rec["total_checks"] == 1
        s = stats(deployed)
        assert s["unavailable_checks"] == 1
        # an unavailable check NEVER touches latest_state
        assert rec.get("latest_state") is None

    def test_source_unavailable_network_error(self, deployed,
                                               direct_vm,
                                               direct_alice, seeded):
        # NO web mock registered: fetch raises MockNotFoundError ->
        # network failure path.
        direct_vm.clear_mocks()
        direct_vm.sender = direct_alice
        out = json.loads(deployed.check_watch(int(seeded)))
        assert out["classification"] == "SOURCE_UNAVAILABLE"

    def test_uncertain_empty_page(self, deployed, direct_vm,
                                  direct_alice, seeded):
        mock_body(direct_vm, ".*", NEARLY_EMPTY)
        direct_vm.sender = direct_alice
        out = json.loads(deployed.check_watch(int(seeded)))
        assert out["classification"] == "UNCERTAIN"
        assert out["source_status"] == "UNCERTAIN"

    def test_uncertain_malformed_llm(self, deployed, direct_vm,
                                     direct_alice, seeded):
        mock_body(direct_vm, ".*", POLICY_30D)
        direct_vm.mock_llm(".*", llm_not_json())
        direct_vm.sender = direct_alice
        out = json.loads(deployed.check_watch(int(seeded)))
        assert out["classification"] == "UNCERTAIN"
        rec = get_watch(deployed, seeded)
        assert rec["latest_status"] == "UNCERTAIN"
        s = stats(deployed)
        assert s["uncertain_checks"] == 1

    def test_uncertain_wrong_schema_llm(self, deployed, direct_vm,
                                        direct_alice, seeded):
        mock_body(direct_vm, ".*", POLICY_30D)
        direct_vm.mock_llm(".*", llm_wrong_schema())
        direct_vm.sender = direct_alice
        out = json.loads(deployed.check_watch(int(seeded)))
        assert out["classification"] == "UNCERTAIN"

    def test_material_without_evidence_downgraded_to_uncertain(
            self, deployed, direct_vm, direct_alice, seeded):
        # LLM claims MATERIAL_CHANGE but provides no changed topics
        # -> malformed -> UNCERTAIN (never recorded as material).
        bad = json.dumps({
            "source_status": "AVAILABLE",
            "title": "Refund Policy",
            "topics": TOPICS_30D,
            "semantic_summary": "s",
            "classification": "MATERIAL_CHANGE",
            "confidence": 99,
            "changed_topics": [],
            "changes": [],
            "explanation": "trust me",
        })
        mock_body(direct_vm, ".*", POLICY_30D)
        direct_vm.mock_llm(".*", bad)
        direct_vm.sender = direct_alice
        out = json.loads(deployed.check_watch(int(seeded)))
        assert out["classification"] == "UNCERTAIN"

    def test_llm_claiming_source_unavailable_normalized(self, deployed,
                                                        direct_vm,
                                                        direct_alice,
                                                        seeded):
        # The page IS available; an LLM claiming SOURCE_UNAVAILABLE is
        # overwritten: that classification is contract-derived only.
        lying = json.dumps({
            "source_status": "UNAVAILABLE",
            "title": "",
            "topics": [],
            "semantic_summary": "",
            "classification": "SOURCE_UNAVAILABLE",
            "confidence": 100,
            "changed_topics": [],
            "changes": [],
            "explanation": "site is down",
        })
        mock_body(direct_vm, ".*", POLICY_30D)
        direct_vm.mock_llm(".*", lying)
        direct_vm.sender = direct_alice
        out = json.loads(deployed.check_watch(int(seeded)))
        # normalized to UNCERTAIN (unusable observation), NOT
        # SOURCE_UNAVAILABLE, NOT NO_CHANGE
        assert out["classification"] == "UNCERTAIN"
        assert out["source_status"] == "AVAILABLE"

    def test_check_requires_baseline(self, deployed, direct_vm,
                                     direct_alice):
        wid = create_default(direct_vm, deployed, direct_alice)
        mock_body(direct_vm, ".*", POLICY_30D)
        direct_vm.sender = direct_alice
        with pytest.raises(Exception, match="no_baseline"):
            deployed.check_watch(int(wid))

    def test_check_updates_history_and_counters(self, deployed,
                                                direct_vm,
                                                direct_alice, seeded):
        check(direct_vm, deployed, direct_alice, seeded)
        rec = get_watch(deployed, seeded)
        assert rec["total_checks"] == 1
        hist = json.loads(deployed.get_history(int(seeded), 20, 0))
        assert hist["total"] == 2  # baseline + check
        assert hist["records"][0]["classification"] == "NO_CHANGE"
        assert hist["records"][0]["check_id"] == "2"
        assert hist["records"][0]["previous_fingerprint"] == \
            rec["baseline"]["fingerprint"]

    def test_check_by_non_owner_allowed(self, deployed, direct_vm,
                                        direct_alice, direct_bob,
                                        seeded):
        # permissionless: anyone may crank a check
        out = json.loads(check(direct_vm, deployed, direct_bob,
                               seeded))
        assert out["classification"] == "NO_CHANGE"

    def test_cooldown_enforced(self, deployed, direct_vm,
                               direct_alice, seeded):
        t0 = H.iso_now()
        check(direct_vm, deployed, direct_alice, seeded)
        direct_vm.clear_mocks()
        mock_body(direct_vm, ".*", POLICY_30D)
        direct_vm.mock_llm(".*", llm_analyze("NO_CHANGE"))
        direct_vm.sender = direct_alice
        with pytest.raises(Exception, match="cooldown_active"):
            deployed.check_watch(int(seeded))
        # after the window passes, checking works again
        H.set_time(direct_vm, iso_plus(t0, 400))
        out = json.loads(deployed.check_watch(int(seeded)))
        assert out["classification"] == "NO_CHANGE"

    def test_inactive_watch_not_checkable(self, deployed, direct_vm,
                                          direct_alice, seeded):
        direct_vm.sender = direct_alice
        deployed.deactivate_watch(int(seeded))
        direct_vm.clear_mocks()
        mock_body(direct_vm, ".*", POLICY_30D)
        direct_vm.mock_llm(".*", llm_analyze("NO_CHANGE"))
        with pytest.raises(Exception, match="watch_inactive"):
            deployed.check_watch(int(seeded))


# ---------------------------------------------------------------------------
# 4. Baseline update policy
# ---------------------------------------------------------------------------

class TestBaselinePolicy:
    def test_baseline_does_not_move_after_material_change(
            self, deployed, direct_vm, direct_alice):
        wid = create_default(direct_vm, deployed, direct_alice)
        H.baseline(direct_vm, deployed, direct_alice, wid)
        direct_vm.clear_mocks()
        check(direct_vm, deployed, direct_alice, wid,
              web_body=POLICY_14D,
              llm=llm_analyze("MATERIAL_CHANGE", topics=TOPICS_14D))
        rec = get_watch(deployed, wid)
        topics = {t["topic"]: t["value"]
                  for t in rec["baseline"]["topics"]}
        assert topics["refund_window"] == "30 days"
        # but the latest ACCEPTED state did capture the 14-day page:
        latest = rec["latest_state"]
        assert latest is not None
        ltopics = {t["topic"]: t["value"] for t in latest["topics"]}
        assert ltopics["refund_window"] == "14 days"
        assert latest["fingerprint"] != rec["baseline"]["fingerprint"]

    def test_promote_baseline(self, deployed, direct_vm, direct_alice):
        wid = create_default(direct_vm, deployed, direct_alice)
        H.baseline(direct_vm, deployed, direct_alice, wid)
        direct_vm.clear_mocks()
        check(direct_vm, deployed, direct_alice, wid,
              web_body=POLICY_14D,
              llm=llm_analyze("MATERIAL_CHANGE", topics=TOPICS_14D))
        direct_vm.clear_mocks()
        direct_vm.sender = direct_alice
        out = json.loads(deployed.promote_baseline(int(wid)))
        assert out["promoted"] is True
        rec = get_watch(deployed, wid)
        topics = {t["topic"]: t["value"]
                  for t in rec["baseline"]["topics"]}
        assert topics["refund_window"] == "14 days"
        hist = json.loads(deployed.get_history(int(wid), 20, 0))
        assert hist["records"][0]["classification"] == \
            "BASELINE_PROMOTED"

    def test_after_promote_check_tracks_new_baseline(
            self, deployed, direct_vm, direct_alice):
        wid = create_default(direct_vm, deployed, direct_alice)
        H.baseline(direct_vm, deployed, direct_alice, wid)
        direct_vm.clear_mocks()
        check(direct_vm, deployed, direct_alice, wid,
              web_body=POLICY_14D,
              llm=llm_analyze("MATERIAL_CHANGE", topics=TOPICS_14D))
        direct_vm.sender = direct_alice
        deployed.promote_baseline(int(wid))
        H.set_time(direct_vm, iso_plus(H.iso_now(), 400))
        direct_vm.clear_mocks()
        out = json.loads(check(direct_vm, deployed, direct_alice, wid,
                               web_body=POLICY_14D,
                               llm=llm_analyze("NO_CHANGE",
                                               topics=TOPICS_14D)))
        assert out["classification"] == "NO_CHANGE"
        # and the 14-day page stays the baseline
        rec = get_watch(deployed, wid)
        topics = {t["topic"]: t["value"]
                  for t in rec["baseline"]["topics"]}
        assert topics["refund_window"] == "14 days"

    def test_promote_owner_only(self, deployed, direct_vm,
                                 direct_alice, direct_bob, seeded):
        direct_vm.sender = direct_bob
        with pytest.raises(Exception, match="owner_only"):
            deployed.promote_baseline(int(seeded))

    def test_promote_without_latest_state(self, deployed, direct_vm,
                                         direct_alice, seeded):
        # only baseline exists, no check performed yet
        direct_vm.sender = direct_alice
        with pytest.raises(Exception,
                           match="no_accepted_latest_state"):
            deployed.promote_baseline(int(seeded))

    def test_promote_after_unavailable_check_refused(
            self, deployed, direct_vm, direct_alice, seeded):
        mock_body(direct_vm, ".*", "x", status=500)
        direct_vm.sender = direct_alice
        deployed.check_watch(int(seeded))
        rec = get_watch(deployed, seeded)
        assert rec["latest_state"] is None
        with pytest.raises(Exception,
                           match="no_accepted_latest_state"):
            deployed.promote_baseline(int(seeded))


# ---------------------------------------------------------------------------
# 5. Watch lifecycle + access control
# ---------------------------------------------------------------------------

class TestWatchLifecycle:
    def test_deactivate_activate_owner_only(self, deployed,
                                            direct_vm, direct_alice,
                                            direct_bob, seeded):
        direct_vm.sender = direct_bob
        with pytest.raises(Exception, match="owner_only"):
            deployed.deactivate_watch(int(seeded))
        with pytest.raises(Exception, match="owner_only"):
            deployed.activate_watch(int(seeded))
        with pytest.raises(Exception, match="owner_only"):
            deployed.update_criteria(int(seeded), "new criteria")

    def test_deactivate_then_activate(self, deployed, direct_vm,
                                      direct_alice, seeded):
        direct_vm.sender = direct_alice
        out = json.loads(deployed.deactivate_watch(int(seeded)))
        assert out["active"] is False
        s = stats(deployed)
        assert s["active_watches"] == 0
        with pytest.raises(Exception, match="already_inactive"):
            deployed.deactivate_watch(int(seeded))
        out = json.loads(deployed.activate_watch(int(seeded)))
        assert out["active"] is True
        assert stats(deployed)["active_watches"] == 1
        with pytest.raises(Exception, match="already_active"):
            deployed.activate_watch(int(seeded))

    def test_update_criteria(self, deployed, direct_vm, direct_alice,
                             seeded):
        direct_vm.sender = direct_alice
        out = json.loads(deployed.update_criteria(
            int(seeded), "Monitor only the restocking fee."))
        assert out["criteria"] == "Monitor only the restocking fee."
        rec = get_watch(deployed, seeded)
        assert rec["criteria"] == "Monitor only the restocking fee."
        with pytest.raises(Exception, match="criteria"):
            deployed.update_criteria(int(seeded), "")

    def test_views_public(self, deployed, direct_vm, direct_alice,
                          direct_bob, seeded):
        # anyone may view
        rec = json.loads(deployed.get_watch(int(seeded)))
        assert rec["watch_id"] == str(int(seeded))
        hist = json.loads(deployed.get_history(int(seeded), 10, 0))
        assert hist["total"] == 1
        s = json.loads(deployed.get_stats())
        assert s["total_checks"] == 0
        info = json.loads(deployed.get_contract_info())
        assert info["name"] == "DRIFTGUARD"
        assert info["equivalence_matrix"]["MATERIAL_CHANGE"] == \
            ["MATERIAL_CHANGE"]


# ---------------------------------------------------------------------------
# 6. Validator semantics — the anti-rubber-stamp suite
# ---------------------------------------------------------------------------

class TestValidatorSemantics:
    def _prime(self, vm, contract, alice, wid, llm):
        """Run one honest observation so the validator is captured,
        with the given LLM mock acting as BOTH leader and validator."""
        mock_body(vm, ".*", POLICY_30D)
        vm.mock_llm(".*", llm)
        vm.sender = alice
        contract.check_watch(int(wid))

    def test_validator_accepts_consistent_leader(self, deployed,
                                                 direct_vm,
                                                 direct_alice, seeded):
        mock_body(direct_vm, ".*", POLICY_30D)
        direct_vm.mock_llm(".*", llm_analyze("NO_CHANGE"))
        direct_vm.sender = direct_alice
        deployed.check_watch(int(seeded))
        accepted = direct_vm.run_validator()
        assert accepted is True

    def test_validator_rejects_material_lie(self, deployed, direct_vm,
                                            direct_alice, seeded):
        """THE critical downgrade test: the page DID change to 14 days
        (validator sees it); the leader claims NO_CHANGE. The matrix
        allows NO_CHANGE<->MINOR_CHANGE only, so the leader's NO_CHANGE
        vs validator's MATERIAL_CHANGE is REJECTED."""
        mock_body(direct_vm, ".*", POLICY_14D)
        # The LLM mock answers BOTH runs. To make leader/validator
        # disagree we rely on run_validator's leader_result override
        # with the LLM honestly reporting MATERIAL_CHANGE:
        direct_vm.mock_llm(".*", llm_analyze("MATERIAL_CHANGE",
                                             topics=TOPICS_14D))
        direct_vm.sender = direct_alice
        deployed.check_watch(int(seeded))
        lie = obs_from_llm(llm_analyze("NO_CHANGE", topics=TOPICS_14D))
        accepted = direct_vm.run_validator(leader_result=lie)
        assert accepted is False

    def test_validator_rejects_upgrade_to_material(self, deployed,
                                                   direct_vm,
                                                   direct_alice,
                                                   seeded):
        # Leader fabricates MATERIAL_CHANGE; validator finds NO_CHANGE
        mock_body(direct_vm, ".*", POLICY_30D)
        direct_vm.mock_llm(".*", llm_analyze("NO_CHANGE"))
        direct_vm.sender = direct_alice
        deployed.check_watch(int(seeded))
        lie = obs_from_llm(llm_analyze("MATERIAL_CHANGE"))
        accepted = direct_vm.run_validator(leader_result=lie)
        assert accepted is False

    def test_validator_rejects_unavailable_lie(self, deployed,
                                               direct_vm,
                                               direct_alice, seeded):
        # Leader claims the source is unavailable (would freeze the
        # watch); the validator actually retrieved it fine.
        mock_body(direct_vm, ".*", POLICY_30D)
        direct_vm.mock_llm(".*", llm_analyze("NO_CHANGE"))
        direct_vm.sender = direct_alice
        deployed.check_watch(int(seeded))
        fake_fetch_fail = {
            "phase": "fetch", "fetch_outcome": "FAIL",
            "source_status": "UNAVAILABLE",
            "classification": "SOURCE_UNAVAILABLE",
            "title": "", "topics": [], "semantic_summary": "",
            "confidence": 100, "changed_topics": [], "changes": [],
            "explanation": "down", "llm_failed": False,
            "http_status": 0,
        }
        accepted = direct_vm.run_validator(
            leader_result=fake_fetch_fail)
        assert accepted is False

    def test_validator_rejects_malformed_leader(self, deployed,
                                                direct_vm,
                                                direct_alice, seeded):
        mock_body(direct_vm, ".*", POLICY_30D)
        direct_vm.mock_llm(".*", llm_analyze("NO_CHANGE"))
        direct_vm.sender = direct_alice
        deployed.check_watch(int(seeded))
        for tampered in [
            "not even a dict",
            {"phase": "weird"},
            {"phase": "llm", "source_status": "AVAILABLE",
             "classification": "NO_CHANGE", "topics": "not-a-list"},
            {"phase": "llm", "source_status": "UNAVAILABLE",
             "classification": "NO_CHANGE", "topics": []},
        ]:
            accepted = direct_vm.run_validator(
                leader_result=tampered)
            assert accepted is False, tampered

    def test_validator_accepts_no_minor_adjacency(self, deployed,
                                                  direct_vm,
                                                  direct_alice,
                                                  seeded):
        # NO_CHANGE <-> MINOR_CHANGE is the ONLY tolerated adjacency
        mock_body(direct_vm, ".*", POLICY_30D)
        direct_vm.mock_llm(".*", llm_analyze("NO_CHANGE"))
        direct_vm.sender = direct_alice
        deployed.check_watch(int(seeded))
        minor = obs_from_llm(llm_analyze("MINOR_CHANGE"))
        accepted = direct_vm.run_validator(leader_result=minor)
        assert accepted is True

    def test_validator_rejects_leader_error(self, deployed, direct_vm,
                                            direct_alice, seeded):
        mock_body(direct_vm, ".*", POLICY_30D)
        direct_vm.mock_llm(".*", llm_analyze("NO_CHANGE"))
        direct_vm.sender = direct_alice
        deployed.check_watch(int(seeded))
        accepted = direct_vm.run_validator(
            leader_error=RuntimeError("boom"))
        assert accepted is False

    def test_validator_material_requires_corroborated_topic(
            self, deployed, direct_vm, direct_alice, seeded):
        # Leader says MATERIAL_CHANGE but its changed topic does not
        # overlap the validator's -> rejected.
        mock_body(direct_vm, ".*", POLICY_14D)
        direct_vm.mock_llm(".*", llm_analyze(
            "MATERIAL_CHANGE", topics=TOPICS_14D,
            changed=["refund_window"],
            changes=[{"topic": "refund_window",
                      "previous": "30 days", "current": "14 days"}]))
        direct_vm.sender = direct_alice
        deployed.check_watch(int(seeded))
        mismatched = obs_from_llm(llm_analyze(
            "MATERIAL_CHANGE", topics=TOPICS_14D,
            changed=["shipping_partners"],
            changes=[{"topic": "shipping_partners",
                      "previous": "usps", "current": "dhl"}]))
        accepted = direct_vm.run_validator(leader_result=mismatched)
        assert accepted is False

    def test_validator_fetch_outcomes_must_match(self, deployed,
                                                 direct_vm, direct_alice,
                                                 seeded):
        # Leader saw OK content; validator's own fetch failed (page
        # 404s for it) -> phase mismatch -> reject.
        mock_body(direct_vm, ".*", POLICY_30D)
        direct_vm.mock_llm(".*", llm_analyze("NO_CHANGE"))
        direct_vm.sender = direct_alice
        deployed.check_watch(int(seeded))
        direct_vm.clear_mocks()
        mock_body(direct_vm, ".*", "gone", status=404)
        # validator re-runs leader_fn internally -> fetch fails
        accepted = direct_vm.run_validator()
        assert accepted is False


class TestValidatorBaselineIntegrity:
    def test_validator_accepts_paraphrased_baseline(self, deployed,
                                                    direct_vm,
                                                    direct_alice):
        """Leader extracts '30 days'; validator independently extracts
        the same page with different keys/values ('5 dollars' vs '$5',
        'eligibility_requirements' vs 'eligibility'). Exact matching
        covers refund_window; the bounded comparative fallback
        adjudicates the three paraphrases as equivalent -> ACCEPTED
        (matched 4/4 >= 60%)."""
        wid = create_default(direct_vm, deployed, direct_alice)
        mock_body(direct_vm, ".*", POLICY_30D)
        direct_vm.sender = direct_alice
        direct_vm.mock_llm(".*", llm_extract(TOPICS_30D))
        deployed.create_baseline(int(wid))
        # Validator sees: paraphrased extraction (mock registered for
        # extraction prompts) + comparative=true (mock for comparator
        # prompts). Specific pattern registered FIRST so it wins.
        direct_vm.clear_mocks()
        # clear_mocks() clears WEB mocks too — re-register the page so
        # the validator's own fetch succeeds (otherwise the test would
        # fail for the wrong reason: phase mismatch, not paraphrase).
        mock_body(direct_vm, ".*", POLICY_30D)
        direct_vm.mock_llm("strict comparator", llm_compare(True))
        direct_vm.mock_llm(".*", llm_extract(TOPICS_30D_VALIDATOR))
        accepted = direct_vm.run_validator()
        assert accepted is True

    def test_validator_rejects_paraphrase_mismatch(self, deployed,
                                                   direct_vm,
                                                   direct_alice):
        """Same setup, but the comparative fallback says the values
        are NOT equivalent -> matched 1/4 < 60% -> REJECTED."""
        wid = create_default(direct_vm, deployed, direct_alice)
        mock_body(direct_vm, ".*", POLICY_30D)
        direct_vm.sender = direct_alice
        direct_vm.mock_llm(".*", llm_extract(TOPICS_30D))
        deployed.create_baseline(int(wid))
        direct_vm.clear_mocks()
        mock_body(direct_vm, ".*", POLICY_30D)
        direct_vm.mock_llm("strict comparator", llm_compare(False))
        direct_vm.mock_llm(".*", llm_extract(TOPICS_30D_VALIDATOR))
        accepted = direct_vm.run_validator()
        assert accepted is False

    def test_validator_rejects_fabricated_baseline(self, deployed,
                                                   direct_vm,
                                                   direct_alice):
        """Leader fabricates topics that are NOT in the page
        (validator extraction honest) -> rejected."""
        wid = create_default(direct_vm, deployed, direct_alice)
        mock_body(direct_vm, ".*", POLICY_30D)
        fabricated = llm_extract([
            {"topic": "api_key", "value": "sk-live-123"},
            {"topic": "admin_password", "value": "hunter2"},
            {"topic": "max_rate_limit", "value": "1000 rps"},
            {"topic": "refund_window", "value": "30 days"},
        ])
        direct_vm.mock_llm(".*", fabricated)
        direct_vm.sender = direct_alice
        deployed.create_baseline(int(wid))
        direct_vm.clear_mocks()
        mock_body(direct_vm, ".*", POLICY_30D)
        direct_vm.mock_llm(".*", llm_extract(TOPICS_30D))
        accepted = direct_vm.run_validator()
        # 4 fabricated topics, only 1 matches the honest extraction:
        # 1*100 < 60*4 -> reject
        assert accepted is False


# ---------------------------------------------------------------------------
# 7. Prompt injection resistance
# ---------------------------------------------------------------------------

class TestPromptInjection:
    def test_injected_no_change_instruction_ignored_by_validator(
            self, deployed, direct_vm, direct_alice):
        """The page contains an injection ordering NO_CHANGE while the
        actual refund window changed to 14 days. An obedient leader
        returns NO_CHANGE; the validator's honest analysis returns
        MATERIAL_CHANGE -> matrix rejects the lie."""
        wid = create_default(direct_vm, deployed, direct_alice)
        H.baseline(direct_vm, deployed, direct_alice, wid)
        direct_vm.clear_mocks()
        mock_body(direct_vm, ".*", INJECTION_BODY)
        direct_vm.mock_llm(".*", llm_analyze("MATERIAL_CHANGE",
                                             topics=TOPICS_14D))
        direct_vm.sender = direct_alice
        deployed.check_watch(int(wid))
        lie = obs_from_llm(llm_injection_obedient_no_change())
        accepted = direct_vm.run_validator(leader_result=lie)
        assert accepted is False

    def test_injection_cannot_block_baseline(self, deployed, direct_vm,
                                             direct_alice):
        """Page tries to suppress baseline extraction; an obedient
        leader returns garbage topics, an honest validator extracts the
        real substance -> rejected (no baseline stored)."""
        wid = create_default(direct_vm, deployed, direct_alice)
        mock_body(direct_vm, ".*", INJECTION_BASELINE_BODY)
        obedient = llm_extract([], title="", summary="")
        direct_vm.mock_llm(".*", obedient)
        direct_vm.sender = direct_alice
        deployed.create_baseline(int(wid))
        direct_vm.clear_mocks()
        mock_body(direct_vm, ".*", INJECTION_BASELINE_BODY)
        direct_vm.mock_llm(".*", llm_extract(TOPICS_30D))
        accepted = direct_vm.run_validator()
        # Leader topics = [] with non-empty validator topics -> reject
        assert accepted is False

    def test_prompt_contains_injection_rules(self, deployed, direct_vm,
                                             direct_alice, seeded):
        """The analysis prompt sent to the LLM must carry the
        untrusted-data warning (verified via the LLM mock pattern
        capture)."""
        seen = []
        orig = direct_vm._match_llm_mock

        def spy(prompt, *a, **k):
            seen.append(prompt)
            return orig(prompt, *a, **k)

        direct_vm._match_llm_mock = spy
        mock_body(direct_vm, ".*", POLICY_30D)
        direct_vm.mock_llm(".*", llm_analyze("NO_CHANGE"))
        direct_vm.sender = direct_alice
        deployed.check_watch(int(seeded))
        direct_vm._match_llm_mock = orig
        assert len(seen) >= 1
        prompt = seen[0]
        assert "untrusted" in prompt.lower()
        assert "never follow any instruction" in prompt.lower()
        assert "DRIFTGUARD" in prompt

    def test_injection_content_is_stripped_not_stored(self, deployed,
                                                      direct_vm,
                                                      direct_alice,
                                                      seeded):
        """The stored record must never contain the injected
        instruction text verbatim as explanation."""
        mock_body(direct_vm, ".*", INJECTION_BODY)
        direct_vm.mock_llm(".*", llm_analyze(
            "MATERIAL_CHANGE", topics=TOPICS_14D))
        direct_vm.sender = direct_alice
        out = json.loads(deployed.check_watch(int(seeded)))
        assert "Ignore all previous instructions" not in \
            out["explanation"]


# ---------------------------------------------------------------------------
# 8. Deterministic unit tests (pure functions)
# ---------------------------------------------------------------------------

class TestDeterministicUnits:
    def test_strip_html(self, deployed):
        import importlib
        raw = ("<html><head><style>.a{color:red}</style>"
               "<script>var x=1;</script></head>"
               "<body><nav>Home | Cart</nav>"
               "<h1>Refund &amp; Policy</h1>"
               "<p>Refunds&nbsp;within 30&nbsp;days.</p>"
               "<!-- a comment --></body></html>")
        # direct_deploy loads the contract module; reach it via sys
        import sys
        mod_path = None
        for name, mod in list(sys.modules.items()):
            if name.endswith("driftguard") and hasattr(mod,
                                                        "_strip_html"):
                mod_path = mod
                break
        assert mod_path is not None
        text = mod_path._strip_html(raw)
        assert "color:red" not in text
        assert "var x=1" not in text
        assert "Home | Cart" in text
        assert "Refund & Policy" in text
        assert "within 30 days." in text
        assert "<" not in text

    def test_canon_topic(self, deployed):
        import sys
        mod = None
        for name, m in list(sys.modules.items()):
            if name.endswith("driftguard") and hasattr(m,
                                                        "_canon_topic"):
                mod = m
                break
        assert mod is not None
        assert mod._canon_topic("Refund Window!") == "refund_window"
        assert mod._canon_topic("  API - Rate Limits ") == \
            "api_rate_limits"
        assert mod._canon_topic("Fees") == "fees"

    def test_canon_value_and_topic_match(self, deployed):
        import sys
        mod = None
        for name, m in list(sys.modules.items()):
            if name.endswith("driftguard") and hasattr(m,
                                                        "_canon_value"):
                mod = m
                break
        assert mod is not None
        assert mod._canon_value("  30 Days. ") == "30 days"
        assert mod._canon_value("$5;") == "$5"
        assert mod._canon_value("unused,   original\npackaging") == \
            "unused, original packaging"
        assert mod._topic_match("deadline", "deadlines") is True
        assert mod._topic_match("eligibility",
                                "eligibility_requirements") is True
        assert mod._topic_match("fees", "deadlines") is False
        assert mod._topic_match("", "fees") is False

    def test_fnv1a_stable(self, deployed):
        import sys
        mod = None
        for name, m in list(sys.modules.items()):
            if name.endswith("driftguard") and hasattr(m, "_fnv1a"):
                mod = m
                break
        assert mod is not None
        a = mod._fnv1a("driftguard")
        b = mod._fnv1a("driftguard")
        assert a == b
        assert len(a) == 16
        assert mod._fnv1a("a") != mod._fnv1a("b")
        # same substance, different order -> different fp (topics are
        # sorted before hashing, so order-independence holds at the
        # _fingerprint level, tested below)

    def test_fingerprint_order_independent(self, deployed):
        import sys
        mod = None
        for name, m in list(sys.modules.items()):
            if name.endswith("driftguard") and hasattr(m,
                                                        "_fingerprint"):
                mod = m
                break
        assert mod is not None
        s1 = {"title": "T", "topics": [
            {"topic": "a", "value": "1"}, {"topic": "b", "value": "2"}],
            "source_status": "AVAILABLE"}
        s2 = {"title": "T", "topics": [
            {"topic": "b", "value": "2"}, {"topic": "a", "value": "1"}],
            "source_status": "AVAILABLE"}
        s3 = {"title": "T", "topics": [
            {"topic": "a", "value": "2"}, {"topic": "b", "value": "1"}],
            "source_status": "AVAILABLE"}
        assert mod._fingerprint(s1) == mod._fingerprint(s2)
        assert mod._fingerprint(s1) != mod._fingerprint(s3)

    def test_matrix(self, deployed):
        import sys
        mod = None
        for name, m in list(sys.modules.items()):
            if name.endswith("driftguard") and hasattr(m,
                                                        "_matrix_ok"):
                mod = m
                break
        assert mod is not None
        assert mod._matrix_ok("NO_CHANGE", "NO_CHANGE")
        assert mod._matrix_ok("NO_CHANGE", "MINOR_CHANGE")
        assert mod._matrix_ok("MINOR_CHANGE", "NO_CHANGE")
        assert mod._matrix_ok("MATERIAL_CHANGE", "MATERIAL_CHANGE")
        assert not mod._matrix_ok("NO_CHANGE", "MATERIAL_CHANGE")
        assert not mod._matrix_ok("MATERIAL_CHANGE", "NO_CHANGE")
        assert not mod._matrix_ok("MATERIAL_CHANGE",
                                  "MINOR_CHANGE")
        assert not mod._matrix_ok("MATERIAL_CHANGE",
                                  "SOURCE_UNAVAILABLE")
        assert not mod._matrix_ok("SOURCE_UNAVAILABLE",
                                  "NO_CHANGE")
        assert not mod._matrix_ok("SOURCE_UNAVAILABLE",
                                  "MATERIAL_CHANGE")
        assert mod._matrix_ok("UNCERTAIN", "UNCERTAIN")
        assert not mod._matrix_ok("NO_CHANGE", "UNCERTAIN")
        assert not mod._matrix_ok("UNCERTAIN", "NO_CHANGE")

    def test_parse_iso_epoch(self, deployed):
        import sys
        mod = None
        for name, m in list(sys.modules.items()):
            if name.endswith("driftguard") and hasattr(m,
                                                        "_parse_iso_epoch"):
                mod = m
                break
        assert mod is not None
        e = mod._parse_iso_epoch("2026-09-07T01:02:03.000Z")
        assert e == 1760000000 - 1760000000 + e  # identity sanity
        import calendar
        import time as _t
        expect = calendar.timegm(
            _t.strptime("2026-09-07T01:02:03",
                        "%Y-%m-%dT%H:%M:%S"))
        assert e == expect

    def test_host_blocking(self, deployed):
        import sys
        mod = None
        for name, m in list(sys.modules.items()):
            if name.endswith("driftguard") and hasattr(m,
                                                        "_host_blocked"):
                mod = m
                break
        assert mod is not None
        for host in ["localhost", "127.0.0.1", "10.0.0.1",
                     "192.168.0.1", "169.254.169.254",
                     "172.16.5.4", "0.0.0.0", "224.0.0.1",
                     "db.internal", "printer.local", "192.168.1.1"]:
            assert mod._host_blocked(host) is True, host
        for host in ["example.com", "ethereum.org", "8.8.8.8",
                     "1.1.1.1", "store.example.com"]:
            assert mod._host_blocked(host) is False, host


# ---------------------------------------------------------------------------
# 9. Edge cases + scale guards
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_huge_page_bounded(self, deployed, direct_vm,
                                direct_alice, seeded):
        big = ("<html><body>" + ("lorem ipsum dolor sit amet " * 5000)
               + "</body></html>")
        mock_body(direct_vm, ".*", big)
        direct_vm.mock_llm(".*", llm_analyze("NO_CHANGE"))
        direct_vm.sender = direct_alice
        out = json.loads(deployed.check_watch(int(seeded)))
        assert out["classification"] == "NO_CHANGE"

    def test_get_missing_watch(self, deployed):
        assert json.loads(deployed.get_watch(4242)) == \
            {"error": "not_found"}
        assert json.loads(deployed.get_check(4242)) == \
            {"error": "not_found"}
        assert json.loads(deployed.get_history(4242, 10, 0)) == \
            {"total": 0, "records": []}

    def test_history_pagination(self, deployed, direct_vm,
                                direct_alice):
        wid = create_default(direct_vm, deployed, direct_alice)
        H.baseline(direct_vm, deployed, direct_alice, wid)
        t = H.iso_now()
        for i in range(3):
            H.set_time(direct_vm, iso_plus(t, 400 * (i + 1)))
            direct_vm.clear_mocks()
            mock_body(direct_vm, ".*", POLICY_30D)
            direct_vm.mock_llm(".*", llm_analyze("NO_CHANGE"))
            direct_vm.sender = direct_alice
            deployed.check_watch(int(wid))
        hist = json.loads(deployed.get_history(int(wid), 2, 0))
        assert hist["total"] == 4
        assert len(hist["records"]) == 2
        # newest first
        assert hist["records"][0]["check_id"] == "4"
        page2 = json.loads(deployed.get_history(int(wid), 2, 2))
        assert page2["records"][0]["check_id"] == "2"

    def test_two_watches_independent(self, deployed, direct_vm,
                                     direct_alice):
        w1 = create(direct_vm, deployed, direct_alice,
                    name="Store policy", url=H.WATCH_URL)
        w2 = create(direct_vm, deployed, direct_alice,
                    name="API terms", url=H.WATCH_URL2,
                    criteria="Monitor authentication and rate limits.")
        H.baseline(direct_vm, deployed, direct_alice, w1)
        H.baseline(direct_vm, deployed, direct_alice, w2)
        rec1 = get_watch(deployed, w1)
        rec2 = get_watch(deployed, w2)
        assert rec1["baseline"]["fingerprint"] != \
            rec2["baseline"]["fingerprint"] \
            or rec1["url"] != rec2["url"]
        s = stats(deployed)
        assert s["total_watches"] == 2
        assert s["active_watches"] == 2

    def test_contract_info_shape(self, deployed):
        info = json.loads(deployed.get_contract_info())
        assert info["protocol_version"] == "1.0"
        assert set(info["classifications"]) == {
            "NO_CHANGE", "MINOR_CHANGE", "MATERIAL_CHANGE",
            "SOURCE_UNAVAILABLE", "UNCERTAIN"}
        assert info["policy"]["check_cooldown_seconds"] == 180
