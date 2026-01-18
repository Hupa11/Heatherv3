"""
Stripe SK Charge Gate - Uses stored secret key to charge cards
Performs real charges via Stripe API
"""

import os
import requests
from typing import Tuple


STRIPE_SK = os.environ.get("STRIPE_SK_KEY", "")


def stripe_sk_charge(card_num: str, card_mon: str, card_yer: str, card_cvc: str,
                     amount_cents: int = 100, proxy: dict = None) -> Tuple[str, bool]:
    """
    Charge a card using stored Stripe SK
    
    Args:
        card_num: Card number
        card_mon: Expiry month
        card_yer: Expiry year
        card_cvc: CVV/CVC
        amount_cents: Amount to charge in cents (default $1.00)
        proxy: Optional proxy dict
    
    Returns:
        Tuple of (status_message, proxy_alive)
    """
    if not STRIPE_SK:
        return ("Error: STRIPE_SK_KEY not configured", False)
    
    if len(card_yer) == 2:
        card_yer = "20" + card_yer
    
    try:
        session = requests.Session()
        if proxy:
            session.proxies = proxy
        
        headers = {
            'Authorization': f'Bearer {STRIPE_SK}',
            'Content-Type': 'application/x-www-form-urlencoded',
        }
        
        token_data = {
            'card[number]': card_num,
            'card[exp_month]': card_mon,
            'card[exp_year]': card_yer,
            'card[cvc]': card_cvc,
        }
        
        token_resp = session.post('https://api.stripe.com/v1/tokens', 
                                  headers=headers, data=token_data, timeout=20)
        token_json = token_resp.json()
        
        if 'error' in token_json:
            error_msg = token_json['error'].get('message', 'Unknown error')
            error_code = token_json['error'].get('code', '')
            decline_code = token_json['error'].get('decline_code', '')
            
            if 'test' in error_msg.lower():
                return ("DECLINED - Live Mode Test Card", True)
            if error_code == 'incorrect_cvc':
                return ("CCN LIVE - Incorrect CVV", True)
            if error_code == 'invalid_cvc':
                return ("CCN LIVE - Invalid CVV", True)
            if error_code == 'expired_card':
                return ("DECLINED - Expired Card", True)
            if decline_code == 'insufficient_funds':
                return ("CCN LIVE - Insufficient Funds", True)
            if decline_code == 'lost_card':
                return ("DECLINED - Lost Card", True)
            if decline_code == 'stolen_card':
                return ("DECLINED - Stolen Card", True)
            if error_code == 'card_declined':
                return (f"DECLINED - {error_msg[:50]}", True)
            return (f"DECLINED - {error_msg[:50]}", True)
        
        token_id = token_json.get('id')
        if not token_id:
            return ("DECLINED - Token creation failed", True)
        
        charge_data = {
            'amount': amount_cents,
            'currency': 'usd',
            'source': token_id,
            'description': 'Card validation',
        }
        
        charge_resp = session.post('https://api.stripe.com/v1/charges',
                                   headers=headers, data=charge_data, timeout=20)
        charge_json = charge_resp.json()
        
        if 'error' in charge_json:
            error_msg = charge_json['error'].get('message', 'Unknown error')
            error_code = charge_json['error'].get('code', '')
            decline_code = charge_json['error'].get('decline_code', '')
            
            if error_code == 'incorrect_cvc' or 'cvc' in error_msg.lower():
                return ("CCN LIVE - CVV Issue", True)
            if decline_code == 'insufficient_funds':
                return ("CCN LIVE - Insufficient Funds", True)
            if 'expired' in error_msg.lower():
                return ("DECLINED - Expired Card", True)
            if decline_code in ('lost_card', 'stolen_card', 'pickup_card'):
                return (f"DECLINED - {decline_code.replace('_', ' ').title()}", True)
            if error_code == 'card_declined':
                return (f"DECLINED - {decline_code or error_msg[:40]}", True)
            return (f"DECLINED - {error_msg[:50]}", True)
        
        if charge_json.get('paid') and charge_json.get('status') == 'succeeded':
            amount = charge_json.get('amount', 0) / 100
            return (f"CHARGED ${amount:.2f}", True)
        
        return ("DECLINED - Charge failed", True)
        
    except requests.exceptions.Timeout:
        return ("Error: Request timeout", False)
    except requests.exceptions.RequestException:
        return ("Error: Network issue", False)
    except Exception as e:
        return (f"Error: {str(e)[:40]}", False)


def stripe_sk_charge_1(card_num: str, card_mon: str, card_yer: str, card_cvc: str,
                       proxy: dict = None) -> Tuple[str, bool]:
    """$1.00 charge"""
    return stripe_sk_charge(card_num, card_mon, card_yer, card_cvc, amount_cents=100, proxy=proxy)


def stripe_sk_charge_5(card_num: str, card_mon: str, card_yer: str, card_cvc: str,
                       proxy: dict = None) -> Tuple[str, bool]:
    """$5.00 charge"""
    return stripe_sk_charge(card_num, card_mon, card_yer, card_cvc, amount_cents=500, proxy=proxy)


if __name__ == "__main__":
    result, alive = stripe_sk_charge_1("4000000000000002", "12", "29", "123")
    print(f"Result: {result}, Proxy OK: {alive}")
