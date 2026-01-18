#!/usr/bin/env python3
"""
CLI Card Checker - Direct Gateway Testing Tool
Tests gates without Telegram bot wrapper for easier debugging
"""

import asyncio
import sys
import os
from pathlib import Path

# Add current directory to path
sys.path.insert(0, str(Path(__file__).parent))

# Import config first
import config

# Import available gate modules
try:
    from gates import (
        stripe_auth, paypal_charge, braintree_auth, shopify_nano,
        stripe_charge, lions_club, stripe_charity
    )
    GATES_AVAILABLE = True
except ImportError as e:
    print(f"⚠️ Warning: Some gates unavailable: {e}")
    GATES_AVAILABLE = False

# Import rainbowponk gates
try:
    from gates import rainbowponk_stripe, rainbowponk_paypal, rainbowponk_adyen, rainbowponk_amazon
    RAINBOWPONK_AVAILABLE = True
except ImportError:
    RAINBOWPONK_AVAILABLE = False
    print("⚠️ RainbowPonk gates not available")

# Color codes
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
RESET = "\033[0m"

# Gate mappings
GATES = {}

if GATES_AVAILABLE:
    GATES.update({
        'sa': ('Stripe Auth', stripe_auth.check_card),
        'ppc': ('PayPal $5', paypal_charge.check_card),
        'b3': ('Braintree Auth', braintree_auth.check_card),
        'sn': ('Shopify Auth', shopify_nano.check_card),
        'skc': ('Stripe Charge $1', stripe_charge.check_card),
        'lc5': ('Lions Club $5', lions_club.check_card),
        'sc2': ('Stripe Charity', stripe_charity.check_card),
    })

# Add rainbowponk gates if available
if RAINBOWPONK_AVAILABLE:
    GATES.update({
        'rbstripe1': ('RainbowPonk Stripe v1', lambda card, proxy: rainbowponk_stripe.check_card_v1(card, proxy)),
        'rbstripe2': ('RainbowPonk Stripe v2', lambda card, proxy: rainbowponk_stripe.check_card_v2(card, proxy)),
        'rbstripe3': ('RainbowPonk Stripe v3', lambda card, proxy: rainbowponk_stripe.check_card_v3(card, proxy)),
        'rbstripe4': ('RainbowPonk Stripe v4', lambda card, proxy: rainbowponk_stripe.check_card_v4(card, proxy)),
        'rbstripe5': ('RainbowPonk Stripe v5', lambda card, proxy: rainbowponk_stripe.check_card_v5(card, proxy)),
        'rbpp5': ('RainbowPonk PayPal $5', lambda card, proxy: rainbowponk_paypal.check_card_pp5(card, proxy)),
        'rbpp10': ('RainbowPonk PayPal $10', lambda card, proxy: rainbowponk_paypal.check_card_pp10(card, proxy)),
        'rbbt1': ('RainbowPonk Braintree $1', lambda card, proxy: rainbowponk_paypal.check_card_bt1(card, proxy)),
        'rbadyen01': ('RainbowPonk Adyen $0.1', lambda card, proxy: rainbowponk_adyen.check_card_adyen01(card, proxy)),
        'rbadyen1': ('RainbowPonk Adyen $1', lambda card, proxy: rainbowponk_adyen.check_card_adyen1(card, proxy)),
        'rbadyen2': ('RainbowPonk Adyen $2', lambda card, proxy: rainbowponk_adyen.check_card_adyen2(card, proxy)),
        'rbadyen5': ('RainbowPonk Adyen $5', lambda card, proxy: rainbowponk_adyen.check_card_adyen5(card, proxy)),
        'rbamzau': ('RainbowPonk Amazon AU', lambda card, proxy: rainbowponk_amazon.check_card_au(card, proxy)),
        'rbamzca': ('RainbowPonk Amazon CA', lambda card, proxy: rainbowponk_amazon.check_card_ca(card, proxy)),
        'rbamzmx': ('RainbowPonk Amazon MX', lambda card, proxy: rainbowponk_amazon.check_card_mx(card, proxy)),
        'rbamzjp': ('RainbowPonk Amazon JP', lambda card, proxy: rainbowponk_amazon.check_card_jp(card, proxy)),
        'rbamzit': ('RainbowPonk Amazon IT', lambda card, proxy: rainbowponk_amazon.check_card_it(card, proxy)),
    })

