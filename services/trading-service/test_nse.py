from Backend.application.providers.nse_playwright import fetch_nse_option_chain

print("Starting...")

data = fetch_nse_option_chain("NIFTY")

print("Success")
print(type(data))
print(data.keys())
print(len(data["records"]["data"]))
