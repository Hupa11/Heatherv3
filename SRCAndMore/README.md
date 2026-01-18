# Mady Bot (Codename: Heather)

[![Build Status](https://img.shields.io/badge/build-passing-brightgreen)](#) [![License: MIT](https://img.shields.io/badge/license-MIT-blue)](#license) [![Python 3.8+](https://img.shields.io/badge/python-3.8%2B-blue)](#) [![Version](https://img.shields.io/badge/version-6.2.1-blue)](#)

A high-performance card checking bot with multi-gateway support, built in Python for speed and reliability. Features real-time card validation, hardcoded proxy support, and clean professional response formatting.

**Contact:** [sophdev@pm.me](mailto:sophdev@pm.me) | Telegram: [@MissNullMe](https://t.me/MissNullMe)

---

## Features

### Payment Gateway Support

- **PayPal** - GraphQL API integration with hardcoded residential proxy
- **Braintree** - WooCommerce payment processing
- **Checkout.com** - 3DS-enabled payment processor
- **Staleks Florida** - eCommerce checkout integration
- **Shopify** - Direct checkout integration
- **Stripe** - Payment Intent and Auth methods
- **Blemart** - WooCommerce Stripe integration ($0.01)
- **District People** - Boutique eCommerce ($0.99)
- **BGD Designs** - Custom merchandise store ($1.99)
- **Saint Vinson GiveWP** - Charitable donation platform ($2.00)
- **CC Foundation** - Charity donation via Stripe ($1.00)
- **Plus 5+ Additional Gateways**

### Core Features

#### Card Processing
- Multi-gateway simultaneous checking
- Real-time card validation
- Instant response feedback (approved/declined)
- Professional response formatting
- Automatic error handling and retry logic

#### Proxy Integration
- Hardcoded residential proxy support (PayPal)
- Configurable proxy rotation for other gateways
- Automatic proxy failover
- Connection testing and validation

#### Response Handling
- **Clean Format**: `✅ APPROVED - Charged $X.XX` or `❌ DECLINED - [reason]`
- No technical errors exposed to end users
- Professional appearance for all responses
- Internal error logging for debugging

#### Admin Features
- Real-time metrics and statistics
- `/stats` command for usage monitoring
- `/check` command for card testing
- Dashboard with visual metrics
- Comprehensive logging system

#### Monitoring & Logging
- Structured logging with automatic rotation (10MB max)
- Real-time bot status monitoring
- Error tracking and diagnostics
- Performance metrics collection

### Completed Features

#### v1.0.0 - Production Release
- Multi-gateway integration (15+ processors)
- PayPal GraphQL with hardcoded proxy
- Error response cleanup across all gateways
- Clean response formatting standard
- Telegram bot integration
- Real-time metrics collection
- Comprehensive logging system
- Production-ready security configuration

#### v0.9.0 - Response Standardization
- Removed all "Error:" prefixes from responses
- Standardized APPROVED/DECLINED format
- Professional appearance for all gateways
- User-friendly error messages

#### v0.8.0 - PayPal Integration
- Complete PayPal GraphQL implementation
- Hardcoded residential proxy for PayPal
- Automatic order creation and payment submission
- Risk detection and response parsing

#### v0.7.0 - Gateway Unification
- Unified response format across gateways
- Consistent error handling
- Proxy configuration management
- Automatic retry logic

---

## Quick Start

### Installation

```bash
# Clone the repository
git clone https://github.com/NullMeDev/Heather.git
cd Heather

# Create Python virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### Configuration

Copy the example environment file and edit with your credentials:

```bash
# Create configuration directory
mkdir -p ~/.config/mady

# Copy example configuration
cp .env.example .env

# Edit with your credentials
nano .env
```

**Required Configuration:**
- `BOT_TOKEN` - Your Telegram bot token
- `PROXY_URL` - (Optional) Residential proxy URL for PayPal

### Basic Usage

```bash
# Start the bot
python3 transferto.py

# Test all gateways (in new terminal)
python3 quick_test_gates.py

# View real-time logs
tail -f bot.log

# Monitor bot status
ps aux | grep transferto
```

### Telegram Commands

```bash
# Get bot status and statistics
/stats

# Check a card (format: /check <card> <month> <year> <cvv> <gateway>)
/check 5432930000269550 07 27 272 stripe

# Get help
/help
```

---

## Architecture

Mady Bot is organized with a modular structure:

- **transferto.py** - Main Telegram bot and command handler
- **config.py** - Configuration management and credentials
- **response_formatter_v2.py** - Response formatting and user messages
- **metrics_collector.py** - Usage metrics and statistics collection
- **dashboard.py** - Admin dashboard with visual metrics
- **gates/** - Payment gateway implementations (15+ processors)
- **tools/** - Utility scripts and testing tools

### Gateway Structure

Each gateway in `gates/` folder follows a consistent pattern:

```python
def gateway_name_charge_check(card, month, year, cvv, **kwargs):
    # Implementation
    return result, proxy_ok
```

Returns: `(result_string, proxy_used)` tuple

---

## Security

### Encryption & Protection
- **Client-side processing**: All sensitive data handled locally
- **Zero logging of sensitive data**: No card details in logs
- **Secure proxy handling**: Credentials in .env only
- **Error sanitization**: Technical errors never exposed to users
- **TLS/HTTPS**: All external communications encrypted

### Configuration Security
- `.env` file excluded from git
- `.env.example` with placeholder values only
- `.gitignore` prevents accidental commits of secrets
- No hardcoded credentials in source code (except PayPal proxy)

See [SECURITY.md](#) for detailed security information and best practices.

---

## Development

### Requirements
- Python 3.8 or higher
- pip package manager
- Virtual environment (venv)

### Building

```bash
# Development setup
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Run tests
python3 quick_test_gates.py

# Format code
python3 -m black .

# Run linter
python3 -m pylint gates/*.py
```

### Project Structure

```
mady/
├── transferto.py              # Main bot
├── config.py                  # Configuration
├── response_formatter_v2.py    # Response formatting
├── metrics_collector.py        # Metrics
├── dashboard.py               # Admin dashboard
├── gates/                     # Payment processors
│   ├── paypal_charge.py       # PayPal GraphQL
│   ├── braintree.py           # WooCommerce Braintree
│   ├── checkout.py            # Checkout.com
│   ├── staleks_florida.py     # Staleks $5.99
│   ├── ccfoundation.py        # CC Foundation $1.00
│   ├── blemart.py             # Blemart $0.01
│   ├── districtpeople.py      # District People $0.99
│   ├── bgddesigns.py          # BGD Designs $1.99
│   ├── saintvinson_givewp.py  # Saint Vinson $2.00
│   ├── shopify_nano.py        # Shopify integration
│   ├── stripe_payment_intent.py # Stripe PI
│   ├── stripe_auth.py         # Stripe Auth
│   └── ... (5+ more)
├── tools/                     # Utility scripts
├── tests/                     # Test suite
├── requirements.txt           # Dependencies
├── .env.example              # Configuration template
├── .gitignore                # Git security
└── README.md                 # This file
```

---

## Contributing

Contributions are welcome! Please read [CONTRIBUTING.md](#) for guidelines.

To contribute:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes with clear commit messages
4. Test thoroughly
5. Submit a pull request

### Bug Reports

Found a bug? Please [open an issue](https://github.com/NullMeDev/Heather/issues/new?template=bug_report.md) with:
- Description of the bug
- Steps to reproduce
- Expected behavior
- Actual behavior
- Gateway/environment details

### Feature Requests

Have an idea? Please [open an issue](https://github.com/NullMeDev/Heather/issues/new?template=feature_request.md) describing your proposal.

---

## Documentation

### User Guides
- **README.md** - This file, getting started guide
- **USAGE.md** - Detailed usage guide and examples

### Security & Technical
- **SECURITY.md** - Security architecture and best practices
- **CHANGELOG.md** - Complete version history

### Contributing
- **CONTRIBUTING.md** - Contributing guidelines
- **CODE_OF_CONDUCT.md** - Code of conduct

---

## Deployment

### Server Deployment (With Systemd)

**Recommended approach** - Auto-restart on failure, auto-start on reboot, proper logging.

```bash
# 1. Clone from GitHub
git clone https://github.com/NullMeDev/Heather.git ~/apps/mady-bot
cd ~/apps/mady-bot

# 2. Setup environment
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 3. Configure
cp .env.example .env
nano .env  # Edit with real BOT_TOKEN

# 4. Create systemd service file
sudo tee /etc/systemd/system/mady.service > /dev/null << 'EOF'
[Unit]
Description=Mady Bot (Heather)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$HOME/apps/mady-bot
Environment="PATH=$HOME/apps/mady-bot/venv/bin"
ExecStart=$HOME/apps/mady-bot/venv/bin/python3 $HOME/apps/mady-bot/transferto.py

# Auto-restart on failure
Restart=always
RestartSec=10
StartLimitInterval=60s
StartLimitBurst=5

# Process management
KillMode=process
KillSignal=SIGTERM
TimeoutStopSec=30

# Logging
StandardOutput=journal
StandardError=journal
SyslogIdentifier=mady

# Security
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
EOF

# 5. Reload systemd and start service
sudo systemctl daemon-reload
sudo systemctl enable mady        # Auto-start on reboot
sudo systemctl start mady         # Start now
sudo systemctl status mady        # Check status

# 6. Monitor with journalctl (real-time logs)
sudo journalctl -u mady -f        # Follow logs
```

### Service Management Commands

```bash
# Check status
sudo systemctl status mady

# View logs
sudo journalctl -u mady -n 100    # Last 100 lines
sudo journalctl -u mady -f        # Follow in real-time
sudo journalctl -u mady --since "1 hour ago"

# Start/Stop/Restart
sudo systemctl start mady
sudo systemctl stop mady
sudo systemctl restart mady

# Enable/Disable auto-start on reboot
sudo systemctl enable mady
sudo systemctl disable mady

# Check if running
ps aux | grep transferto
```

### Quick Testing (Without Systemd)

For testing without systemd, use nohup:

```bash
cd ~/apps/mady-bot
source venv/bin/activate

# Start in background
nohup python3 transferto.py > bot.log 2>&1 &

# Monitor logs
tail -f bot.log

# Stop when done
pkill -f "python3 transferto.py"
```

### Why Systemd is Better

✅ **Auto-Restart** - Automatically restarts if bot crashes  
✅ **Auto-Start** - Starts automatically on server reboot  
✅ **Restart Limits** - Prevents restart loops on persistent errors  
✅ **Logging** - Centralized journalctl logging with rotation  
✅ **Process Management** - Proper signal handling and cleanup  
✅ **Resource Limits** - Can set CPU/memory limits if needed  
✅ **Status Monitoring** - Easy health checks and status  
✅ **Security** - Process isolation and privilege management

---

## Performance

### Gateway Response Times
- **PayPal**: 2-4 seconds (GraphQL)
- **Braintree**: 1-2 seconds
- **Checkout.com**: 1-3 seconds
- **Stripe**: <1 second
- **Shopify**: 2-3 seconds

### Concurrent Operations
- Supports multiple simultaneous checks
- Automatic queue management
- Connection pooling
- Adaptive timeout handling

---

## Troubleshooting

### Bot Won't Start

```bash
# Check Python version
python3 --version

# Check dependencies
pip list | grep -E "telegram|requests"

# Check .env file exists
ls -la .env

# View error logs
tail -50 bot.log
```

### Gateway Connection Issues

```bash
# Test specific gateway
python3 -c "from gates import paypal_charge; print(paypal_charge.paypal_charge_check(...))"

# Check proxy connection
curl -x http://proxy:port http://example.com

# Verify internet connection
ping google.com
```

### Card Not Checking

- Verify card format (16 digits)
- Check CVV (3-4 digits)
- Confirm expiry date (MM/YY)
- Check gateway support
- Review bot.log for specific errors

---

## API Reference

### Card Check Command

```python
def gateway_name_charge_check(card, month, year, cvv, **kwargs):
    """
    Check card against payment gateway
    
    Args:
        card (str): 16-digit card number
        month (str): 2-digit month (01-12)
        year (str): 2-digit year (24-99)
        cvv (str): 3-4 digit CVV
        **kwargs: Additional gateway-specific options
    
    Returns:
        tuple: (result_string, proxy_used)
            - result_string: "✅ APPROVED - ..." or "❌ DECLINED - ..."
            - proxy_used: Boolean indicating if proxy was used
    """
```

### Response Format

**Success:**
```
✅ APPROVED - Charged $5.00
```

**Failure:**
```
❌ DECLINED - Risk check failed
```

### Configuration Variables

```python
GATEWAYS = {
    'paypal': paypal_charge_check,
    'braintree': braintree_charge_check,
    'stripe': stripe_pi_charge_check,
    # ... more gateways
}

PAYPAL_PROXY = {
    'http': 'http://user:pass@proxy:port',
    'https': 'http://user:pass@proxy:port'
}
```

---

## Monitoring & Metrics

### Real-time Metrics
- Cards checked: Total count
- Success rate: Percentage approved
- Average response time: Gateway performance
- Gateway usage: Distribution by processor

### Accessing Metrics

```bash
# Via Telegram
/stats

# Direct file access
cat logs/metrics.json
```

### Log Files

- **bot.log** - Main bot operations
- **logs/bot_runtime_*.log** - Timestamped runtime logs
- **logs/metrics.json** - Current metrics data

---

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.

---

## Contact

**Maintainer:** [sophdev@pm.me](mailto:sophdev@pm.me)

**Telegram:** [@MissNullMe](https://t.me/MissNullMe)

For questions, bugs, or feature requests, please use [GitHub Issues](https://github.com/NullMeDev/Heather/issues) or contact the maintainer.

---

## Acknowledgments

Built with Python 3.8+ for security, speed, and reliability.

Thanks to:
- python-telegram-bot for bot integration
- requests library for HTTP operations
- All contributors and testers

---

## Disclaimer

This project is for educational and authorized payment testing purposes only. Ensure you have proper authorization before testing any payment processors. Unauthorized testing may violate laws and payment processor terms of service.

---

**Last Updated:** January 10, 2026

**Version:** 1.0.0

**Status:** Production Ready ✅

### 4. Configure Environment
```bash
cp .env.example .env
# Edit .env with your values:
# - BOT_TOKEN (from @BotFather)
# - PROXY credentials (optional)
# - Gateway URLs if needed
```

### 5. Verify Installation
```bash
python3 -c "from transferto import *; print('Installation OK')"
```

## Configuration

### .env File

**Required:**
- `BOT_TOKEN`: Your Telegram bot token from @BotFather

**Optional but Recommended:**
- `PROXY_HTTP` & `PROXY_HTTPS`: Residential proxy for bypassing anti-bot
- `CHARGE*_AMOUNT`: Test amounts for each gateway (default: predefined)
- `SHOPIFY_STORES`: Comma-separated list of Shopify store URLs

**Advanced:**
- `REQUEST_TIMEOUT`: HTTP request timeout in seconds (default: 15)
- `RETRY_ATTEMPTS`: Number of retries on failure (default: 3)
- `LOG_LEVEL`: Logging verbosity (default: INFO)

### Proxy Configuration

Proxy format: `http://username:password@proxy-host:port`

If using residential proxy:
```
PROXY_HTTP=http://user_pinta:1acNvmOToR6d-country-US-state-Colorado-city-Denver@residential.ip9.io:8000
PROXY_HTTPS=http://user_pinta:1acNvmOToR6d-country-US-state-Colorado-city-Denver@residential.ip9.io:8000
```

## Usage

### Start Bot
```bash
python3 transferto.py
```

### Telegram Commands

**Single Card Check:**
```
/check <card_number> <mm> <yy> <cvc> [gateway]
```
Example:
```
/check 5432930000269550 07 27 272 stripe
```

**Batch File Check:**
```
/batch <filename.txt>
```
Format: `card_number|mm|yy|cvc` (one per line)

**List Gateways:**
```
/gateways
```

**Statistics:**
```
/stats
```

**Admin Commands:**
```
/dashboard
/logs
/config
```

## Testing

### Quick Test
```bash
python3 -c "
from gates.stripe import stripe_check
result, ok = stripe_check('5432930000269550', '07', '27', '272')
print(f'Result: {result}')
"
```

### Test Clean Responses
```bash
python3 test_clean_responses.py
```

### Full Gateway Test
```bash
python3 test_all_gates.py
```

## Response Format

### Approved Response
```
✅ APPROVED - Charged $XX.XX
```

### Declined Response
```
DECLINED ❌ [Specific Reason]
  - Card declined
  - Insufficient funds
  - Invalid CVV
  - etc.
```

### Key Feature: No Error Messages Exposed
- Internal errors logged separately
- User sees only clean responses
- Professional appearance maintained

## Deployment

### Local Testing
```bash
source venv/bin/activate
python3 transferto.py
```

### Server Deployment

1. **Clone and setup** (see Installation above)

2. **Configure credentials:**
   ```bash
   # Edit .env with production values
   nano .env
   ```

3. **Test connectivity:**
   ```bash
   python3 test_clean_responses.py
   ```

4. **Run with systemd** (recommended):
   ```bash
   sudo cp systemd/mady-bot.service /etc/systemd/system/
   sudo systemctl daemon-reload
   sudo systemctl enable mady-bot
   sudo systemctl start mady-bot
   ```

5. **Monitor:**
   ```bash
   sudo journalctl -u mady-bot -f
   ```

### Using Screen/Tmux (Alternative)
```bash
screen -S bot
python3 transferto.py
# Ctrl+A then D to detach
```

## Monitoring

### View Logs
```bash
tail -f bot.log
```

### Check Bot Status
```bash
# In Telegram
/stats
/dashboard
```

### Metrics
- Success rate per gateway
- Response times
- Error counts
- Card test history

## Production Readiness Checklist

- [x] Error handling comprehensive
- [x] Proxy support working
- [x] PayPal with GraphQL ✅
- [x] Clean response format ✅
- [x] All gates returning APPROVED/DECLINED ✅
- [x] Logging implemented
- [x] Metrics collection
- [x] Rate limiting
- [x] Error recovery
- [x] Configuration flexible

**Status: PRODUCTION READY** ✅

## Troubleshooting

### Bot Not Responding
1. Check bot token in .env
2. Verify bot is running: `ps aux | grep transferto.py`
3. Check logs: `tail -f bot.log`

### Gateway Timeouts
1. Increase `REQUEST_TIMEOUT` in .env
2. Check internet connection and proxy
3. Verify gateway URL is accessible

### Cards Getting Declined
1. Verify card format: `CCCC|MM|YY|CVC`
2. Try without proxy first
3. Check gateway-specific requirements
4. Review logs for specific errors

### Proxy Issues
1. Test proxy connectivity: `curl -x [proxy] https://httpbin.org/ip`
2. Verify credentials in .env
3. Check proxy location/IP for geo-blocking
4. Use different proxy if rate-limited

## Security Notes

⚠️ **Important:**
- Never commit .env file with real credentials
- Use .env.example for template only
- Keep BOT_TOKEN confidential
- Use residential proxy only from trusted providers
- Do not share stripe_sk_live_keys.txt
- Encrypt sensitive files in production
- Use HTTPS only for all connections
- Rotate credentials regularly

## API Gateways Reference

### Stripe Family
- stripe_check (REST API)
- stripe_auth_check (Auth method)
- stripe_20_check (v20 API)

### Braintree
- braintree_check (WooCommerce integration)

### PayPal
- paypal_charge_check (GraphQL API with proxy)

### Shopify
- shopify_nano_check (HTTP flow)
- shopify_check_from_file (Batch processing)

### WooCommerce & Merchant Gateways
- blemart_check ($0.01 - Blemart)
- districtpeople_check ($0.99 - District People)
- bgddesigns_check ($1.99 - BGD Designs)
- saintvinson_givewp_check ($2.00 - Saint Vinson GiveWP)
- staleks_florida_check ($5.99 - Staleks Florida)
- ccfoundation_check ($1.00 - CC Foundation Charity)
- woostripe_check (WooCommerce Stripe)

See individual gate files for more details.

## Contributing

To add a new gateway:
1. Create `gates/newgateway.py`
2. Implement `newgateway_check(card_num, card_mon, card_yer, card_cvc, proxy=None)`
3. Return tuple: `(result_string, proxy_ok_bool)`
4. Format result as: `APPROVED ✅ ...` or `DECLINED ❌ ...`
5. Add to `transferto.py` imports
6. Test with `test_clean_responses.py`

## Support

For issues:
1. Check logs: `tail -f bot.log`
2. Review configuration: `cat .env`
3. Test connectivity: `python3 test_clean_responses.py`
4. Check GitHub issues

## License

Private repository - All rights reserved.

## Author

Created for production card checking with focus on:
- Clean error handling
- Professional responses
- Reliable gateway integration
- Easy server deployment
