"""
portal/helpers/explain.py
=========================
Plain-English explanations for decisions and rule hits, written for a
customer with no technical background.
"""

RULE_PLAIN = {
    "R1": "The amount is much bigger than what this account usually spends.",
    "R2": "Too many payments were made in a few minutes.",
    "R3": "The payment came from a city far away, too soon after the last one.",
    "R4": "A large payment was made from a phone or computer never used before.",
    "R5": "A large payment was made in the middle of the night.",
    "R6": "Something in this payment is on our list of known fraudsters.",
    "R7": "Several payments just under ₹50,000 were made, as if to dodge limits.",
    "R8": "An account unused for many months suddenly made a big payment.",
    "R9": "A brand-new payee was paid right after a risky login or OTP from a new device.",
}

DECISION_TEXT = {
    "APPROVED": "This payment looks normal, so it went through.",
    "REVIEW": "This payment was held for a quick check by our team before any money moves.",
    "BLOCKED": "This payment was stopped. The money never left the account.",
    "PENDING": "This payment is still being checked.",
}

NEXT_STEP = {
    "APPROVED": "Nothing to do.",
    "REVIEW": "An analyst will look at it, and the customer is asked 'Was this you?'.",
    "BLOCKED": "The customer is told immediately and an analyst investigates.",
    "PENDING": "Please wait a moment.",
}


def inr(amount):
    """₹ with Indian digit grouping: 125000 -> ₹1,25,000."""
    value = float(amount or 0)
    negative = value < 0
    whole = str(int(round(abs(value))))
    if len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        whole = ",".join(groups) + "," + tail
    return f"{'-' if negative else ''}₹{whole}"


def rule_sentence(hit):
    """The best sentence for one rule hit: the SQL's own detail, else a default."""
    return hit.get("detail_text") or RULE_PLAIN.get(hit.get("rule_code"), "A warning sign was found.")


def decision_summary(status, score, hits, review_threshold=40, block_threshold=70):
    n = len(hits)
    if status == "APPROVED" and n == 0:
        reason = "No warning signs were found."
    elif status == "APPROVED":
        reason = (
            f"{n} small warning sign{'s' if n != 1 else ''} added up to {score} out of 100, "
            f"below the {review_threshold} needed to hold a payment."
        )
    else:
        reason = (
            f"{n} warning sign{'s' if n != 1 else ''} added up to a risk score of {score} out of 100 "
            f"(hold at {review_threshold}, block at {block_threshold})."
        )
    return {
        "headline": DECISION_TEXT.get(status, ""),
        "reason": reason,
        "next_step": NEXT_STEP.get(status, ""),
    }
