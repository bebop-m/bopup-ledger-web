import json
import math
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote

import requests

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / 'data'
WATCHLIST_PATH = DATA_DIR / 'watchlist.json'
OUTPUT_PATH = DATA_DIR / 'market.json'
DEFAULT_RATES = {'CNY': 1, 'USD': 7.22, 'HKD': 0.92}
QUOTE_ENDPOINT = 'https://query1.finance.yahoo.com/v7/finance/quote'
CHART_ENDPOINT = 'https://query1.finance.yahoo.com/v8/finance/chart/{symbol}'
REQUEST_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                  '(KHTML, like Gecko) Chrome/134.0 Safari/537.36',
    'Accept': 'application/json,text/plain,*/*',
    'Accept-Language': 'en-US,en;q=0.9'
}


def load_watchlist():
    payload = json.loads(WATCHLIST_PATH.read_text(encoding='utf-8-sig'))
    return [str(symbol).strip().upper() for symbol in payload.get('symbols', []) if str(symbol).strip()]


def load_previous_snapshot():
    if not OUTPUT_PATH.exists():
        return {}
    try:
        return json.loads(OUTPUT_PATH.read_text(encoding='utf-8-sig'))
    except Exception:
        return {}


def safe_float(value, default=0.0):
    if value is None:
        return default
    if isinstance(value, str):
        cleaned = value.strip().replace(',', '').replace('%', '')
        if cleaned in {'', '--', 'nan', 'None', 'null'}:
            return default
        value = cleaned
    try:
        parsed = float(value)
    except Exception:
        return default
    return parsed if math.isfinite(parsed) else default


def fetch_json(url, params=None, timeout=20):
    response = requests.get(url, params=params, timeout=timeout, headers=REQUEST_HEADERS)
    response.raise_for_status()
    return response.json()


def fetch_with_retry(label, fn, *args, retries=3, delay_seconds=2, **kwargs):
    last_error = None
    for attempt in range(1, retries + 1):
        try:
            return fn(*args, **kwargs)
        except Exception as error:
            last_error = error
            print(f'{label} failed on attempt {attempt}/{retries}: {error}')
            if attempt < retries:
                time.sleep(delay_seconds)
    raise last_error


def to_yahoo_symbol(symbol):
    normalized = str(symbol).strip().upper()
    if normalized.endswith('.HK'):
        raw = normalized[:-3]
        digits = raw.lstrip('0')
        digits = digits.zfill(4) if digits else '0000'
        return f'{digits}.HK'
    if normalized.endswith('.SH'):
        return f'{normalized[:-3]}.SS'
    return normalized


def from_yahoo_symbol(symbol):
    normalized = str(symbol).strip().upper()
    if normalized.endswith('.HK'):
        return f'{normalized[:-3].zfill(5)}.HK'
    if normalized.endswith('.SS'):
        return f'{normalized[:-3]}.SH'
    return normalized


def infer_market_currency(symbol):
    if symbol.endswith('.HK'):
        return 'HK', 'HKD'
    if symbol.endswith('.SH') or symbol.endswith('.SZ'):
        return 'CN', 'CNY'
    return 'US', 'USD'


def fetch_quotes(watchlist):
    yahoo_symbols = [to_yahoo_symbol(symbol) for symbol in watchlist]
    payload = fetch_json(QUOTE_ENDPOINT, params={'symbols': ','.join(yahoo_symbols)})
    results = (payload.get('quoteResponse') or {}).get('result') or []
    quotes = {}

    for item in results:
        yahoo_symbol = str(item.get('symbol') or '').upper()
        symbol = from_yahoo_symbol(yahoo_symbol)
        market, currency = infer_market_currency(symbol)
        price = safe_float(
            item.get('regularMarketPrice'),
            safe_float(item.get('postMarketPrice'), safe_float(item.get('previousClose'), 0))
        )
        quotes[symbol] = {
            'symbol': symbol,
            'name': str(item.get('shortName') or item.get('longName') or symbol).strip(),
            'market': market,
            'currency': currency,
            'price': round(price, 6),
            'dividendYield': 0,
            'dividendPerShareTtm': 0
        }

    return quotes


