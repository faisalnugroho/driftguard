#!/usr/bin/env python3
"""Regression tests for deploy_smoke.py helpers.

Covers the v1 live-crash bug exactly: the chain returns check ids as
decimal STRINGS inside JSON records ("check_id": "7") while the v1
script compared them with ints ("7" <= 0 -> TypeError). _as_int()
must normalize int / numeric str / quoted str / None / float / bool /
garbage without ever raising, and the acceptance comparison
(_as_int(check_id) > known) must behave correctly for every shape.
"""
import importlib.util
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPT = HERE.parent.parent / "scripts" / "deploy_smoke.py"


def load_helpers():
    """Import deploy_smoke.py WITHOUT running main() and without
    importing genlayer_py (stub the heavy deps first)."""
    stubs = ["genlayer_py", "genlayer_py.chains", "genlayer_py.types"]
    for name in stubs:
        if name not in sys.modules:
            m = type(sys)("stub_" + name.replace(".", "_"))
            if name == "genlayer_py":
                m.create_client = lambda **k: None
                m.create_account = lambda **k: None
            if name == "genlayer_py.chains":
                m.studionet = None
            if name == "genlayer_py.types":
                m.TransactionStatus = None
            sys.modules[name] = m
    spec = importlib.util.spec_from_file_location("deploy_smoke", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestAsInt:
    def setup_method(self):
        self.mod = load_helpers()

    # ---- the exact v1 crash: string id compared against int ----
    def test_v1_regression_string_check_id(self):
        # v1 line: last.get("check_id", 0) <= 0  ->  "7" <= 0 TypeError
        rec = {"check_id": "7"}
        # must not raise, and must compare correctly afterwards
        assert self.mod._as_int(rec.get("check_id", 0)) == 7
        assert self.mod._as_int(rec.get("check_id", 0)) > 0  # v1 crashed here

    def test_int(self):
        assert self.mod._as_int(7) == 7
        assert self.mod._as_int(0) == 0
        assert self.mod._as_int(-1) == -1

    def test_numeric_string(self):
        assert self.mod._as_int("7") == 7
        assert self.mod._as_int(" 12 ") == 12
        assert self.mod._as_int("0") == 0

    def test_quoted_string(self):
        assert self.mod._as_int('"7"') == 7

    def test_float_string_and_float(self):
        assert self.mod._as_int("7.0") == 7
        assert self.mod._as_int(7.0) == 7

    def test_none_returns_default(self):
        assert self.mod._as_int(None) == 0
        assert self.mod._as_int(None, default=99) == 99

    def test_bool_rejected(self):
        # bool is an int subclass; ids are never bools
        assert self.mod._as_int(True) == 0
        assert self.mod._as_int(False) == 0

    def test_garbage_returns_default(self):
        assert self.mod._as_int("banana") == 0
        assert self.mod._as_int("banana", default=5) == 5
        assert self.mod._as_int([1, 2]) == 0
        assert self.mod._as_int({"a": 1}) == 0
        assert self.mod._as_int(object()) == 0

    def test_never_raises(self):
        for weird in [None, "", " ", "-", "+", "0x10", 3.7, "1e3",
                      float("nan") if False else "nan", [], {}, True]:
            try:
                self.mod._as_int(weird)
            except Exception as e:  # pragma: no cover
                raise AssertionError(f"_as_int({weird!r}) raised {e!r}")

    # ---- acceptance comparison used by check(): new record detection ----
    def test_acceptance_comparison_chain_shapes(self):
        known = 4
        for cid, accepted in [("5", True), (5, True), ("4", False),
                              (4, False), (None, False), ("garbage", False)]:
            assert (self.mod._as_int(cid) > known) is accepted, cid

    # ---- guard payload parsing: cooldown remainder extraction ----
    def test_cooldown_remainder_parse(self):
        payload = "cooldown_active:126"
        # the exact split used in deploy_smoke.check/baseline
        assert self.mod._as_int(payload.split(":")[1]) == 126
        # malformed variant must fall back, not raise
        bad = "cooldown_active:oops"
        val = self.mod._as_int(bad.split(":")[1], default=60)
        assert val == 60

    # ---- v2.1 regression: lifecycle history rows must not count as
    #      determinism verdicts (first live rerun captured the
    #      BASELINE_CREATED row as "verdict 1" and failed S2) ----
    def test_v21_lifecycle_rows_not_check_verdicts(self):
        LIFECYCLE = {"BASELINE_CREATED", "BASELINE_PROMOTED"}
        recs = [
            {"check_id": "7", "classification": "BASELINE_CREATED"},
            {"check_id": "8", "classification": "NO_CHANGE"},
            {"check_id": "9", "classification": "BASELINE_PROMOTED"},
            {"check_id": "10", "classification": "MATERIAL_CHANGE"},
        ]
        known = 7  # baseline row id
        fresh = [x for x in recs
                 if self.mod._as_int(x.get("check_id")) > known
                 and x.get("classification") not in LIFECYCLE]
        assert [x["classification"] for x in fresh] == \
            ["NO_CHANGE", "MATERIAL_CHANGE"]
