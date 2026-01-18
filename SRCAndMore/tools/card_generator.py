"""
Card Generator - Generate Luhn-valid cards from a BIN pattern
"""

import random
import requests

def luhn_checksum(card_number):
    """Calculate Luhn checksum digit"""
    digits = [int(d) for d in card_number]
    odd_digits = digits[-1::-2]
    even_digits = digits[-2::-2]
    
    total = sum(odd_digits)
    for d in even_digits:
        total += sum(divmod(d * 2, 10))
    
    return (10 - (total % 10)) % 10

def generate_luhn_valid(cc_base, length=16):
    """Generate a Luhn-valid card number from a base"""
    cc = list(cc_base)
    while len(cc) < length - 1:
        cc.append(str(random.randint(0, 9)))
    
    partial = ''.join(cc)
    check_digit = luhn_checksum(partial + '0')
    
    digits = [int(d) for d in partial]
    odd_sum = sum(digits[-1::-2])
    even_sum = sum(sum(divmod(d * 2, 10)) for d in digits[-2::-2])
    total = odd_sum + even_sum
    check = (10 - (total % 10)) % 10
    
    return partial + str(check)

def fill_pattern(value, length, default_range):
    """Fill pattern with random digits where 'x' appears"""
    if not value:
        return str(random.randint(*default_range)).zfill(length)
    result = ""
    for ch in value:
        if ch.lower() == 'x':
            result += str(random.randint(0, 9))
        else:
            result += ch
    return result.zfill(length)[:length]

def generate_cards(bin_code, mes=None, ano=None, cvv=None, amount=10, brand=""):
    """
    Generate Luhn-valid cards from a BIN pattern
    
    Args:
        bin_code: BIN or pattern with 'x' for random digits (e.g., "414720xxxxxxxxxx")
        mes: Month pattern (optional, e.g., "xx" or "12")
        ano: Year pattern (optional, e.g., "xx" or "25")
        cvv: CVV pattern (optional, e.g., "xxx" or "123")
        amount: Number of cards to generate
        brand: Card brand for CVV length detection
    
    Returns:
        List of card strings in format "CARD|MM|YY|CVV"
    """
    cards = []
    
    brand_lower = brand.lower()
    cvv_len = 4 if "amex" in brand_lower or "american express" in brand_lower else 3
    
    bin_clean = bin_code.replace(" ", "").replace("-", "")
    
    for _ in range(amount):
        cc_list = []
        for ch in bin_clean:
            if ch.lower() == 'x':
                cc_list.append(str(random.randint(0, 9)))
            elif ch.isdigit():
                cc_list.append(ch)
        
        cc_partial = ''.join(cc_list)[:15]
        while len(cc_partial) < 15:
            cc_partial += str(random.randint(0, 9))
        
        digits = [int(d) for d in cc_partial]
        odd_sum = sum(digits[-1::-2])
        even_sum = sum(sum(divmod(d * 2, 10)) for d in digits[-2::-2])
        total = odd_sum + even_sum
        check = (10 - (total % 10)) % 10
        cc_final = cc_partial + str(check)
        
        mm = fill_pattern(mes, 2, (1, 12))
        if mm == "00":
            mm = str(random.randint(1, 12)).zfill(2)
        if int(mm) > 12:
            mm = str(random.randint(1, 12)).zfill(2)
            
        yy = fill_pattern(ano, 2, (25, 30))
        cvv_val = fill_pattern(cvv, cvv_len, (10**(cvv_len-1), 10**cvv_len - 1))
        
        cards.append(f"{cc_final}|{mm}|{yy}|{cvv_val}")
    
    return cards

def lookup_bin(bin_number):
    """Look up BIN information"""
    try:
        bin_6 = bin_number[:6]
        resp = requests.get(f"https://lookup.binlist.net/{bin_6}", timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            return {
                'bin': bin_6,
                'brand': data.get('scheme', 'Unknown'),
                'type': data.get('type', 'Unknown'),
                'level': data.get('brand', 'Unknown'),
                'bank': data.get('bank', {}).get('name', 'Unknown'),
                'country': data.get('country', {}).get('name', 'Unknown'),
                'emoji': data.get('country', {}).get('emoji', ''),
            }
    except:
        pass
    
    try:
        resp = requests.get(f"https://data.handyapi.com/bin/{bin_number[:6]}", timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            return {
                'bin': bin_number[:6],
                'brand': data.get('Scheme', 'Unknown'),
                'type': data.get('Type', 'Unknown'),
                'level': data.get('CardTier', 'Unknown'),
                'bank': data.get('Issuer', 'Unknown'),
                'country': data.get('Country', {}).get('Name', 'Unknown'),
                'emoji': data.get('Country', {}).get('A2', ''),
            }
    except:
        pass
    
    return None

def format_gen_response(cards, bin_info, bin_pattern, amount):
    """Format the generator response for Telegram"""
    cards_formatted = '\n'.join([f"<code>{c}</code>" for c in cards[:10]])
    
    if amount > 10:
        cards_formatted += f"\n<i>... and {amount - 10} more in file</i>"
    
    if bin_info:
        info_line = f"{bin_info['brand']} - {bin_info['type']} - {bin_info['level']}"
        bank = bin_info['bank']
        country = f"{bin_info['country']} {bin_info['emoji']}"
    else:
        info_line = "Unknown"
        bank = "Unknown"
        country = "Unknown"
    
    return f"""<b>CARD GENERATOR</b>

<b>BIN:</b> <code>{bin_pattern}</code>
<b>Amount:</b> {amount}

{cards_formatted}

<b>Info:</b> <code>{info_line}</code>
<b>Bank:</b> <code>{bank}</code>
<b>Country:</b> <code>{country}</code>"""
