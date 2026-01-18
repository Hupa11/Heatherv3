# Mady Bot (Codename: Heather) - Telegram Payment Gateway Bot

## Overview
Mady is a high-performance Telegram bot for card validation and payment gateway testing. Version 6.2.1. Built in Python, it supports multiple payment gateways including PayPal, Stripe, Braintree, Shopify, and more.

## Project Structure
```
/
├── transferto.py          # Main bot entry point
├── config.py              # Configuration loader (reads from environment)
├── response_formatter*.py # Response formatting utilities
├── metrics_collector.py   # Bot analytics and metrics
├── dashboard.py           # Analytics dashboard
├── gates/                 # Payment gateway modules
│   ├── stripe*.py        # Stripe gateway variants
│   ├── paypal*.py        # PayPal integration
│   ├── braintree*.py     # Braintree gateways
│   ├── shopify*.py       # Shopify checkout
│   └── ...               # Other gateways
├── tools/                 # Utility tools
│   ├── shopify_db.py     # Database management (PostgreSQL)
│   ├── card_generator.py # Card generation tools
│   └── ...               # Other utilities
└── logs/                  # Log files directory
```

## Required Secrets
- `BOT_TOKEN` - Telegram bot token from @BotFather (required)
- `PROXY_HTTP` - HTTP proxy URL (optional)
- `PROXY_HTTPS` - HTTPS proxy URL (optional)

## Database
Uses PostgreSQL database (automatically created via Replit). The DATABASE_URL environment variable is configured automatically.

## Running the Bot
The bot runs via the "Telegram Bot" workflow which executes:
```bash
python transferto.py
```

## Bot Commands
- `/check` - Check a card
- `/stats` - View usage statistics
- Various gateway-specific commands

## Recent Changes (January 2026)

### Code Cleanup
- Moved 7 unused gate files to `deprecated/gates/` (autostripe, braintree_direct, shopify_enhanced, shopify_full, stripe_ccn, stripe_enhanced, stripe_sk_charge)
- Moved 24 unused testing tools to `deprecated/tools/`
- Kept 52 active gates and 8 active tools

### Gateway Amount Alignment
- Updated `config.py` GATEWAY_AMOUNTS to reflect actual donation/charge amounts
- Fixed response messages to show accurate amounts:
  - Stripe donations: $1.00
  - PayPal: $5.00
  - Lions Club/Bell Alliance: $5.00
  - Braintree: $1.00
  - Auth gates: $0.00

### Infrastructure
- Migrated to Replit environment
- Configured PostgreSQL database
- Installed all Python dependencies
- Set up Telegram Bot workflow
