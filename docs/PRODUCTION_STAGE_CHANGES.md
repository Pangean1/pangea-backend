# Production Stage — Deferred Changes

This document tracks changes to PANGEA that are intentionally **not** being built yet, deferred until the project reaches its **Production stage** (post-mainnet, once real institutional/grant engagement exists). Each entry explains the current gap, why it's deferred rather than fixed now, what the eventual solution looks like, and what should trigger picking it back up.

See `docs/WHITEPAPER.md` for the original full design these items are deferred from.

---

## 1. `campaignId` is not an indexed event topic (on-chain traceability gap)

**Situation:** PANGEA's core principle is "every transaction publicly verifiable on-chain." Today, that's only true if you trust PANGEA's own backend database. The `DonationSent` event emitted by `PangeaDonation.sol` is:

```solidity
event DonationSent(address indexed donor, address indexed recipient, address indexed token, uint256 amount, uint256 campaignId, uint256 timestamp, string message);
```

`campaignId` is the only field that ties a donation to a specific campaign, but it's a bare number (e.g. `8`) that's meaningless without a name lookup — and that lookup exists **only** in PANGEA's Postgres `campaigns` table, nowhere on-chain. Someone auditing donations directly on PolygonScan, without trusting PANGEA's backend, cannot tell which campaign a donation belongs to.

**Cause:** `campaignId` was never marked `indexed` in the event signature, so it isn't a filterable topic — even someone who already knows "campaignId 8 = Help Ukraine" can't filter the contract's log view by it on PolygonScan. They'd have to open every single `DonationSent` log one at a time and read the decoded value by eye.

**Solution:** Mark `campaignId` as `indexed` in the event signature (max 3 indexed params already used by `donor`/`recipient`/`token`, so one of those would need to be dropped from indexing, or the event restructured — needs real design work, not a one-line change). Requires:
- Modifying and redeploying `PangeaDonation.sol` to a new address
- Re-registering all existing campaigns against the new contract
- Updating `CONTRACT_ADDRESS` everywhere (backend `.env`, event listener config)
- Updating the listener's start block to the new deployment block
- Re-verifying the new contract on PolygonScan

A smaller, non-blocking partial mitigation shipped 2026-07-04 (pangea-frontend commit `3bcba0c`): the `message` field, previously always sent as `''`, now carries `"Campaign: <name>"` for every new donation (see `app/campaign/[id]/donate.tsx`). `campaignId` already appears as its own field in the decoded PolygonScan log, right above `message`, so the two together let a viewer read both the numeric id and the campaign name directly off-chain without trusting PANGEA's database — even though `campaignId` still isn't a filterable indexed topic (that part of the gap remains, see above). This only covers donations made from 2026-07-04 onward; donations before that date remain unlabeled in the raw log.

**Effort & Risk:** High. New contract address is a breaking change across backend, frontend, and every previously-registered campaign. Not something to do casually post-mainnet without a clear migration plan.

**Trigger to revisit:** When PANGEA is ready to invest in a proper contract upgrade path (e.g. alongside a proxy/upgradeability pattern, if one gets adopted), or if an institutional partner specifically requires independently-filterable on-chain audit trails as a condition of engagement.

---

## 2. Fiat / card donations ("Donate with Card" via Ramp Network)

**Situation:** The whitepaper's original design includes "Donate with Card" — a fiat on-ramp via Ramp Network for non-crypto users, funding the same embedded wallet rather than requiring the donor to already hold USDC. The frontend already ships a visible but non-functional placeholder for this: a hardcoded-`disabled` "Donate with Card (disable)" button sits directly below the real "Donate with Wallet" button in `app/campaign/[id]/donate.tsx`. No on-ramp integration exists behind it.

**Cause:** Scoped out early to ship a working donation flow faster; the placeholder button was left in place as a visible marker rather than removed.

**Solution:** Add a fiat on-ramp integration (Ramp Network or equivalent) as an alternate funding path for donors who want to pay by card instead of holding USDC: card → Ramp converts to USDC → lands in the donor's own embedded wallet (invisible to them) → the same embedded-wallet `donate()` call already used today then sends it on-chain to the beneficiary. Two steps under the hood, one smooth funnel to the donor — enter card, confirm, done, no wallet/crypto vocabulary shown.

