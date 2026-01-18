"""
Stripe SK (Secret Key) Validator
Checks if a Stripe secret key is valid and returns account info
"""

import requests
from typing import Tuple, Dict, Any


def validate_stripe_sk(sk_key: str) -> Tuple[bool, Dict[str, Any]]:
    """
    Validate a Stripe secret key and get account info
    
    Returns:
        Tuple of (is_valid, account_info_dict)
    """
    if not sk_key.startswith('sk_live_') and not sk_key.startswith('sk_test_'):
        return False, {"error": "Invalid key format. Must start with sk_live_ or sk_test_"}
    
    try:
        headers = {
            'Authorization': f'Bearer {sk_key}',
        }
        
        response = requests.get('https://api.stripe.com/v1/account', headers=headers, timeout=15)
        result = response.json()
        
        if 'error' in result:
            error_msg = result['error'].get('message', 'Unknown error')
            return False, {"error": error_msg}
        
        account_info = {
            "valid": True,
            "account_id": result.get('id', 'Unknown'),
            "business_name": result.get('business_profile', {}).get('name', 'N/A'),
            "country": result.get('country', 'Unknown'),
            "email": result.get('email', 'N/A'),
            "charges_enabled": result.get('charges_enabled', False),
            "payouts_enabled": result.get('payouts_enabled', False),
            "type": result.get('type', 'Unknown'),
            "default_currency": result.get('default_currency', 'Unknown').upper(),
        }
        
        balance_response = requests.get('https://api.stripe.com/v1/balance', headers=headers, timeout=10)
        if balance_response.status_code == 200:
            balance = balance_response.json()
            available = balance.get('available', [])
            if available:
                amount = available[0].get('amount', 0) / 100
                currency = available[0].get('currency', 'usd').upper()
                account_info['balance'] = f"${amount:.2f} {currency}"
            else:
                account_info['balance'] = "N/A"
        else:
            account_info['balance'] = "Access denied"
        
        return True, account_info
        
    except requests.exceptions.Timeout:
        return False, {"error": "Request timeout"}
    except requests.exceptions.RequestException as e:
        return False, {"error": f"Network error: {str(e)[:50]}"}
    except Exception as e:
        return False, {"error": f"Error: {str(e)[:50]}"}


def format_sk_response(sk_key: str, valid: bool, info: Dict[str, Any]) -> str:
    """Format SK validation response for Telegram"""
    key_type = "LIVE" if "sk_live_" in sk_key else "TEST"
    
    if not valid:
        return f"""<b>━━━━━ SK VALIDATOR ━━━━━</b>

<b>Key:</b> <code>{sk_key}</code>
<b>Type:</b> {key_type}
<b>Status:</b> ❌ <b>INVALID</b>

<b>Error:</b> {info.get('error', 'Unknown error')}

<b>━━━━━━━━━━━━━━━━━━━━</b>"""
    
    charges = "✅" if info.get('charges_enabled') else "❌"
    payouts = "✅" if info.get('payouts_enabled') else "❌"
    
    return f"""<b>━━━━━ SK VALIDATOR ━━━━━</b>

<b>Key:</b> <code>{sk_key}</code>
<b>Type:</b> {key_type}
<b>Status:</b> ✅ <b>VALID</b>

<b>Account ID:</b> <code>{info.get('account_id', 'N/A')}</code>
<b>Business:</b> {info.get('business_name', 'N/A')}
<b>Email:</b> {info.get('email', 'N/A')}
<b>Country:</b> {info.get('country', 'N/A')}
<b>Currency:</b> {info.get('default_currency', 'N/A')}
<b>Account Type:</b> {info.get('type', 'N/A')}

<b>Charges:</b> {charges}
<b>Payouts:</b> {payouts}
<b>Balance:</b> {info.get('balance', 'N/A')}

<b>━━━━━━━━━━━━━━━━━━━━</b>"""


if __name__ == "__main__":
    test_key = "sk_live_test123"
    valid, info = validate_stripe_sk(test_key)
    print(format_sk_response(test_key, valid, info))
