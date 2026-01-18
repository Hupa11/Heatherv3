"""
Configuration loader for Phase 6 bot.
Loads settings from .env file with sensible defaults.
"""
import os
from pathlib import Path

# Load .env file if it exists
ENV_FILE = Path(__file__).parent / '.env'
if ENV_FILE.exists():
    try:
        from dotenv import load_dotenv
        load_dotenv(ENV_FILE)
    except ImportError:
        print("[WARN] python-dotenv not installed. Reading .env manually.")
        # Simple manual .env parser
        with open(ENV_FILE) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    os.environ[key.strip()] = value.strip()
else:
    print("[WARN] .env file not found. Using environment variables or defaults.")

# ============================================================================
# Telegram Bot Configuration
# ============================================================================
BOT_TOKEN = os.getenv('BOT_TOKEN', '')
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN not set. Please set BOT_TOKEN in .env or environment.")

# ============================================================================
# Proxy Configuration
# ============================================================================
PROXY_HTTP = os.getenv('PROXY_HTTP', 'http://username:password@proxy-host.com:port')
PROXY_HTTPS = os.getenv('PROXY_HTTPS', 'http://username:password@proxy-host.com:port')

PROXY = {
    'http': PROXY_HTTP,
    'https': PROXY_HTTPS
}

# ============================================================================
# Gateway Test Amounts (in USD)
# ============================================================================
GATEWAY_AMOUNTS = {
    # PayPal variants
    'paypal_charge': float(os.getenv('PAYPAL_CHARGE_AMOUNT', '5.00')),
    'paypal_charge2': float(os.getenv('PAYPAL_CHARGE2_AMOUNT', '0.01')),
    'paypal_charge3': float(os.getenv('PAYPAL_CHARGE3_AMOUNT', '1.00')),
    
    # Shopify
    'shopify_nano': float(os.getenv('SHOPIFY_NANO_AMOUNT', '0.01')),
    
    # Braintree
    'braintree': float(os.getenv('BRAINTREE_AMOUNT', '1.00')),
    
    # Site-specific gateways
    'blemart': float(os.getenv('BLEMART_AMOUNT', '0.01')),
    'districtpeople': float(os.getenv('DISTRICTPEOPLE_AMOUNT', '0.99')),
    'bgddesigns': float(os.getenv('BGDDESIGNS_AMOUNT', '1.99')),
    'saintvinson_givewp': float(os.getenv('SAINTVINSON_GIVEWP_AMOUNT', '0.25')),
    'staleks_florida': float(os.getenv('STALEKS_FLORIDA_AMOUNT', '5.99')),
    'ccfoundation': float(os.getenv('CCFOUNDATION_AMOUNT', '0.00')),  # Auth - CVV validation only
    
    # Stripe variants
    'madystripe': float(os.getenv('MADYSTRIPE_AMOUNT', '7.00')),
    'checkout': float(os.getenv('CHECKOUT_AMOUNT', '4.00')),
    'woostripe': float(os.getenv('WOOSTRIPE_AMOUNT', '10.00')),
    'woostripe_auth': float(os.getenv('WOOSTRIPE_AUTH_AMOUNT', '0.00')),  # Auth only - $0
    'woostripe_charge': float(os.getenv('WOOSTRIPE_CHARGE_AMOUNT', '18.00')),
    'stripe_auth': float(os.getenv('STRIPE_AUTH_AMOUNT', '0.00')),  # Auth only - $0
    'stripe_20': float(os.getenv('STRIPE_20_AMOUNT', '14.00')),
    'stripe_js': float(os.getenv('STRIPE_JS_AMOUNT', '25.00')),
    'stripe_payment_intent': float(os.getenv('STRIPE_PAYMENT_INTENT_AMOUNT', '8.00')),
    'stripe': float(os.getenv('STRIPE_AMOUNT', '8.00')),
}

def get_gateway_amount(gateway_name: str, default: float = 0.01) -> float:
    """Get the test amount for a specific gateway."""
    return GATEWAY_AMOUNTS.get(gateway_name, default)

# ============================================================================
# Phase 9: Merchant Gateway URLs (Merchant Integration)
# ============================================================================
BGDDESIGNS_URL = os.getenv('BGDDESIGNS_URL', 'https://bgddesigns.com')
STALEKS_FLORIDA_URL = os.getenv('STALEKS_FLORIDA_URL', 'https://www.staleks-florida.com')
CCFOUNDATION_URL = os.getenv('CCFOUNDATION_URL', 'https://ccfoundationorg.com')
SHOPIFY_STORES = os.getenv('SHOPIFY_STORES', 'https://shopzone.nz,https://balliante.com,https://epicalarc.com').split(',')
SHOPIFY_STORES = [store.strip() for store in SHOPIFY_STORES if store.strip()]

