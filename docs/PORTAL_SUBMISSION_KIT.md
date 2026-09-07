# GenLayer Portal Submission Kit — DriftGuard

Target: portal.genlayer.foundation/submit-contribution
Account: zkfync | Contribution Type: Builder → Projects
Reward range: 20–4000 pts (quality/impact-based)
Quota context: Projects = 2 slots/week (verify current usage on the form)

## Form fields

**Contribution Date:** (tanggal submit — isi hari-H)

**Title:**
```
DriftGuard — Trustless semantic change detection for the open web
```

**Notes/Description (954/1000 chars):**
```
DriftGuard is a decentralized web-change monitoring protocol: register any public URL, state what matters about it, and GenLayer validators independently retrieve the page, derive a semantic state limited to your criteria, and reach consensus on whether its MEANING materially changed — not its bytes. "30 days → 14 days" is MATERIAL_CHANGE; "30 days → thirty (30) days" is NO_CHANGE. Every check runs the full leader/validator pipeline under an explicit equivalence matrix — a material change can never be downgraded to "no change", and retrieval failures hit a deterministic SOURCE_UNAVAILABLE gate no LLM can override. Baselines move only by explicit owner promotion; history is immutable on-chain. Live dApp (LIVE mode, reads/writes Studionet directly) with the full lifecycle verified on-chain: baseline → NO_CHANGE → MATERIAL_CHANGE → SOURCE_UNAVAILABLE → BASELINE_PROMOTED (watch #16), plus 99/99 tests and prompt-injection resistance proven live.
```

**Evidence (WAJIB, minimal satu; auto-detect dari URL):**
- Repository: https://github.com/faisalnugroho/driftguard
- (opsional, tambahan) Live dApp: https://driftguard-kappa.vercel.app
- (opsional, tambahan) Explorer contract: https://explorer-studio.genlayer.com/address/0xAc908C41B2326CE515a746292908BAc35f7AB6B6

Lalu reCAPTCHA → Submit Contribution.

## Quick facts (kalau steward follow-up / buat balasan review)

- Contract (GenLayer Studionet): 0xAc908C41B2326CE515a746292908BAc35f7AB6B6
- Deploy tx: 0xb0afd1002db6554bf1371596a4baf1c98553928a58d056d9f63386eb0d6e30fd (Deploy, FINALIZED, SUCCESS, Accepted)
- Repo HEAD: 93d3d37 (SUBMISSION.md lengkap: 10+ skenario live, semua tx hash + read-back on-chain)
- Tests: 99 passed / 0 failed (87 contract direct-mode + 12 deploy-script regression), gltest direct mode 0.29.2
- Live E2E dari dApp publik: watch #16 full lifecycle (5 record on-chain: BASELINE_CREATED → NO_CHANGE → MATERIAL_CHANGE → SOURCE_UNAVAILABLE → BASELINE_PROMOTED), total_checks=3, material_changes=1
- Classification proof terkontrol: MATERIAL 14↔30 days, NO_CHANGE revert, dead→SOURCE_UNAVAILABLE (never NO_CHANGE), empty→UNCERTAIN, prompt injection "IGNORE ALL PREVIOUS INSTRUCTIONS" diperlakukan sebagai data (obeyed=false)
- Guards proven live: baseline_exists rollback, cooldown 180s anti-spam, owner-only writes, permissionless check_watch (third-party burner wallets)
- Frontend: client-side only, tanpa backend di write path; DEMO mode berlabel jelas dan tidak menyentuh GenLayer
- Known limitation (jujur): consensus latency 1–13 menit per tx nondeterministik; fixture tunnel hanya untuk controlled-source proofs

## Pre-submit checklist (sudah hijau)

- [x] Repo public + clean + pushed (93d3d37)
- [x] Kontrak live Studionet, semua metode teruji, konsensus stabil berulang
- [x] SUBMISSION.md = evidence lengkap per skenario dengan tx hash
- [x] 99/99 test, lint clean
- [x] dApp publik live mode LIVE
- [x] Deskripsi < 1000 karakter, klaim semuanya terverifikasi on-chain (no fake data)
