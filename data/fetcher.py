import ccxt
import pandas as pd
from datetime import datetime


SUPPORTED_TIMEFRAMES = ["1m", "5m", "15m", "30m", "1h", "4h", "1d", "1w"]


def fetch_ohlcv(
    symbol: str,
    timeframe: str,
    start_date: str,
    end_date: str,
    exchange_id: str = "bybit",
) -> pd.DataFrame:
    """
    Fetch historical OHLCV candles from a ccxt-compatible exchange.

    Returns DataFrame indexed by UTC datetime with columns:
    open, high, low, close, volume
    """
    exchange_class = getattr(ccxt, exchange_id)
    exchange = exchange_class({"enableRateLimit": True})

    since = int(datetime.strptime(start_date, "%Y-%m-%d").timestamp() * 1000)
    end_ts = int(datetime.strptime(end_date, "%Y-%m-%d").timestamp() * 1000)

    all_ohlcv = []
    prev_last_ts: int | None = None
    while since < end_ts:
        batch = exchange.fetch_ohlcv(symbol, timeframe, since=since, limit=1000)
        if not batch:
            break
        all_ohlcv.extend(batch)
        last_ts = batch[-1][0]
        # Stop once we've covered the requested range.
        if last_ts >= end_ts:
            break
        # Guard against exchanges that return short pages (OKX caps at 100–300
        # per request, not 1000) — keep paginating regardless of page size, but
        # bail if the cursor stops advancing to avoid an infinite loop.
        if prev_last_ts is not None and last_ts <= prev_last_ts:
            break
        prev_last_ts = last_ts
        since = last_ts + 1

    if not all_ohlcv:
        raise ValueError(f"No data returned for {symbol} {timeframe} [{start_date} – {end_date}]")

    df = pd.DataFrame(all_ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
    df.set_index("timestamp", inplace=True)
    df = df[df.index <= pd.Timestamp(end_date, tz="UTC")]
    df = df[~df.index.duplicated(keep="first")]
    df.sort_index(inplace=True)

    return df.astype(float)