# ============================================================================
# Stripe Configuration (Phase 9: Live Keys)
# ============================================================================
STRIPE_SECRET_KEY = os.getenv('STRIPE_SECRET_KEY', '')
STRIPE_KEY_FILE = os.getenv('STRIPE_KEY_FILE', 'stripe_sk_live_keys.txt')
STRIPE_KEY_ATTEMPTS = int(os.getenv('STRIPE_KEY_ATTEMPTS', '3'))

# ============================================================================
# Shopify Configuration
# ============================================================================
SHOPIFY_KEY_FILE = os.getenv('SHOPIFY_KEY_FILE', 'shopify_stores.txt')

# ============================================================================
# PayPal Configuration
# ============================================================================
PAYPAL_USERNAME = os.getenv('PAYPAL_USERNAME', '')
PAYPAL_PASSWORD = os.getenv('PAYPAL_PASSWORD', '')

# ============================================================================
# Network Configuration
# ============================================================================
REQUEST_TIMEOUT = int(os.getenv('REQUEST_TIMEOUT', '15'))  # seconds
RETRY_ATTEMPTS = int(os.getenv('RETRY_ATTEMPTS', '3'))

# ============================================================================
# Gateway-Specific Timeout Configuration
# ============================================================================
# Per-gateway timeout overrides (in seconds)
GATEWAY_TIMEOUTS = {
    # Default timeout for all gateways not specified below
    'default': int(os.getenv('GATEWAY_TIMEOUT_DEFAULT', '22')),
    
    # Stripe variants (typically need more time)
    'stripe': int(os.getenv('GATEWAY_TIMEOUT_STRIPE', '25')),
    'stripe_auth': int(os.getenv('GATEWAY_TIMEOUT_STRIPE_AUTH', '25')),
    'stripe_20': int(os.getenv('GATEWAY_TIMEOUT_STRIPE_20', '25')),
    'stripe_js': int(os.getenv('GATEWAY_TIMEOUT_STRIPE_JS', '25')),
    'stripe_payment_intent': int(os.getenv('GATEWAY_TIMEOUT_STRIPE_PAYMENT_INTENT', '25')),
    
    # PayPal variants (GraphQL can be slow)
    'paypal': int(os.getenv('GATEWAY_TIMEOUT_PAYPAL', '30')),
    'paypal_charge': int(os.getenv('GATEWAY_TIMEOUT_PAYPAL_CHARGE', '30')),
    'check_card': int(os.getenv('GATEWAY_TIMEOUT_CHECK_CARD', '30')),
    
    # Shopify (checkout process can take time)
    'shopify': int(os.getenv('GATEWAY_TIMEOUT_SHOPIFY', '20')),
    'shopify_nano': int(os.getenv('GATEWAY_TIMEOUT_SHOPIFY_NANO', '20')),
    
    # Braintree
    'braintree': int(os.getenv('GATEWAY_TIMEOUT_BRAINTREE', '20')),
    
    # WooCommerce variants
    'woocommerce': int(os.getenv('GATEWAY_TIMEOUT_WOOCOMMERCE', '25')),
    'woostripe': int(os.getenv('GATEWAY_TIMEOUT_WOOSTRIPE', '25')),
    'woostripe_auth': int(os.getenv('GATEWAY_TIMEOUT_WOOSTRIPE_AUTH', '25')),
    'woostripe_charge': int(os.getenv('GATEWAY_TIMEOUT_WOOSTRIPE_CHARGE', '25')),
    
    # Other gateways
    'madystripe': int(os.getenv('GATEWAY_TIMEOUT_MADYSTRIPE', '25')),
    'checkout': int(os.getenv('GATEWAY_TIMEOUT_CHECKOUT', '20')),
    'ccfoundation': int(os.getenv('GATEWAY_TIMEOUT_CCFOUNDATION', '20')),
    'blemart': int(os.getenv('GATEWAY_TIMEOUT_BLEMART', '15')),
    'districtpeople': int(os.getenv('GATEWAY_TIMEOUT_DISTRICTPEOPLE', '15')),
    'bgddesigns': int(os.getenv('GATEWAY_TIMEOUT_BGDDESIGNS', '20')),
    'saintvinson_givewp': int(os.getenv('GATEWAY_TIMEOUT_SAINTVINSON_GIVEWP', '15')),
    'staleks_florida': int(os.getenv('GATEWAY_TIMEOUT_STALEKS_FLORIDA', '20')),
}