def sum_ttm_dividends(dividend_events):
    if not dividend_events:
        return 0.0
    threshold = datetime.now(timezone.utc) - timedelta(days=365)
    total = 0.0
    for event in dividend_events.values():
        amount = safe_float(event.get('amount'), 0)
        event_ts = event.get('date')
        if amount <= 0 or not event_ts:
            continue
        event_date = datetime.fromtimestamp(int(event_ts), tz=timezone.utc)
        if event_date >= threshold:
            total += amount
    return round(total, 6)


def fetch_dividend_metrics(symbol, current_price):
    yahoo_symbol = to_yahoo_symbol(symbol)
    payload = fetch_json(
        CHART_ENDPOINT.format(symbol=quote(yahoo_symbol, safe='')),
        params={'range': '2y', 'interval': '1d', 'events': 'div'}
    )
    result = ((payload.get('chart') or {}).get('result') or [None])[0] or {}
    events = (result.get('events') or {}).get('dividends') or {}
    dividend_per_share_ttm = sum_ttm_dividends(events)
    dividend_yield = (dividend_per_share_ttm / current_price) if current_price > 0 else 0.0
    return {
        'dividendPerShareTtm': round(dividend_per_share_ttm, 6),
        'dividendYield': round(dividend_yield, 6)
    }


def fetch_selected_dividend_metrics(watchlist, quotes):
    metrics = {}
    targets = [symbol for symbol in watchlist if symbol.endswith('.HK') or symbol.endswith('.SH') or symbol.endswith('.SZ')]

    for symbol in targets:
        price = safe_float((quotes.get(symbol) or {}).get('price'), 0)
        try:
            metrics[symbol] = fetch_with_retry(
                f'dividend {symbol}',
                fetch_dividend_metrics,
                symbol,
                price,
                retries=2,
                delay_seconds=1
            )
        except Exception as error:
            print(f'dividend refresh skipped for {symbol}: {error}')

    return metrics


def fetch_rates():
    payload = fetch_json('https://api.frankfurter.dev/v1/latest?base=CNY&symbols=USD,HKD')
    usd = float(payload['rates']['USD'])
    hkd = float(payload['rates']['HKD'])
    return {
        'CNY': 1,
        'USD': round(1 / usd, 4),
        'HKD': round(1 / hkd, 4)
    }


def seed_quotes_from_previous(previous_snapshot, watchlist):
    previous_quotes = previous_snapshot.get('quotes') or {}
    seeded = {}
    for symbol in watchlist:
        if symbol in previous_quotes:
            seeded[symbol] = previous_quotes[symbol]
    return seeded


def main():
    watchlist = load_watchlist()
    previous_snapshot = load_previous_snapshot()
    quotes = seed_quotes_from_previous(previous_snapshot, watchlist)
    rates = {**DEFAULT_RATES, **(previous_snapshot.get('rates') or {})}

    try:
        fresh_quotes = fetch_with_retry('yahoo quotes', fetch_quotes, watchlist, retries=3, delay_seconds=2)
        quotes.update(fresh_quotes)
    except Exception as error:
        print(f'quote refresh skipped: {error}')

    try:
        dividend_metrics = fetch_selected_dividend_metrics(watchlist, quotes)
        for symbol, metric in dividend_metrics.items():
            if symbol in quotes:
                quotes[symbol].update(metric)
    except Exception as error:
        print(f'dividend refresh skipped: {error}')

    try:
        rates = fetch_with_retry('fx rates', fetch_rates, retries=3, delay_seconds=2)
    except Exception as error:
        print(f'fx refresh skipped: {error}')

    payload = {
        'ok': True,
        'provider': {
            'quote': 'yahoo-finance',
            'fx': 'frankfurter',
            'dividend': 'yahoo-finance'
        },
        'updatedAt': datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
        'rates': rates,
        'quotes': quotes
    }
    OUTPUT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'updated {len(quotes)} quotes into {OUTPUT_PATH}')


if __name__ == '__main__':
    main()
