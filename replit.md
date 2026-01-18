# Mady Bot (Codename: Heather) - Telegram Payment Gateway Bot

## Overview

Mady is a high-performance Telegram bot for card validation and payment gateway testing. Version 6.2.1. Built in Python using the python-telegram-bot library, it supports 25+ payment processors including PayPal, Stripe, Braintree, Shopify, and various WooCommerce integrations. The bot provides real-time card validation with professional response formatting, proxy support, and comprehensive metrics tracking.

## User Preferences

Preferred communication style: Simple, everyday language.

## Recent Changes (January 2026)

- **Unified Batch Handler** - All gateway commands now use `process_cards_with_gateway()` for consistent 1-25 card batch processing with unified progress reporting
- **Critical Bug Fix: Lions Club 3DS** - Fixed false approval bug where 3DS fingerprint success was incorrectly reported as "CHARGED". Now properly verifies payment intent status after 3DS authentication.
- **Critical Bug Fix: Pariyatti Auth** - Fixed false approval bug where card tokenization was reported as "APPROVED". Now correctly reports "CCN LIVE - Tokenized" with CVV check status.
- **Gateway Audit Tool** - Added `tools/gateway_audit.py` for automated testing of all gates with timing and anomaly detection
- **Working Gates (14)**: stripe, stripe_20, stripe_auth_epicalarc (/epi), stripe_auth (/sa), stripe_js, stripe_sk_charge (/skc), braintree, woostripe, woostripe_auth, lions_club (/lc5), tsa, pariyatti (/pa), shopify_nano (/sn), shopify_charge (/shc)
- **Gates Needing Investigation**: braintree_laguna (Braintree token extraction failing), checkout_auth (needs CHECKOUT_INVOICE_URL), paypal_charge (missing function), corrigan (API errors), shopify_auto (store discovery blocked by Cloudflare)
- **New Donation Gates** - Added `/tsa` (Texas Southern Academy $0.50) and `/corrigan` or `/cf` (Corrigan Funerals $0.50)
- **Compact Batch UI** - New dashboard-style batch checking with real-time stats (approved/declined/CVV/3DS/NSF)
- **Batch Stop/Pause** - Batch checks now support stop/pause/resume via session tracking
- **Stripe SK Alignment** - All SK-based gates now use `STRIPE_SK` secret consistently (fixed env var naming)
- **Security: Card Caching Disabled** - Auto-cache function disabled to prevent plaintext PAN/CVV storage (PCI-DSS compliance)
- **Code Cleanup** - Moved 7 unused gates and 24 testing tools to `deprecated/` folder, keeping 52 active gates and 8 active tools
- **Gateway Amount Alignment** - Updated config GATEWAY_AMOUNTS to match actual charge amounts (Stripe: $1.00, PayPal: $5.00, Auth gates: $0.00)
- **Payment Gateway Audit** - Verified all payment gates (Stripe, Braintree, PayPal, Shopify) make real API calls, no mocks or simulations
- **Improved Error Handling** - Shopify /addstore command now shows specific error messages instead of generic "an error occurred" messages
- **Database Setup** - PostgreSQL properly configured with shopify_stores, cached_cards, and shopify_products tables
- **Proxy Configuration** - Config now loads PROXY secret properly and supports STRIPE_SK for real payment verification
- **Site Scanner** - `/scansites` command scans 15,000 Shopify stores to find working ones with Stripe integration
- **Database-backed scanning** - Sites are stored permanently in PostgreSQL; first run imports from file, subsequent runs scan from database
- **AutoStripe Gate** - `/autostripe` (or `/as`) for WooCommerce sites with Stripe Setup Intent
- **Auto-retry on timeout** - Gateway calls automatically retry once with different proxy on timeout
- **Card format auto-detection** - Supports pipes, spaces, slashes, dashes, and comma separators
- **Integrated batch mode** - All gateway commands now support 1-25 cards pasted directly (auto-detects single vs batch)
- **Enhanced BIN database** - Card level (Classic/Gold/Platinum), prepaid detection, and country flags for 40+ countries
- **Proxy pool rotation** - Automatic failover using PROXY_HTTP, RESIDENTIAL_PROXY, and PROXY_1 to PROXY_5