def print_config_debug():
    """Print configuration debugging info"""
    print(f"\n{BLUE}═══════════════════════════════════════{RESET}")
    print(f"{BLUE}        Configuration Debug Info        {RESET}")
    print(f"{BLUE}═══════════════════════════════════════{RESET}\n")
    
    # Proxy
    proxy = getattr(config, 'PROXY', None)
    print(f"{'Proxy:':<25} {GREEN if proxy else RED}{proxy if proxy else 'NOT SET'}{RESET}")
    
    # Stripe config
    stripe_sk = getattr(config, 'STRIPE_SECRET_KEY', '')
    print(f"{'Stripe Secret Key:':<25} {GREEN if stripe_sk else RED}{'SET (' + stripe_sk[:20] + '...)' if stripe_sk else 'NOT SET'}{RESET}")
    
    stripe_key_file = getattr(config, 'STRIPE_KEY_FILE', 'stripe_sk_live_keys.txt')
    print(f"{'Stripe Key File:':<25} {stripe_key_file}")
    
    # Check if stripe key file exists
    sk_path = Path(__file__).parent / stripe_key_file
    if sk_path.exists():
        with open(sk_path) as f:
            keys = [line.strip() for line in f if line.strip()]
            print(f"{'  Keys in file:':<25} {GREEN}{len(keys)}{RESET}")
            if keys:
                print(f"{'  First key preview:':<25} {keys[0][:30]}...")
    else:
        print(f"{'  File status:':<25} {RED}NOT FOUND: {sk_path}{RESET}")
    
    # Other settings
    timeout = getattr(config, 'REQUEST_TIMEOUT', 'NOT SET')
    print(f"{'Request Timeout:':<25} {timeout}")
    
    retry = getattr(config, 'RETRY_ATTEMPTS', 'NOT SET')
    print(f"{'Retry Attempts:':<25} {retry}")
    
    # Gateway amounts
    amounts = getattr(config, 'GATEWAY_AMOUNTS', {})
    if amounts:
        print(f"\n{YELLOW}Gateway Amounts:{RESET}")
        for gw, amt in list(amounts.items())[:5]:
            print(f"  {gw:<20} ${amt:.2f}")
    
    print(f"\n{BLUE}═══════════════════════════════════════{RESET}\n")

async def check_card(gate_code, card_data):
    """Check a single card against a specific gate"""
    if gate_code not in GATES:
        print(f"{RED}❌ Unknown gate: {gate_code}{RESET}")
        print(f"\n{YELLOW}Available gates:{RESET}")
        for code, (name, _) in sorted(GATES.items()):
            print(f"  {code:12} - {name}")
        return
    
    gate_name, gate_func = GATES[gate_code]
    proxy = getattr(config, 'PROXY', None)
    
    print(f"\n{BLUE}═══════════════════════════════════════{RESET}")
    print(f"{BLUE}             Testing Card               {RESET}")
    print(f"{BLUE}═══════════════════════════════════════{RESET}")
    print(f"Gate:  {YELLOW}{gate_name}{RESET} ({gate_code})")
    print(f"Card:  {card_data}")
    print(f"Proxy: {proxy if proxy else RED + 'None' + RESET}")
    print(f"{BLUE}{'═' * 43}{RESET}\n")
    
    try:
        result = await gate_func(card_data, proxy)
        
        # Parse result
        if isinstance(result, tuple) and len(result) >= 3:
            status, message, response = result[:3]
            
            # Color based on status
            if "Approved" in status or "CCN" in status or "LIVE" in status or "✅" in status:
                color = GREEN
                symbol = "✅"
            elif "Declined" in status or "Dead" in status or "❌" in status:
                color = RED
                symbol = "❌"
            else:
                color = YELLOW
                symbol = "⚠️"
            
            print(f"{color}{symbol} Status:   {status}{RESET}")
            print(f"   Message:  {message}")
            print(f"   Response: {response}")
        else:
            print(f"{YELLOW}⚠️ Unexpected result format:{RESET}")
            print(result)
            
    except Exception as e:
        print(f"{RED}❌ Error: {e}{RESET}")
        print(f"\n{YELLOW}Full traceback:{RESET}")
        import traceback
        traceback.print_exc()

