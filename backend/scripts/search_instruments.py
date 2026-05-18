import pandas as pd
import requests

def search_instruments(query: str):
    print("Downloading latest instrument list from Zerodha...")
    url = "https://api.kite.trade/instruments"
    
    # Download CSV into pandas
    df = pd.read_csv(url)
    
    # Filter by query
    # E.g. search for "NIFTY" and "PE" or "CE"
    filtered = df[df['tradingsymbol'].str.contains(query, case=False, na=False)]
    
    print(f"\n--- Found {len(filtered)} results for '{query}' ---")
    if len(filtered) > 0:
        print(filtered[['instrument_token', 'tradingsymbol', 'name', 'instrument_type', 'exchange']].head(20).to_string(index=False))
    else:
        print("No instruments found.")

if __name__ == "__main__":
    query = input("Enter symbol to search (e.g., 'NIFTY 50', 'BANKNIFTY', 'RELIANCE'): ")
    search_instruments(query)