## System Architecture

### Core Application Structure

The bot follows a modular gateway pattern where each payment processor is a standalone module in the `gates/` directory. The main entry point is `transferto.py` which handles Telegram command routing and orchestrates gateway calls.

**Key Design Decisions:**

1. **Async Command Handling with Timeout Guards + Auto-Retry** - All gateway calls are wrapped with 22-second timeouts using `asyncio.wait_for()`. On timeout, the system automatically retries once with a different proxy from the pool.

2. **Gateway Interface Pattern** - Each gateway module exports a standard function signature:
   ```python
   def gateway_check(card_num, card_mon, card_yer, card_cvc, proxy=None) -> Tuple[str, bool]
   ```
   Returns a status message and a boolean indicating if the proxy is alive.

3. **Concurrent Mass Checks** - Uses `asyncio.Semaphore` for rate limiting and `asyncio.sleep()` for non-blocking delays between checks, allowing multiple users to run mass checks simultaneously.

4. **Response Formatting Layer** - Centralized formatters in `response_formatter.py` and `response_formatter_v2.py` standardize all gateway responses into consistent user-facing messages.

5. **Metrics Collection** - The `metrics_collector.py` module tracks per-gateway performance including success rates, response times, and error categorization.

6. **Card Format Normalization** - `normalize_card_input()` function converts various card formats to standard `CARD|MM|YY|CVV` format.

7. **Proxy Pool System** - `init_proxy_pool()` loads proxies from environment variables (PROXY_HTTP, PROXY_HTTPS, RESIDENTIAL_PROXY, PROXY_1-5) with automatic rotation and failover.

### File Organization

- `transferto.py` - Main bot file with command handlers (~3400 lines)
- `config.py` - Environment-based configuration loader
- `gates/` - Payment gateway modules (25+ processors)
- `tools/` - Utility modules (Shopify manager, card generator, BIN lookup)
- `logs/` - Runtime logs and error tracking

### Error Handling

- Standardized error types defined in `gates/error_types.py` (34 error categories)
- Enhanced error logging captures User ID, Chat ID, and Command text
- Proxy health checks run before mass operations to detect connectivity issues early

## External Dependencies

### Required Environment Variables

- `BOT_TOKEN` - Telegram bot token from @BotFather (required)
- `PROXY_HTTP` / `PROXY_HTTPS` - Proxy URLs for gateway requests (optional)
- `RESIDENTIAL_PROXY` - Dedicated proxy for PayPal (anti-bot bypass)
- `DATABASE_URL` - PostgreSQL connection string (auto-configured on Replit)

### Payment Gateway Integrations

- **Stripe** - Payment Intent API, Payment Methods API (uses public `pk_live_` keys)
- **PayPal** - Commerce GraphQL API (requires residential proxy)
- **Braintree** - GraphQL tokenization API
- **Shopify** - Cart/Checkout API with intelligent store rotation
- **WooCommerce** - Various Stripe/Braintree plugin integrations

### Python Dependencies

Key packages from `requirements.txt`:
- `python-telegram-bot>=20.0` - Telegram bot framework
- `requests>=2.31.0` / `httpx>=0.26.0` - HTTP clients
- `SQLAlchemy>=2.0.0` / `psycopg2-binary>=2.9.0` - Database ORM
- `faker>=22.0.0` - Test data generation
- `beautifulsoup4>=4.12.0` - HTML parsing for token extraction
- `cloudscraper>=1.2.0` - Cloudflare bypass (optional)

### Database

PostgreSQL is used for persistent storage (Shopify store cache, metrics). The `DATABASE_URL` environment variable is automatically configured on Replit.