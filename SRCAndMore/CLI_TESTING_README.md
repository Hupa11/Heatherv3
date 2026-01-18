# CLI Testing Tool for RainbowPonk Gates

## Quick Start

Test any RainbowPonk gate directly without the Telegram bot:

```bash
cd ~/heather/SRCAndMore
python3 test_rainbowponk.py <gate> "CARD|MM|YY|CVV"
```

## Available Gates

### Stripe (v1-v5)
```bash
python3 test_rainbowponk.py v1 "4388576200115627|05|30|636"
python3 test_rainbowponk.py v2 "4388576200115627|05|30|636"
python3 test_rainbowponk.py v3 "4388576200115627|05|30|636"
python3 test_rainbowponk.py v4 "4388576200115627|05|30|636"
python3 test_rainbowponk.py v5 "4388576200115627|05|30|636"
```

### PayPal
```bash
python3 test_rainbowponk.py pp5 "4388576200115627|05|30|636"   # $5
python3 test_rainbowponk.py pp10 "4388576200115627|05|30|636"  # $10
```

### Braintree
```bash
python3 test_rainbowponk.py bt1 "4388576200115627|05|30|636"   # $1
```

### Adyen
```bash
python3 test_rainbowponk.py adyen01 "4388576200115627|05|30|636"  # $0.10
python3 test_rainbowponk.py adyen1 "4388576200115627|05|30|636"   # $1
python3 test_rainbowponk.py adyen2 "4388576200115627|05|30|636"   # $2
python3 test_rainbowponk.py adyen5 "4388576200115627|05|30|636"   # $5
```

### Amazon
```bash
python3 test_rainbowponk.py amzau "4388576200115627|05|30|636"  # Australia
python3 test_rainbowponk.py amzca "4388576200115627|05|30|636"  # Canada
python3 test_rainbowponk.py amzmx "4388576200115627|05|30|636"  # Mexico
python3 test_rainbowponk.py amzjp "4388576200115627|05|30|636"  # Japan
python3 test_rainbowponk.py amzit "4388576200115627|05|30|636"  # Italy
```

## Configuration Verification

The script automatically loads and displays:
- Proxy configuration
- Stripe SK key status

## Troubleshooting

### Issue: Gates saying SK key not configured

**Problem**: The Telegram bot was passing proxy as a dict `{'http': '...', 'https': '...'}` but RainbowPonk gates expect a string URL.

**Solution**: This CLI tool correctly passes `config.PROXY_HTTP` as a string.

### Issue: httpx proxy parameter error

**Fixed**: Changed `proxies=proxy` to `proxy=proxy` in all gate files.

## Next Steps

1. Test all gates with this CLI tool
2. Once working, fix the Telegram bot to pass proxy correctly
3. Update bot token in `.env` and restart bot

## Files

- `test_rainbowponk.py` - CLI testing tool
- `cli_checker.py` - General CLI tool (work in progress)
- `.env` - Configuration (proxy, bot token, SK keys)
