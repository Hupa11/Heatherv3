"""
Corrigan Charge Gateway - Stub Module
"""

async def corrigan_check(card_input: str, proxy: str = None, timeout: int = 30) -> dict:
    """
    Placeholder for Corrigan charge gateway.
    This module was referenced but not included in the distribution.
    
    Args:
        card_input: Card data in format num|mon|yer|cvv
        proxy: Optional proxy URL
        timeout: Request timeout in seconds
    
    Returns:
        Dictionary with check results
    """
    return {
        "status": "declined",
        "message": "Corrigan gateway temporarily unavailable",
        "elapsed": 0.0
    }
