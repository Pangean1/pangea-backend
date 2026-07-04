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

A smaller, non-blocking partial mitigation already shipped pre-Production: the `message` field (previously always sent as `''`) is now used to embed a human-readable campaign identifier directly in each new donation's log, so at least the *decoded* event is self-describing even though it's not filterable. See commit history / session notes for when this landed.

**Effort & Risk:** High. New contract address is a breaking change across backend, frontend, and every previously-registered campaign. Not something to do casually post-mainnet without a clear migration plan.

**Trigger to revisit:** When PANGEA is ready to invest in a proper contract upgrade path (e.g. alongside a proxy/upgradeability pattern, if one gets adopted), or if an institutional partner specifically requires independently-filterable on-chain audit trails as a condition of engagement.

---

## 2. Fiat / card donations ("Donate with Card" via Ramp Network) + "Connect Wallet" button

**Situation:** The whitepaper's original design has two donation entry points: "Connect Wallet" (crypto-native users bring their own wallet) and "Donate with Card" (fiat on-ramp via Ramp Network, for non-crypto users). The current build has neither — every user gets one embedded-wallet flow (Google/email OTP login → auto-generated smart account), with no wallet-connect dialog at all.

**Cause:** This wasn't an oversight — it's a deliberate simplification that arguably fits PANGEA's "no crypto feel" principle *better* than the original two-path design, since it removes a decision point (and the word "wallet") from the donor's experience entirely. It was scoped out early to ship a working donation flow faster.

**Solution:** Add a fiat on-ramp integration (Ramp Network or equivalent) as an alternate funding path for donors who want to pay by card instead of holding USDC. This does not require reintroducing "Connect Wallet" as a concept to the donor — it can plug into the existing embedded-wallet flow as just another way to fund that wallet, preserving the "no crypto feel" principle rather than reverting it.

**Effort & Risk:** Medium. Mostly additive (new payment provider integration + backend webhook handling for on-ramp completion), doesn't require changing the existing donation contract or flow, but does add a third-party dependency (Ramp Network) and its compliance/KYC surface.

**Trigger to revisit:** Per the whitepaper's own roadmap, scheduled for **V1.5 (Q1 2027)**. Not urgent, not a bug — just not yet built.

---

## 3. Multi-chain support (Base, Celo)

**Situation:** PANGEA currently runs exclusively on Polygon PoS (Amoy testnet today, Polygon mainnet planned). The whitepaper's longer-term vision includes support for additional low-fee EVM chains — Base and Celo are named specifically, both chosen for low transaction costs and strong stablecoin/humanitarian-payments ecosystems.

**Cause:** Single-chain-first was the right call to ship a working product — supporting multiple chains multiplies the surface area of the contract, listener, wallet, and gas/paymaster logic before there was even one working end-to-end flow.

**Solution:** Deploy `PangeaDonation.sol` (or its then-current version) to each additional chain, extend the backend's event listener to watch multiple chains/contracts, and extend the smart-account/paymaster setup (ZeroDev) to support chain selection — ZeroDev already supports both Base and Celo, so this is largely a configuration and multi-listener exercise rather than new architecture.

**Effort & Risk:** Medium-high. Mostly parallel work (repeat the existing single-chain setup per chain), but multiplies operational surface area (more RPC endpoints, more paymasters to fund and monitor, cross-chain campaign identity questions if a campaign should be donatable from more than one chain).

**Trigger to revisit:** Bundled with item #2 in the whitepaper's roadmap — **V1.5 (Q1 2027)**.

---

## 4. Tip mechanism (~15% optional tip)

**Situation:** The whitepaper's entire sustainability model (§10.4) is built around a ~15% optional tip added on top of donations, funding PANGEA's own platform costs while preserving the "zero platform fee — 100% of every donation reaches the recipient" principle (the tip is separate from, not deducted from, the donation). There is currently zero code for this anywhere — no contract support, no backend handling, no frontend UI.

**Cause:** Was listed as a Beta-phase milestone in the original roadmap, but building a real payment/sustainability mechanism before there's a concrete institutional funding conversation to justify it would be premature — it's infrastructure for a revenue model with no active counterparty yet.

**Solution:** Add an optional tip amount to the donation flow (frontend UI: a suggested percentage or custom amount alongside the donation amount), processed as a second, separate on-chain transfer (or bundled into the same UserOperation as a second transfer) so it's visibly distinct from the donation itself in both the UI and the on-chain record — keeping the "100% reaches the recipient" claim auditable.

**Effort & Risk:** Low-medium technically (mostly frontend + a second transfer in the existing donation transaction), but has real product/messaging risk — needs careful framing so it doesn't undercut the "zero platform fee" principle that's central to PANGEA's trust story.

**Trigger to revisit:** When a grant or NGO partnership is being finalized — i.e. once there's a real institutional funding conversation, not before.

---

## How to add a new entry

Use the same structure: **Situation** (what's missing/what's the gap), **Cause** (why it wasn't built now / why it's deferred), **Solution** (what the eventual fix looks like), **Effort & Risk**, **Trigger to revisit** (the specific condition that should prompt picking this up — not just "later").
