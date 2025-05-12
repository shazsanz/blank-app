import datetime
import re
import time
import zipfile
import pandas as pd
import requests
import io


def perform_operations(response):
    # Extract user token or other info from the response if needed
    user_token = response.get('susertoken')

    # Example operation: Fetch market data, place orders, etc.
    print(f"Performing operations with user token: {user_token}")

    # You can add more functions or logic here that require login info
    # For example:
    # fetch_market_data(user_token)
    # place_order(user_token)


def fetch_and_read_zip_csv(url):
    response = requests.get(url)

    if response.status_code == 200:
        with zipfile.ZipFile(io.BytesIO(response.content)) as zip_ref:
            for file_name in zip_ref.namelist():
                if file_name.endswith('.txt'):
                    with zip_ref.open(file_name) as file:
                        data = pd.read_csv(file, delimiter='|')  # Shoonya uses '|' as delimiter
                        return data
            print("❌ No valid .txt file found in the ZIP archive.")
    else:
        print(f"❌ Failed to fetch the ZIP file. Status code: {response.status_code}")
    return None


def get_weekly_expiry():
    today = datetime.datetime.today()
    # Find the next Thursday (weekday=3)
    days_until_thursday = (3 - today.weekday() + 7) % 7
    if days_until_thursday == 0:
        expiry = today
    else:
        expiry = today + datetime.timedelta(days=days_until_thursday)
    return expiry.strftime('%d%b%y').upper()  # e.g., '15MAY25'


def get_niftyStrikePrice(api):
    # Fetch live index price for NIFTY 50
    nifty_data = api.get_quotes(exchange='NSE',
                                token='26000')  # 'NSE' and 'NIFTY' are exchange and symbol for NIFTY index
    #print(nifty_data)
    if nifty_data and 'lp' in nifty_data:
        current_price = float(nifty_data['lp'])  # 'lp' is Last Price
        strike_price = round(current_price / 50) * 50  # Round to nearest 50
        print(f"Current NIFTY price: {current_price}")
        print(f"ATM Strike Price: {strike_price}")
        return strike_price
    else:
        print("Failed to fetch NIFTY price.")


def get_option_symbol(strike_price, option_type, expiry_date_str):
    # Build symbol like NIFTY15MAY25C29600
    return f'NIFTY{expiry_date_str}{option_type}{int(strike_price)}'


def download_and_extract_symbols(zip_url):
    response = requests.get(zip_url)
    if response.status_code == 200:
        with zipfile.ZipFile(io.BytesIO(response.content)) as z:
            for filename in z.namelist():
                if filename.endswith('.txt'):
                    with z.open(filename) as f:
                        lines = f.read().decode('utf-8').splitlines()
                        return lines
    else:
        raise Exception(f"Failed to download file: {response.status_code}")


# ---------- Step 2: Extract ATM CE/PE from symbol list ----------
def get_atm_option_symbols_from_lines(lines, strike_price):
    pattern = re.compile(rf'NIFTY.*{strike_price}(CE|PE)')

    matches = [line.strip() for line in lines if pattern.search(line)]

    if not matches:
        print("No matching options found.")
        return None, None

def extract_expiry(symbol):
    match = re.search(r'NIFTY(\d{2}[A-Z]{1}\d{2})', symbol)
    if match:
        try:
            return datetime.strptime(match.group(1), '%y%b%d')
        except:
            return None
    return None

    matches = sorted(matches, key=lambda sym: extract_expiry(sym) or datetime.max)

    atm_ce = atm_pe = None
    for sym in matches:
        if sym.endswith('CE') and atm_ce is None:
            atm_ce = sym
        elif sym.endswith('PE') and atm_pe is None:
            atm_pe = sym
        if atm_ce and atm_pe:
            break

    return atm_ce, atm_pe

def getTotalStraddlePrice(api,response):
    global total
    strike_price = 0
    # Check if login is successful
    if response and response.get('stat') == 'Ok':
        print("✅ Login successful!")
        # perform_operations(response)  # Pass response or token to operations
        strike_price = get_niftyStrikePrice(api)
    else:
        print("❌ Login failed!")
        print("Reason:", response.get('emsg') if response else "No response")

    expiry = get_weekly_expiry()
    ce_symbol = get_option_symbol(strike_price, 'C', expiry)
    pe_symbol = get_option_symbol(strike_price, 'P', expiry)

    # Fetch quotes
    ce_data = api.get_quotes('NFO', ce_symbol)
    pe_data = api.get_quotes('NFO', pe_symbol)

    ce_price = float(ce_data['lp']) if ce_data and 'lp' in ce_data else None
    pe_price = float(pe_data['lp']) if pe_data and 'lp' in pe_data else None

    if ce_price is not None:
        print(f"{ce_symbol} Price: {ce_price}")
    else:
        print("CE quote not found")

    if pe_price is not None:
        print(f"{pe_symbol} Price: {pe_price}")
    else:
        print("PE quote not found")

    # Print sum if both prices are available
    if ce_price is not None and pe_price is not None:
        total = ce_price + pe_price
        print(f"Total CE + PE Premium: {total}")
    else:
        print("Cannot calculate total premium due to missing data.")

    return {
        'Time': datetime.datetime.now().strftime('%H:%M:%S'),
        'Strike Price': strike_price,
        'CE Price': ce_price,
        'PE Price': pe_price,
        'Total Premium': total
    }

def updateExcel(duration_minutes,interval_seconds,api,response):

    records = []
    end_time = time.time() + duration_minutes * 60

    while time.time() < end_time:
        strike_price = 0
        ce_price = pe_price = total = None

        if response and response.get('stat') == 'Ok':
            strike_price, ce_price, pe_price, total=getTotalStarddlePrice(api, response)
            print(
                f"[{datetime.datetime.now().strftime('%H:%M:%S')}] Strike: {strike_price}, CE: {ce_price}, PE: {pe_price}, Total: {total}")
            records.append({
                'Time': datetime.datetime.now().strftime('%H:%M:%S'),
                'Strike Price': strike_price,
                'CE Price': ce_price,
                'PE Price': pe_price,
                'Total Premium': total
            })

            time.sleep(interval_seconds)

            # Save to Excel
        df = pd.DataFrame(records)
        df.to_excel("nifty_straddle_log.xlsx", index=False)
        print("✅ Data written to 'nifty_straddle_log.xlsx'")

