"""
Fake Identity Generator - Generate fake user data by country
Uses randomuser.me API
"""

import requests
import random

COUNTRY_CODES = {
    'us': 'United States',
    'gb': 'United Kingdom',
    'ca': 'Canada',
    'au': 'Australia',
    'fr': 'France',
    'de': 'Germany',
    'es': 'Spain',
    'br': 'Brazil',
    'nl': 'Netherlands',
    'nz': 'New Zealand',
    'dk': 'Denmark',
    'fi': 'Finland',
    'ie': 'Ireland',
    'no': 'Norway',
    'ch': 'Switzerland',
}

def generate_fake_identity(country_code="us"):
    """
    Generate a fake identity using randomuser.me API
    
    Args:
        country_code: Two-letter country code (us, gb, ca, etc.)
    
    Returns:
        dict with identity info or None on error
    """
    country_code = country_code.lower()
    if country_code not in COUNTRY_CODES:
        country_code = "us"
    
    try:
        response = requests.get(
            f"https://randomuser.me/api/?nat={country_code}",
            timeout=10
        )
        
        if response.status_code != 200:
            return None
        
        data = response.json()["results"][0]
        
        return {
            'name': f"{data['name']['first']} {data['name']['last']}",
            'first_name': data['name']['first'],
            'last_name': data['name']['last'],
            'gender': data['gender'].capitalize(),
            'street': f"{data['location']['street']['number']} {data['location']['street']['name']}",
            'city': data['location']['city'],
            'state': data['location']['state'],
            'postcode': str(data['location']['postcode']),
            'country': data['location']['country'],
            'phone': data['phone'],
            'cell': data['cell'],
            'email': data['email'],
            'dob': data['dob']['date'][:10],
            'age': data['dob']['age'],
            'username': data['login']['username'],
        }
        
    except Exception as e:
        print(f"[fake_identity] API error: {e}")
        return None

def generate_us_address():
    """Generate a random US address without API"""
    streets = [
        "Main St", "Oak Ave", "Maple Dr", "Cedar Ln", "Pine Rd",
        "Elm St", "Park Ave", "Lake Dr", "Hill Rd", "River Ln"
    ]
    cities = [
        ("New York", "NY", "10001"),
        ("Los Angeles", "CA", "90001"),
        ("Chicago", "IL", "60601"),
        ("Houston", "TX", "77001"),
        ("Phoenix", "AZ", "85001"),
        ("Philadelphia", "PA", "19101"),
        ("San Antonio", "TX", "78201"),
        ("San Diego", "CA", "92101"),
        ("Dallas", "TX", "75201"),
        ("Miami", "FL", "33101"),
    ]
    
    first_names = ["James", "John", "Robert", "Michael", "William", "David", "Mary", "Patricia", "Jennifer", "Linda"]
    last_names = ["Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis", "Rodriguez", "Martinez"]
    
    city, state, zip_code = random.choice(cities)
    
    return {
        'name': f"{random.choice(first_names)} {random.choice(last_names)}",
        'first_name': random.choice(first_names),
        'last_name': random.choice(last_names),
        'street': f"{random.randint(100, 9999)} {random.choice(streets)}",
        'city': city,
        'state': state,
        'postcode': zip_code,
        'country': 'United States',
        'phone': f"({random.randint(200, 999)}) {random.randint(200, 999)}-{random.randint(1000, 9999)}",
    }

def format_fake_response(identity, country_code):
    """Format the fake identity response for Telegram"""
    if not identity:
        return "Failed to generate fake identity. Try again."
    
    return f"""<b>FAKE IDENTITY - {country_code.upper()}</b>

<b>Name:</b> <code>{identity['name']}</code>
<b>Gender:</b> <code>{identity.get('gender', 'N/A')}</code>
<b>Street:</b> <code>{identity['street']}</code>
<b>City:</b> <code>{identity['city']}</code>
<b>State:</b> <code>{identity.get('state', 'N/A')}</code>
<b>Postcode:</b> <code>{identity['postcode']}</code>
<b>Country:</b> <code>{identity['country']}</code>
<b>Phone:</b> <code>{identity['phone']}</code>
<b>Email:</b> <code>{identity.get('email', 'N/A')}</code>
<b>DOB:</b> <code>{identity.get('dob', 'N/A')}</code>"""
