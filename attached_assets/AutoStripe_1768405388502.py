import requests
import asyncio
import aiohttp
from bs4 import BeautifulSoup
import uuid
import re
import json

class StripeChecker:
    def __init__(self, domain: str, username: str, password: str):
        self.domain = domain.rstrip('/')
        self.username = username
        self.password = password
        self.session = requests.Session()
        self.stripe_pk = None

    def _parse_value(self, data: str, start: str, end: str) -> str:
        try:
            start_pos = data.index(start) + len(start)
            end_pos = data.index(end, start_pos)
            return data[start_pos:end_pos]
        except ValueError:
            return "None"

    def login(self):
        """Login and extract Stripe public key."""
        print("[+] Attempting to login...")
        
        # Get login page
        login_url = f"{self.domain}/my-account/"
        headers = {
            "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "accept-language": "en-US,en;q=0.9",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36",
        }
        
        res = self.session.get(login_url, headers=headers)
        soup = BeautifulSoup(res.text, 'html.parser')
        
        # Find login form
        login_form = soup.find('form', {'class': 'login'})
        if not login_form:
            print("[!] Warning: Could not find standard login form, trying alternate methods...")
            login_form = soup.find('form', {'id': lambda x: x and 'login' in x.lower()}) or \
                        soup.find('form', {'action': lambda x: x and 'login' in x.lower()}) or \
                        soup.find('form', {'method': 'post'})
            
            if not login_form:
                raise Exception("❌ Could not find any login form")
        
        # Get hidden fields
        hidden_inputs = login_form.find_all('input', {'type': 'hidden'})
        form_data = {input.get('name'): input.get('value') for input in hidden_inputs if input.get('name')}
        
        # Add login credentials
        form_data.update({
            'username': self.username,
            'password': self.password,
            'login': 'Log in',
            'woocommerce-login-nonce': form_data.get('woocommerce-login-nonce', ''),
            '_wp_http_referer': form_data.get('_wp_http_referer', '/my-account/'),
        })
        
        # Perform login
        headers = {
            "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "content-type": "application/x-www-form-urlencoded",
            "origin": self.domain,
            "referer": login_url,
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36",
        }
        
        res = self.session.post(login_url, headers=headers, data=form_data)
        
        # Extract Stripe public key after login
        print("[+] Extracting Stripe public key...")
        res = self.session.get(f"{self.domain}/my-account/add-payment-method/")
        
        # Try different methods to find the key
        # Method 1: Look for woocommerce_stripe params
        match = re.search(r'wc_stripe_params\s*=\s*({[^}]+})', res.text)
        if match:
            try:
                params = json.loads(match.group(1))
                self.stripe_pk = params.get('key')
            except:
                pass
                
        # Method 2: Direct search for pk_live or pk_test
        if not self.stripe_pk:
            pk_match = re.search(r'pk_(live|test)_[0-9a-zA-Z]+', res.text)
            if pk_match:
                self.stripe_pk = pk_match.group(0)
                
        if not self.stripe_pk:
            raise Exception("❌ Could not extract Stripe public key")
            
        print(f"[+] Found Stripe public key: {self.stripe_pk}")

    def get_setup_nonce(self):
        print("[+] Getting setup nonce...")
        headers = {
            "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "accept-language": "en-US,en;q=0.9",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36",
        }

        res = self.session.get(
            f"{self.domain}/my-account/add-payment-method/",
            headers=headers
        )
        nonce = self._parse_value(res.text, '"createAndConfirmSetupIntentNonce":"', '"')
        print(f"[+] Found nonce: {nonce}")
        return nonce

    def create_payment_method(self, card_number: str, exp_month: str, exp_year: str, cvv: str):
        print("[+] Creating payment method...")
        headers = {
            "accept": "application/json",
            "content-type": "application/x-www-form-urlencoded",
            "origin": "https://js.stripe.com",
            "referer": "https://js.stripe.com/",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36",
        }

        # Ensure year is 2 digits
        exp_year = exp_year[-2:] if len(exp_year) > 2 else exp_year

        data = {
            "type": "card",
            "card[number]": card_number,
            "card[cvc]": cvv,
            "card[exp_year]": exp_year,
            "card[exp_month]": exp_month,
            "billing_details[address][postal_code]": "99501",
            "billing_details[address][country]": "US",
            "payment_user_agent": "stripe.js/b85ba7b837; stripe-js-v3/b85ba7b837; payment-element; deferred-intent",
            "key": self.stripe_pk,
            "_stripe_version": "2024-06-20",
        }

        res = requests.post(
            "https://api.stripe.com/v1/payment_methods",
            headers=headers,
            data=data
        )

        if res.status_code == 200:
            pm_id = res.json().get('id')
            print(f"[+] Got payment method ID: {pm_id}")
            return pm_id
        else:
            print("❌ Failed to create payment method")
            print(res.text)
            return None

    def confirm_setup_intent(self, payment_method_id: str, nonce: str):
        print("[+] Confirming setup intent...")
        headers = {
            "accept": "*/*",
            "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
            "origin": self.domain,
            "referer": f"{self.domain}/my-account/add-payment-method/",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36",
            "x-requested-with": "XMLHttpRequest",
        }

        data = {
            "action": "create_and_confirm_setup_intent",
            "wc-stripe-payment-method": payment_method_id,
            "wc-stripe-payment-type": "card",
            "_ajax_nonce": nonce,
        }

        res = self.session.post(
            f"{self.domain}/?wc-ajax=wc_stripe_create_and_confirm_setup_intent",
            headers=headers,
            data=data
        )
        return res.text

    def check_card(self, card_number: str, exp_month: str, exp_year: str, cvv: str) -> dict:
        try:
            # Step 1: Login and get Stripe key
            self.login()
            
            # Step 2: Get setup nonce
            nonce = self.get_setup_nonce()
            
            # Step 3: Create payment method
            pm_id = self.create_payment_method(card_number, exp_month, exp_year, cvv)
            if not pm_id:
                return {
                    "success": False,
                    "message": "Failed to create payment method",
                    "card": f"{card_number}|{exp_month}|{exp_year}|{cvv}"
                }
            
            # Step 4: Confirm setup intent
            result = self.confirm_setup_intent(pm_id, nonce)
            
            return {
                "success": "error" not in result.lower(),
                "message": result,
                "payment_method_id": pm_id,
                "card": f"{card_number}|{exp_month}|{exp_year}|{cvv}"
            }
            
        except Exception as e:
            return {
                "success": False,
                "message": str(e),
                "card": f"{card_number}|{exp_month}|{exp_year}|{cvv}"
            }

def main():
    print("=== Stripe Card Checker ===")
    print("Format: card_number|month|year|cvv")
    print("Example: 4242424242424242|01|2025|123")
    print("=" * 30 + "\n")
    
    domain = input("Enter the domain: ").strip()
    username = input("Enter your username/email: ").strip()
    password = input("Enter your password: ").strip()
    card_string = input("Enter card details (number|month|year|cvv): ").strip()
    
    try:
        number, month, year, cvv = card_string.strip().split("|")
        checker = StripeChecker(domain, username, password)
        result = checker.check_card(number, month, year, cvv)
        print("\nResult:")
        print(json.dumps(result, indent=2))
    except ValueError:
        print("❌ Invalid card format. Please use: number|month|year|cvv")
    except Exception as e:
        print(f"❌ Error: {str(e)}")

if __name__ == "__main__":
    main()
