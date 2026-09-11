# Wallet Recovery Guide — Same Email, Two Phones

## The problem

Each PANGEA account's embedded wallet key is generated **locally on the phone**, the first time that email signs in on that device, and is never synced to any server (non-custodial by design — see `docs/WHITEPAPER.md`).

If the same email signs in on a **second** phone that has never seen that account before, the app has no way to know a wallet already exists for it — so it silently generates a **second, unrelated** private key on that phone.

Result: the account now has two different wallets that don't know about each other.
- Whichever phone signed in **first** keeps working normally — its wallet is the one already registered to the account on the backend, so its donations/campaigns show up correctly.
- The **second** phone can still view the account's existing history (campaigns, past donations), but any donation or campaign creation it tries to make will use its own new wallet — not the one the account's history is under.

This is not a bug and not data loss — nothing is deleted. It's a mismatch between which wallet key a given phone is holding and which wallet the account is actually known by.

## How to tell this is what's happening

Open the app on the affected phone, go to **Wallet recovery (Advanced)**, and compare the two addresses shown:
- **Registered wallet** — the address the backend has on file for this account.
- **This device's active wallet** — the address this phone is currently signing with.

If they differ, the screen shows:
> ⚠ This device does not have your real wallet key.

If they match, it shows:
> ✓ This device has the correct key.

## Fix — step by step

You need **both phones in hand** at the same time. The correct key only ever exists on the phone that has it — there is no way to recover it from the server or from the other phone alone.

1. **On the phone that already works correctly** (the one whose wallet matches the account's history):
   - Open the app, sign in, go to **Wallet recovery (Advanced)**.
   - Confirm it shows **✓ This device has the correct key.**
   - Tap **Show private key**, confirm the warning, then tap **Copy key**.

2. **Send that key to the second phone** using a method only you control — e.g. a private note-to-self, a password manager, or typing it directly on the second phone. Never send it over email, SMS, or any channel someone else could read; whoever holds this key controls the wallet's funds.

3. **On the second phone** (the one with the wrong/mismatched wallet):
   - Open the app, sign in with the same email, go to **Wallet recovery (Advanced)**.
   - Confirm it currently shows **⚠ This device does not have your real wallet key.**
   - Paste the copied key into **Restore a key on this device** and tap **Restore key on this device**.
   - If the pasted key's address doesn't match the account's registered wallet, the app will warn you before proceeding — this is expected if you pasted the wrong key; re-check step 1 in that case.

4. **Verify:** the second phone's screen should now show **✓ This device has the correct key.**, and its registered/device addresses should match. From this point on, both phones sign with the same wallet, and both correctly show the account's full donation/campaign history.

## Notes

- This is a manual, one-time recovery step — there is currently no automatic multi-device sync for embedded wallets.
- The private key is only ever shown on-screen and only copied through the device clipboard — it is never transmitted through PANGEA's backend at any point in this flow.
- If neither phone shows the correct key (e.g. the original phone was lost before recovery), the wallet cannot be recovered — this is the same tradeoff as any non-custodial wallet with no seed-phrase backup taken. See "Beneficiary cash-out" and open device-loss items in `docs/PRODUCTION_STAGE_CHANGES.md` for related pre-mainnet considerations.
