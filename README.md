# DriftGuard

**Trustless semantic change detection for the open web.**

DriftGuard is a decentralized web-change monitoring protocol built on GenLayer
Intelligent Contracts. GenLayer validators independently retrieve a registered
public source, normalize what it says, and reach consensus on whether its
**meaning** materially changed — not its bytes, not its layout.

```
"Refunds are available within 30 days."     → "within 14 days"
     = MATERIAL_CHANGE

"Refunds are available within 30 days."     → "within thirty (30) days"
     = NO_CHANGE
```

A byte-diff sees both edits. Only semantic consensus under GenLayer's
Equivalence Principle can tell a policy change from a rewording — and it
takes a majority of independent validators to make the call.

## Why GenLayer

A conventional backend can detect byte-level changes. DriftGuard solves the
harder problem: *did the meaning or important substance of this public
document actually change?* That verdict must be:

- **Trustless** — no single LLM, backend, or frontend is the authority;
  every validator re-runs the entire retrieval → normalization →
  classification pipeline itself.
- **Fail-safe** — retrieval failures become `SOURCE_UNAVAILABLE` via a
  deterministic gate no LLM can override; ambiguous content becomes
  `UNCERTAIN`, a legitimate terminal state. Failures are never converted
  into "no change".
- **Explicit** — the leader's classification is accepted only if it
  matches the validator's own under a fixed equivalence matrix, so a
  material change can never be downgraded to "no change", and an
  unavailable source can never masquerade as a calm one.

## Architecture

```
USER / DAPP
   │
DriftGuard UI  (React + TypeScript + Vite, GenLayer JS SDK)
   │
DriftGuard Intelligent Contract  (GenLayer Studionet)
   │  NON-DETERMINISTIC
   ▼
Leader retrieval + semantic analysis
   │  Equivalence Principle
   ▼
Validators independently verify  ──► Consensus decision
   ▼
Deterministic state update on-chain
```

Each monitored source is a **Watch**. A watch stores the owner, source URL,
monitoring criteria, an accepted **semantic baseline** (a compact structured
representation + fingerprint — never raw HTML), an immutable **change
history**, and counters. The baseline moves only when the owner explicitly
**promotes** the latest accepted state, making DriftGuard useful for
tracking policy and documentation evolution.

### Classifications

| State | Meaning |
|---|---|
| `NO_CHANGE` | No meaningful semantic change vs the accepted baseline |
| `MINOR_CHANGE` | Wording/formatting changed, monitored meaning did not |
| `MATERIAL_CHANGE` | Fees, deadlines, eligibility, API behavior, legal terms… changed |
| `SOURCE_UNAVAILABLE` | Retrieval failed (HTTP error, timeout, DNS) — deterministic gate |
| `UNCERTAIN` | Validators cannot reliably determine the change — legitimate terminal state |

### Equivalence matrix (leader ↔ validator)

```
NO_CHANGE          ↔ NO_CHANGE / MINOR_CHANGE
MINOR_CHANGE       ↔ NO_CHANGE / MINOR_CHANGE
MATERIAL_CHANGE    ↔ MATERIAL_CHANGE            (strict — never downgraded)
SOURCE_UNAVAILABLE ↔ SOURCE_UNAVAILABLE         (strict)
UNCERTAIN          ↔ UNCERTAIN                  (strict)
```

## Contract

`contracts/driftguard.py` — a single GenLayer Intelligent Contract
(py-genlayer runner pinned by hash). Key design:

- **Retrieval gate** (`_fetch`): HTTP status + stripped-text checks happen
  deterministically *before* any LLM call; failures map to
  `SOURCE_UNAVAILABLE` (non-2xx, network error) or `UNCERTAIN` (2xx but
  nearly empty), never `NO_CHANGE`.
- **URL safety**: only `http`/`https`; private, loopback and link-local
  hosts are rejected (SSRF-style protection within the GenLayer web
  sandbox).
- **Semantic normalization** (`_observe`): the page is stripped of
  markup/CSS/nav noise, and an LLM extracts a structured state limited to
  the watch's criteria — topics, values, rules — producing a stable
  canonical fingerprint. Validators compare the *derived classification*,
  not raw page bytes (Equivalence Principle).