**⚠️ Dependency on item #3:** This flow's second step *is* today's embedded-wallet `donate()` call — the same one currently exposed under the "Donate with Wallet" button. When item #3 repurposes that button for external-wallet-connect, the embedded-wallet signing code must be **preserved, not deleted or overwritten** — it just stops being triggered by a donor-facing button directly and instead fires automatically as the last step of this card flow. Building #3 without keeping this path intact would silently break "Donate with Card."

**Effort & Risk:** Medium. Mostly additive (new payment provider integration + backend webhook handling for on-ramp completion, then wiring the existing placeholder button to it), doesn't require changing the existing donation contract, but does depend on the embedded-wallet `donate()` path from item #3 surviving intact, and adds a third-party dependency (Ramp Network) and its compliance/KYC surface.

**Trigger to revisit:** Per the whitepaper's own roadmap, scheduled for **V1.5 (Q1 2027)**. Not urgent, not a bug — just not yet built.

---

## 3. Repurpose "Donate with Wallet" as a real external-wallet-connect flow for crypto-native donors

**Situation:** Today, "Donate with Wallet" (`app/campaign/[id]/donate.tsx`) is the one and only donation flow, used by every donor regardless of crypto experience — it signs with the donor's auto-generated embedded smart-account wallet (email OTP → local key → ZeroDev ERC-4337 account), never an externally connected wallet. A crypto-native donor who already holds their own USDC (e.g. in MetaMask) has no way to donate directly from their own wallet; instead they'd have to move funds into the app-generated embedded wallet first. Pre-mainnet, embedded wallets are funded by a dev-only faucet (`backend/app/routes/faucet.py`, hard-disabled when `settings.environment == "production"`) that transfers test USDC out of the deployer wallet — this only works because it's testnet money, not real funds.

**Cause:** Correct, deliberate simplification for the Development/Test/Show-the-app stage — one universal embedded-wallet flow was the fastest path to a working, demoable donation feature, and didn't require building wallet-connect UI before there was even one working end-to-end flow. Confirmed by Oscar (2026-07-09): no change needed pre-production.

**Solution:** Add a real wallet-connect integration (WalletConnect / MetaMask connector, via the already-installed Wagmi + Viem stack) so a crypto-native donor can connect their own external wallet and sign the `donate()` transaction directly, moving USDC straight from their own wallet to the beneficiary's address. This is additive, not a replacement: the embedded-wallet flow remains the default for non-crypto-native donors; this only adds a second signing path for donors who opt to connect their own wallet. Non-custodial "direct to beneficiary" transfer already holds true today regardless of which wallet signs — that property doesn't need to change, only *whose key* does the signing and *where their USDC comes from*.

