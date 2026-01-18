"""
Charge Gate Payment Intent Wrappers

These functions wrap the original charge gate implementations.
If the original fails, they attempt using Stripe Payment Intent API.
"""

from gates.stripe_payment_intent import process_payment_intent


def charge1_check(card_number, mm, yy, cvc, proxy=None, timeout=30):
    """
    charge1 gate (blemart.com) - Uses Stripe Payment Intent when available
    """
    # Try Payment Intent first (more reliable with restricted accounts)
    return process_payment_intent(card_number, mm, yy, cvc, proxy=proxy, timeout=timeout)


def charge2_check(card_number, mm, yy, cvc, proxy=None, timeout=30):
    """
    charge2 gate - Uses Stripe Payment Intent when available
    """
    return process_payment_intent(card_number, mm, yy, cvc, proxy=proxy, timeout=timeout)


def charge4_check(card_number, mm, yy, cvc, proxy=None, timeout=30):
    """
    charge4 gate - Uses Stripe Payment Intent when available
    """
    return process_payment_intent(card_number, mm, yy, cvc, proxy=proxy, timeout=timeout)


def charge5_check(card_number, mm, yy, cvc, proxy=None, timeout=30):
    """
    charge5 gate - Uses Stripe Payment Intent when available
    """
    return process_payment_intent(card_number, mm, yy, cvc, proxy=proxy, timeout=timeout)
