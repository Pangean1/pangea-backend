def display_name_and_initials(email: str | None, wallet_address: str) -> tuple[str, str]:
    """Derives a human-friendly display name and 2-letter avatar initials for
    a wallet address, from its owner's registered email when known.

    Never returns the email itself — only the part before "@" (e.g.
    "eduarmes" for eduarmes@gmail.com) — so a wallet address, already public
    on-chain, can never be paired with a full email just by browsing
    campaigns/donations/impact-updates in the app. See CLAUDE.md Changes1.txt
    (2026-09-27) and the OTP mass-send incident (2026-09-16) this guards
    against.

    Falls back to the shortened wallet address (and its first two hex chars)
    when no email is registered yet — same as the app's pre-existing
    wallet-only display, so accounts without an email on file (several
    pre-existing test wallets) never show blank.
    """
    if email and "@" in email:
        local_part = email.split("@")[0]
        if local_part:
            return local_part, local_part[:2].upper()

    if len(wallet_address) >= 10:
        short = f"{wallet_address[:6]}…{wallet_address[-4:]}"
    else:
        short = wallet_address
    initials = wallet_address[2:4].upper() if len(wallet_address) >= 4 else "—"
    return short, initials