- **Prompt-injection resistance**: every LLM prompt embeds SYSTEM RULES
  (R1–R3) declaring retrieved content as untrusted data that can never
  redefine criteria, classification rules, or output format.
- **Strict LLM output validation** (`_normalize_llm_output`): malformed
  output is rejected safely → `UNCERTAIN`; classification must be one of
  the five states.
- **Owner-only writes** for baseline promotion / pause / resume / criteria
  updates (address-checksummed comparisons); **`check_watch` is
  permissionless** for composability.
- **History**: compact per-check records (classification, fingerprints,
  changed topics, explanation) — no HTML ever stored on-chain.

## Testing

99 tests (`gltest` pinned 0.29.2): 87 direct-mode contract tests covering
watch creation, invalid URL / empty criteria rejection, owner permissions,
baseline creation, all five classifications, injection attempts,
equivalence-matrix rejections, baseline promotion, pause/resume, and view
methods — plus 12 deploy-script regression tests.

```bash
cd ~/driftguard && ~/genlayer-env/bin/python -m pytest tests/direct -q
```

Live Studionet evidence:
- `scripts/deploy_smoke.py` — deploy + determinism ×3 + negative cases +
  views readback → `docs/deployment_log.json`
- `scripts/classification_proof.py` — controlled-fixture classification
  proofs (material change, revert, dead URL, empty page, prompt injection)
  → `docs/classification_proof.json`
- Full lifecycle E2E driven from the hosted dApp (watch #16) →
  `SUBMISSION.md`

## Frontend dApp

`frontend/` — React + TypeScript + Vite, GenLayer JS SDK bundle,
in-browser burner wallets with Studionet faucet, full tx lifecycle with
FINALIZED + execution-result checking, LIVE/DEMO modes.

- **LIVE** talks to the real Intelligent Contract via `window.GenLayerSDK`
  (reads + writes with consensus waiting).
- **DEMO MODE** is a clearly-labeled deterministic local simulation for
  frontend testing only — it never contacts GenLayer and every screen is
  badged `DEMO MODE — simulated, not consensus`.

```bash
cd frontend && npm install && npm run build
npx vite preview --port 4510
```

Pages: Dashboard (stats + watch list), Create Watch (with example
configurations), Watch Detail (current status, change visualization cards,
accepted baseline, expandable history timeline).

## Repository layout

```
contracts/driftguard.py     the Intelligent Contract
tests/direct/               87 direct-mode tests (+ helpers)
scripts/deploy_smoke.py     Studionet deploy + live consensus smoke
frontend/                   React/TS dApp (LIVE + DEMO modes)
docs/deployment_log.json    live smoke evidence (tx hashes, verdicts)
```

## Live deployment

| Item | Value |
|---|---|
| Contract | `0xAc908C41B2326CE515a746292908BAc35f7AB6B6` (GenLayer Studionet) — [explorer](https://explorer-studio.genlayer.com/address/0xAc908C41B2326CE515a746292908BAc35f7AB6B6) |
| dApp | https://driftguard-kappa.vercel.app (LIVE mode — reads/writes the Studionet contract directly) |
| Tests | 99 passed / 0 failed (87 direct-mode + 12 regression) |

On-chain evidence for watch #16 (read back via RPC, see `SUBMISSION.md`):
`BASELINE_CREATED → NO_CHANGE → MATERIAL_CHANGE → SOURCE_UNAVAILABLE →
BASELINE_PROMOTED`, baseline fingerprint moved only by the explicit owner
promotion (`7550639f…` → `eb32fb09…`).

## Honest status

- The contract is deployed and live; every claim above was read back from
  the chain, and the dApp renders real consensus state (not simulations).
- DEMO mode is clearly badged and never contacts GenLayer; the UI shows
  "Awaiting live verification" rather than fabricating results.
- `SUBMISSION.md` is the full evidence trail (tx hashes per scenario);
  `docs/PORTAL_SUBMISSION_KIT.md` mirrors the GenLayer Builder Portal
  submission fields.
