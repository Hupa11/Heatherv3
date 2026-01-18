"""
Mass Check Handler
Concurrent card checking across multiple gates
"""

import asyncio
from typing import Callable, List, Tuple, Dict, Any
from concurrent.futures import ThreadPoolExecutor
import time


AVAILABLE_GATES = {
    "paypal_charge": {
        "name": "PayPal $5 Charge",
        "type": "CHARGE",
        "amount": "$5.00",
        "module": "gates.paypal_charge",
        "function": "paypal_charge_check",
    },
    "shopify": {
        "name": "Shopify Auth",
        "type": "AUTH",
        "amount": "$0",
        "module": "gates.shopify_nano",
        "function": "shopify_nano_check",
    },
    "stripe_charge": {
        "name": "Stripe $1 Charge",
        "type": "CHARGE",
        "amount": "$1.00",
        "module": "gates.stripe_charge",
        "function": "stripe_charge_check",
    },
    "braintree_auth": {
        "name": "Braintree Auth",
        "type": "AUTH",
        "amount": "$0",
        "module": "gates.braintree_auth",
        "function": "braintree_auth_check",
    },
    "checkout_auth": {
        "name": "Checkout.com Auth",
        "type": "AUTH",
        "amount": "$0",
        "module": "gates.checkout_auth",
        "function": "checkout_auth_check",
        "requires_invoice": True,
    },
}


def get_gate_function(gate_name: str) -> Callable:
    """Get gate check function by name"""
    if gate_name not in AVAILABLE_GATES:
        raise ValueError(f"Unknown gate: {gate_name}")
    
    gate_info = AVAILABLE_GATES[gate_name]
    module = __import__(gate_info["module"], fromlist=[gate_info["function"]])
    return getattr(module, gate_info["function"])


def _is_approved(result: str) -> bool:
    """
    Determine if a card result indicates approval
    This centralizes approval detection logic to ensure consistency
    
    CRITICAL: We check for the approval emoji/status first, not just keywords.
    A message like "DECLINED ❌ Insufficient Funds" is NOT approved.
    Only messages with "APPROVED ✅" or explicit success indicators are approved.
    """
    if not result:
        return False
    
    result_lower = result.lower()
    
    if "declined" in result_lower or "❌" in result:
        return False
    
    if "error" in result_lower and ":" in result:
        return False
    
    explicit_approval = [
        "approved ✅", "approved ✔", "approved", "success",
        "charged $", "charged 1", "charged 5", "3ds required",
        "cvv live", "card verified", "payment method added",
        "accesstoken", "cartid",
    ]
    
    return any(ind in result_lower for ind in explicit_approval) or "✅" in result


def check_single_card(card_data: str, gate_name: str, proxy=None, extra_params: Dict = None) -> Tuple[str, str, bool]:
    """
    Check a single card on a single gate
    
    Args:
        card_data: Card in format num|mm|yy|cvv
        gate_name: Name of gate to use
        proxy: Optional proxy dict
        extra_params: Extra parameters (like invoice_url for checkout.com)
    
    Returns: (card_data, result_message, is_approved)
        - is_approved: True if card was approved/live, False otherwise
        - Note: Gate return values indicate proxy health, but here we
          interpret the RESULT MESSAGE to determine approval status
    """
    try:
        parts = card_data.strip().split('|')
        if len(parts) < 4:
            return (card_data, "ERROR: Invalid card format", False)
        
        card_num = parts[0]
        card_mon = parts[1]
        card_yer = parts[2][-2:] if len(parts[2]) == 4 else parts[2]
        card_cvc = parts[3]
        
        gate_func = get_gate_function(gate_name)
        
        gate_info = AVAILABLE_GATES[gate_name]
        if gate_info.get("requires_invoice"):
            invoice_url = (extra_params or {}).get("invoice_url")
            if not invoice_url:
                return (card_data, "ERROR: Invoice URL required", False)
            result, _ = gate_func(card_num, card_mon, card_yer, card_cvc, invoice_url, proxy)
        else:
            result, _ = gate_func(card_num, card_mon, card_yer, card_cvc, proxy)
        
        is_approved = _is_approved(result)
        
        return (card_data, result, is_approved)
        
    except Exception as e:
        return (card_data, f"ERROR: {str(e)[:40]}", False)


def mass_check_sync(cards: List[str], gate_name: str, max_workers: int = 5, 
                    proxy=None, extra_params: Dict = None, 
                    callback: Callable = None) -> List[Tuple[str, str, bool]]:
    """
    Mass check cards synchronously with thread pool
    
    Args:
        cards: List of cards in format num|mm|yy|cvv
        gate_name: Gate to use
        max_workers: Max concurrent workers
        proxy: Optional proxy
        extra_params: Extra params for gate
        callback: Optional callback(card, result, success) for each result
    
    Returns: List of (card, result, success) tuples
    """
    results = []
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = []
        for card in cards:
            future = executor.submit(check_single_card, card, gate_name, proxy, extra_params)
            futures.append(future)
        
        for future in futures:
            result = future.result()
            results.append(result)
            
            if callback:
                callback(result[0], result[1], result[2])
    
    return results


async def mass_check_async(cards: List[str], gate_name: str, max_concurrent: int = 5,
                            proxy=None, extra_params: Dict = None,
                            callback: Callable = None) -> List[Tuple[str, str, bool]]:
    """
    Mass check cards asynchronously
    
    Args:
        cards: List of cards in format num|mm|yy|cvv
        gate_name: Gate to use
        max_concurrent: Max concurrent checks
        proxy: Optional proxy
        extra_params: Extra params for gate
        callback: Optional async callback for each result
    
    Returns: List of (card, result, success) tuples
    """
    semaphore = asyncio.Semaphore(max_concurrent)
    results = []
    
    async def check_with_semaphore(card: str) -> Tuple[str, str, bool]:
        async with semaphore:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None, 
                check_single_card, 
                card, 
                gate_name, 
                proxy, 
                extra_params
            )
            
            if callback:
                if asyncio.iscoroutinefunction(callback):
                    await callback(result[0], result[1], result[2])
                else:
                    callback(result[0], result[1], result[2])
            
            return result
    
    tasks = [check_with_semaphore(card) for card in cards]
    results = await asyncio.gather(*tasks)
    
    return results


def mass_check_multi_gate(cards: List[str], gate_names: List[str],
                           max_workers: int = 3, proxy=None,
                           stop_on_approved: bool = True) -> Dict[str, List[Tuple[str, str, bool]]]:
    """
    Check cards across multiple gates
    
    Args:
        cards: List of cards
        gate_names: List of gate names to use
        max_workers: Max concurrent workers per gate
        proxy: Optional proxy
        stop_on_approved: Stop checking a card once approved on any gate
    
    Returns: Dict of gate_name -> results
    """
    all_results = {gate: [] for gate in gate_names}
    approved_cards = set()
    
    for card in cards:
        if card in approved_cards:
            continue
        
        for gate_name in gate_names:
            if card in approved_cards and stop_on_approved:
                continue
            
            result = check_single_card(card, gate_name, proxy)
            all_results[gate_name].append(result)
            
            if result[2]:
                approved_cards.add(card)
                if stop_on_approved:
                    break
    
    return all_results


def get_available_gates() -> Dict[str, Dict]:
    """Get list of available gates with their info"""
    return AVAILABLE_GATES.copy()


def get_gate_info(gate_name: str) -> Dict:
    """Get info about a specific gate"""
    return AVAILABLE_GATES.get(gate_name, {})