**⚠️ Do not remove the embedded-wallet signing path.** The existing embedded-wallet `donate()` call (today's "Donate with Wallet" button) must be kept intact as its own internal code path when this new external-wallet-connect flow is added — item #2 ("Donate with Card") depends on that exact mechanism to push card-funded USDC on to the beneficiary. The end state has **two separate `donate()`-calling paths**: the preserved embedded-wallet one (now fired automatically at the end of the card flow, no longer its own donor-facing button) and this new external-wallet one (surfaced under the "Donate with Wallet" label). Confirmed by Oscar (2026-07-09) as an explicit implementation requirement, not a nice-to-have.

**Effort & Risk:** Medium. Wagmi already supports external connectors, but this needs new UI (a wallet picker / connect dialog), a second parallel signing path alongside the existing embedded-wallet signing code, and testing against a real external wallet (e.g. MetaMask mobile) instead of the dev-only faucet.

**Trigger to revisit:** Mainnet/Production launch itself — this is required before real crypto-native donors can use their own funds; the current embedded-wallet-only flow only works pre-production because of the dev-only testnet faucet.

---

## 4. Multi-chain support (Base, Celo)

**Situation:** PANGEA currently runs exclusively on Polygon PoS (Amoy testnet today, Polygon mainnet planned). The whitepaper's longer-term vision includes support for additional low-fee EVM chains — Base and Celo are named specifically, both chosen for low transaction costs and strong stablecoin/humanitarian-payments ecosystems.

**Cause:** Single-chain-first was the right call to ship a working product — supporting multiple chains multiplies the surface area of the contract, listener, wallet, and gas/paymaster logic before there was even one working end-to-end flow.

**Solution:** Deploy `PangeaDonation.sol` (or its then-current version) to each additional chain, extend the backend's event listener to watch multiple chains/contracts, and extend the smart-account/paymaster setup (ZeroDev) to support chain selection — ZeroDev already supports both Base and Celo, so this is largely a configuration and multi-listener exercise rather than new architecture.

**Effort & Risk:** Medium-high. Mostly parallel work (repeat the existing single-chain setup per chain), but multiplies operational surface area (more RPC endpoints, more paymasters to fund and monitor, cross-chain campaign identity questions if a campaign should be donatable from more than one chain).

**Trigger to revisit:** Bundled with item #2 in the whitepaper's roadmap — **V1.5 (Q1 2027)**.

---

## 5. Tip mechanism (~15% optional tip)

**Situation:** The whitepaper's entire sustainability model (§10.4) is built around a ~15% optional tip added on top of donations, funding PANGEA's own platform costs while preserving the "zero platform fee — 100% of every donation reaches the recipient" principle (the tip is separate from, not deducted from, the donation). There is currently zero code for this anywhere — no contract support, no backend handling, no frontend UI.

**Cause:** Was listed as a Beta-phase milestone in the original roadmap, but building a real payment/sustainability mechanism before there's a concrete institutional funding conversation to justify it would be premature — it's infrastructure for a revenue model with no active counterparty yet.

**Solution:** Add an optional tip amount to the donation flow (frontend UI: a suggested percentage or custom amount alongside the donation amount), processed as a second, separate on-chain transfer so it's visibly distinct from the donation itself in both the UI and the on-chain record — keeping the "100% reaches the recipient" claim auditable.

**Mechanism, confirmed 2026-07-10 (Oscar chose the "cheap version"):** The tip is a plain `USDC.transfer()` call straight from the donor's embedded wallet to a separate, publicly known PANGEA treasury address — **not** folded into the existing `donate()` call's `amount`, and **no change to `PangeaDonation.sol`** (the contract stays unaware a tip exists). Bundle both calls (the `donate()` call to the beneficiary + the plain transfer to the treasury) into a single ERC-4337 UserOperation via ZeroDev's batched-call support, so the donor signs once but the chain still records **two distinct `Transfer` events** — one to the beneficiary, one to the treasury address — rather than one lump transfer. Explicitly rejected: the "self-describing" alternative (extending/adding a contract event that labels an amount as "tip"), which would require a `PangeaDonation.sol` redeploy — same cost/risk category as the `campaignId`-indexing item (#1 above). Trade-off accepted: an on-chain observer must already know the treasury address by convention to recognize the second transfer as a tip; the chain itself doesn't label it.

**Effort & Risk:** Low-medium technically (mostly frontend + a second transfer batched into the existing donation UserOperation, no contract changes needed), but has real product/messaging risk — needs careful framing so it doesn't undercut the "zero platform fee" principle that's central to PANGEA's trust story.

**Trigger to revisit:** When a grant or NGO partnership is being finalized — i.e. once there's a real institutional funding conversation, not before.

---

## 6. Beneficiary cash-out (USDC → USD/EUR off-ramp)

**Situation:** Once real USDC lands on mainnet, a beneficiary needs a way to convert it into real currency they can actually spend. There is currently zero code for this anywhere — no contract, backend, or frontend trace. The embedded wallet's private key is not exportable by design, so a DIY route (manually moving funds to an exchange) isn't realistically available to beneficiaries as-is — an in-app off-ramp isn't optional, it's the only path.

**Cause:** Not needed until real (mainnet) funds exist — building a fiat off-ramp integration before there's real money to cash out would be premature, and pre-mainnet testnet USDC has no cash value to off-ramp in the first place.

**Solution:** Confirmed with Oscar (2026-07-10): a "Cash out" button built directly inside the PANGEA app (and, later, the web version), backed by a fiat off-ramp integration (e.g. Ramp Network, Transak, or MoonPay) that pays out to a bank account/card. The beneficiary never sees a wallet address or exports a private key — consistent with the "no crypto feel" principle.

**Effort & Risk:** Medium. New third-party off-ramp integration (KYC/compliance surface similar to item #2's on-ramp), plus a payout-to-bank flow; needs to work identically across the mobile app and the future web client.

**Trigger to revisit:** Before mainnet launch — this is the step that makes donations actually usable as real money for the beneficiary.

---

## How to add a new entry

Use the same structure: **Situation** (what's missing/what's the gap), **Cause** (why it wasn't built now / why it's deferred), **Solution** (what the eventual fix looks like), **Effort & Risk**, **Trigger to revisit** (the specific condition that should prompt picking this up — not just "later").