def get_gateway_timeout(gateway_name: str) -> int:
    """
    Get the timeout (in seconds) for a specific gateway.
    
    Args:
        gateway_name: Name of the gateway (e.g., 'stripe', 'paypal', 'shopify')
    
    Returns:
        Timeout in seconds, or default timeout if gateway not configured
    """
    return GATEWAY_TIMEOUTS.get(gateway_name.lower(), GATEWAY_TIMEOUTS['default'])

# ============================================================================
# Database Configuration
# ============================================================================
DATABASE_URL = os.getenv('DATABASE_URL', '')
PGHOST = os.getenv('PGHOST', '')
PGPORT = os.getenv('PGPORT', '5432')
PGUSER = os.getenv('PGUSER', '')
PGPASSWORD = os.getenv('PGPASSWORD', '')
PGDATABASE = os.getenv('PGDATABASE', '')

# ============================================================================
# Logging Configuration
# ============================================================================
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
LOG_FILE = os.getenv('LOG_FILE', 'logs/bot.log')
METRICS_FILE = os.getenv('METRICS_FILE', 'logs/metrics.json')

# Create logs directory if it doesn't exist
os.makedirs(os.path.dirname(LOG_FILE) if LOG_FILE else 'logs', exist_ok=True)

# ============================================================================
# Feature Flags
# ============================================================================
ENABLE_PROXY = os.getenv('ENABLE_PROXY', 'true').lower() == 'true'
ENABLE_MASS_CHECK = os.getenv('ENABLE_MASS_CHECK', 'true').lower() == 'true'
ENABLE_SMOKE_TESTS = os.getenv('ENABLE_SMOKE_TESTS', 'true').lower() == 'true'

# ============================================================================
# Console Colors (for logging)
# ============================================================================
COLOR_RED = '\033[1;31m'
COLOR_GREEN = '\033[2;32m'
COLOR_GRAY = '\033[1;30m'
COLOR_ORANGE = '\033[38;5;208m'
COLOR_RESET = '\033[0m'

def validate_config():
    """Validate critical configuration settings."""
    errors = []
    
    if not BOT_TOKEN:
        errors.append("BOT_TOKEN is not set")
    if not PROXY_HTTP or not PROXY_HTTPS:
        errors.append("Proxy configuration is incomplete")
    
    if errors:
        print(f"{COLOR_RED}[ERROR] Configuration validation failed:{COLOR_RESET}")
        for error in errors:
            print(f"  - {error}")
        return False
    
    print(f"{COLOR_GREEN}[✓] Configuration validated successfully{COLOR_RESET}")
    return True

# ============================================================================
# Export all configuration as a dictionary
# ============================================================================
CONFIG = {
    'bot_token': BOT_TOKEN,
    'proxy': PROXY,
    'gateway_amounts': GATEWAY_AMOUNTS,
    'request_timeout': REQUEST_TIMEOUT,
    'retry_attempts': RETRY_ATTEMPTS,
    'log_level': LOG_LEVEL,
    'log_file': LOG_FILE,
    'metrics_file': METRICS_FILE,
    'enable_proxy': ENABLE_PROXY,
    'enable_mass_check': ENABLE_MASS_CHECK,
    'enable_smoke_tests': ENABLE_SMOKE_TESTS,
    'bgddesigns_url': BGDDESIGNS_URL,
    'staleks_florida_url': STALEKS_FLORIDA_URL,
    'ccfoundation_url': CCFOUNDATION_URL,
    'shopify_stores': SHOPIFY_STORES,
    'stripe_key_file': STRIPE_KEY_FILE,
    'stripe_key_attempts': STRIPE_KEY_ATTEMPTS,
    'database_url': DATABASE_URL,
}

if __name__ == '__main__':
    # Print configuration summary when run directly
    print("Phase 6 Bot Configuration")
    print("=" * 50)
    print(f"Bot Token: {'***' + BOT_TOKEN[-10:] if BOT_TOKEN else 'NOT SET'}")
    print(f"Proxy: {PROXY['http'][:30]}..." if PROXY['http'] else 'NOT SET')
    print(f"Request Timeout: {REQUEST_TIMEOUT}s")
    print(f"Retry Attempts: {RETRY_ATTEMPTS}")
    print(f"Log Level: {LOG_LEVEL}")
    print(f"Gateway Amounts: {GATEWAY_AMOUNTS}")
    print("=" * 50)
    validate_config()
