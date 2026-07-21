"""
LARGE_CAP_TICKERS: a broad universe of well-known, established large/mid-cap
US-listed tickers, spanning every major sector — deliberately excludes
penny stocks and obscure/thinly-traded names.

IMPORTANT — read before relying on this for anything:
This is a best-effort, POINT-IN-TIME list assembled from general knowledge,
not a live feed of the actual current S&P 500 constituents. Index
membership changes over time (additions, removals, mergers, delistings),
and this list cannot be verified against a live source without network
access. Treat it as "a large set of genuinely well-known companies to
start from," not as an authoritative, current S&P 500 roster.

To get the real, current S&P 500 list instead: Wikipedia's "List of S&P
500 companies" page is commonly used as a free, regularly-updated source,
or a data provider's official constituents API/file. Swap this list out
for that once you have it, if exact index membership matters to you.

Before relying on this in the automated weekly equity cycle, run
scripts/verify_watchlist_markets.py once (with network access) — it flags
any ticker here that SEC EDGAR doesn't actually recognize, so bad entries
show up as a one-time report rather than silently degrading every cycle.
"""

LARGE_CAP_TICKERS = [
    # Technology
    "AAPL", "MSFT", "GOOGL", "GOOG", "AMZN", "NVDA", "META", "AVGO", "ORCL", "CRM",
    "ADBE", "CSCO", "ACN", "AMD", "INTC", "IBM", "TXN", "QCOM", "INTU", "NOW",
    "AMAT", "MU", "ADI", "LRCX", "KLAC", "SNPS", "CDNS", "PANW", "FTNT", "ANET",
    "CRWD", "WDAY", "TEAM", "ADSK", "MSI", "ROP", "APH", "TER", "KEYS", "GLW",
    "HPQ", "HPE", "NTAP", "STX", "WDC", "JNPR", "FFIV", "AKAM", "GEN", "EPAM",
    # Communication Services
    "NFLX", "DIS", "CMCSA", "T", "VZ", "TMUS", "CHTR", "EA", "TTWO", "WBD",
    "PARA", "OMC", "IPG", "LYV", "MTCH", "PINS", "SNAP", "ROKU",
    # Consumer Discretionary
    "TSLA", "HD", "MCD", "NKE", "LOW", "SBUX", "TJX", "BKNG", "ABNB", "CMG",
    "ORLY", "MAR", "GM", "F", "HLT", "YUM", "ROST", "DHI", "LEN", "NVR",
    "AZO", "EBAY", "ETSY", "BBY", "DPZ", "APTV", "GPC", "POOL", "ULTA", "TSCO",
    "RCL", "CCL", "NCLH", "EXPE", "WYNN", "MGM", "LVS", "DRI", "KMX", "LKQ",
    # Consumer Staples
    "WMT", "PG", "KO", "PEP", "COST", "PM", "MO", "MDLZ", "CL", "KMB",
    "GIS", "STZ", "SYY", "KHC", "HSY", "MKC", "CLX", "CHD", "TAP", "K",
    "CAG", "CPB", "SJM", "HRL", "TSN", "ADM", "BG", "KR", "DG", "DLTR",
    # Healthcare
    "UNH", "JNJ", "LLY", "ABBV", "MRK", "PFE", "TMO", "ABT", "DHR", "BMY",
    "AMGN", "MDT", "ISRG", "GILD", "CVS", "ELV", "SYK", "VRTX", "REGN", "CI",
    "ZTS", "BSX", "HCA", "HUM", "BDX", "IDXX", "EW", "IQV", "MRNA", "A",
    "RMD", "MTD", "DXCM", "BIIB", "WST", "CNC", "GEHC", "ALGN", "MOH", "INCY",
    # Financials
    "BRK.B", "JPM", "V", "MA", "BAC", "WFC", "GS", "MS", "SPGI", "AXP",
    "C", "SCHW", "BLK", "CB", "PGR", "MMC", "ICE", "PNC", "USB", "AON",
    "CME", "TFC", "AJG", "MCO", "COF", "TRV", "AIG", "MET", "PRU", "ALL",
    "BK", "FITB", "STT", "NTRS", "HBAN", "RF", "CFG", "KEY", "SYF", "DFS",
    # Industrials
    "GE", "CAT", "RTX", "HON", "UNP", "BA", "UPS", "LMT", "DE", "ETN",
    "ADP", "GD", "NOC", "ITW", "EMR", "CSX", "NSC", "WM", "PH", "TT",
    "CARR", "CTAS", "PCAR", "RSG", "FDX", "JCI", "CMI", "OTIS", "IR", "GWW",
    "URI", "FAST", "PAYX", "ODFL", "XYL", "DOV", "SNA", "AME", "ROK", "LHX",
    # Energy
    "XOM", "CVX", "COP", "SLB", "EOG", "MPC", "PSX", "VLO", "OXY", "WMB",
    "KMI", "OKE", "HES", "BKR", "FANG", "DVN", "TRGP", "HAL", "CTRA", "MRO",
    # Materials
    "LIN", "APD", "SHW", "ECL", "FCX", "NEM", "NUE", "DOW", "DD", "PPG",
    "VMC", "MLM", "ALB", "CTVA", "IFF", "LYB", "STLD", "CE", "MOS", "FMC",
    # Real Estate
    "PLD", "AMT", "EQIX", "CCI", "PSA", "SPG", "O", "WELL", "DLR", "AVB",
    "EQR", "SBAC", "VTR", "ARE", "EXR", "MAA", "ESS", "INVH", "UDR", "CPT",
    # Utilities
    "NEE", "SO", "DUK", "AEP", "SRE", "D", "EXC", "XEL", "ED", "PEG",
    "WEC", "ES", "FE", "AWK", "DTE", "PPL", "CMS", "EIX", "ATO", "AEE",
    # Additional well-known large/mid caps
    "PYPL", "SQ", "SHOP", "UBER", "LYFT", "DASH", "COIN", "PLTR", "SNOW",
    "DDOG", "NET", "ZS", "OKTA", "MDB", "HUBS", "TWLO", "DOCU", "ZM", "RBLX",
]