async def batch_check(gate_code, file_path):
    """Check multiple cards from a file"""
    if not Path(file_path).exists():
        print(f"{RED}❌ File not found: {file_path}{RESET}")
        return
    
    with open(file_path) as f:
        cards = [line.strip() for line in f if line.strip() and '|' in line]
    
    if not cards:
        print(f"{RED}❌ No valid cards found in file{RESET}")
        return
    
    print(f"\n{BLUE}═══ Batch Check ═══{RESET}")
    print(f"Gate:  {gate_code}")
    print(f"Cards: {len(cards)}")
    print(f"{BLUE}{'═' * 30}{RESET}\n")
    
    approved = 0
    declined = 0
    errors = 0
    
    for i, card in enumerate(cards, 1):
        print(f"\n{BLUE}[{i}/{len(cards)}]{RESET} {card}")
        
        try:
            gate_name, gate_func = GATES[gate_code]
            proxy = getattr(config, 'PROXY', None)
            result = await gate_func(card, proxy)
            
            if isinstance(result, tuple) and len(result) >= 3:
                status = result[0]
                if "Approved" in status or "LIVE" in status:
                    approved += 1
                    print(f"  {GREEN}✅ {status}{RESET}")
                elif "Declined" in status or "Dead" in status:
                    declined += 1
                    print(f"  {RED}❌ {status}{RESET}")
                else:
                    print(f"  {YELLOW}⚠️ {status}{RESET}")
        except Exception as e:
            errors += 1
            print(f"  {RED}❌ Error: {e}{RESET}")
        
        # Small delay between checks
        await asyncio.sleep(0.5)
    
    print(f"\n{BLUE}═══════════════ Results ═══════════════{RESET}")
    print(f"Total:    {len(cards)}")
    print(f"{GREEN}Approved: {approved}{RESET}")
    print(f"{RED}Declined: {declined}{RESET}")
    print(f"{YELLOW}Errors:   {errors}{RESET}")
    print(f"{BLUE}═══════════════════════════════════════{RESET}\n")

def show_usage():
    """Show usage information"""
    print(f"""
{BLUE}═══════════════════════════════════════════════════════════
    CLI Card Checker - Gateway Testing Tool
═══════════════════════════════════════════════════════════{RESET}

{YELLOW}USAGE:{RESET}
    python3 cli_checker.py <command> [arguments]

{YELLOW}COMMANDS:{RESET}
    
    {GREEN}check <gate> <card>{RESET}
        Check a single card
        Example: python3 cli_checker.py check rbstripe1 4388576200115627|05|30|636
    
    {GREEN}batch <gate> <file>{RESET}
        Check multiple cards from a file
        Example: python3 cli_checker.py batch ppc cards.txt
    
    {GREEN}list{RESET}
        List all available gates
    
    {GREEN}config{RESET}
        Show configuration debug info (SK keys, proxy, etc)
    
    {GREEN}test <gate>{RESET}
        Test specific gate with sample card
        Example: python3 cli_checker.py test rbstripe1

{YELLOW}AVAILABLE GATES:{RESET}
    Standard: sa, ppc, b3, sn, skc, lc5, sc2
    RainbowPonk: rbstripe1-5, rbpp5, rbpp10, rbbt1, 
                 rbadyen01/1/2/5, rbamzau/ca/mx/jp/it

{BLUE}═══════════════════════════════════════════════════════════{RESET}
""")

async def test_gate(gate_code):
    """Test specific gate with sample card"""
    test_card = "4388576200115627|05|30|636"
    
    print(f"\n{BLUE}═══ Testing Gate ═══{RESET}")
    print(f"Gate: {gate_code}")
    print(f"Test Card: {test_card}\n")
    
    await check_card(gate_code, test_card)

def main():
    if len(sys.argv) < 2:
        show_usage()
        sys.exit(1)
    
    command = sys.argv[1].lower()
    
    if command == "config":
        print_config_debug()
    
    elif command == "list":
        print(f"\n{BLUE}═══════════════ Available Gates ═══════════════{RESET}\n")
        for code, (name, _) in sorted(GATES.items()):
            print(f"  {GREEN}{code:12}{RESET} - {name}")
        print(f"\n{BLUE}═══════════════════════════════════════════════{RESET}\n")
    
    elif command == "check":
        if len(sys.argv) < 4:
            print(f"{RED}Usage: python3 cli_checker.py check <gate> <card>{RESET}")
            print(f"Example: python3 cli_checker.py check rbstripe1 4388576200115627|05|30|636")
            sys.exit(1)
        gate_code = sys.argv[2].lower()
        card_data = sys.argv[3]
        asyncio.run(check_card(gate_code, card_data))
    
    elif command == "batch":
        if len(sys.argv) < 4:
            print(f"{RED}Usage: python3 cli_checker.py batch <gate> <file>{RESET}")
            sys.exit(1)
        gate_code = sys.argv[2].lower()
        file_path = sys.argv[3]
        asyncio.run(batch_check(gate_code, file_path))
    
    elif command == "test":
        if len(sys.argv) < 3:
            print(f"{RED}Usage: python3 cli_checker.py test <gate>{RESET}")
            sys.exit(1)
        gate_code = sys.argv[2].lower()
        asyncio.run(test_gate(gate_code))
    
    else:
        print(f"{RED}Unknown command: {command}{RESET}")
        show_usage()
        sys.exit(1)

if __name__ == "__main__":
    main()
