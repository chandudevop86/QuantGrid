import yfinance as yf


class InstitutionalCollector:


    def get_market_data(self):

        data = {}

        # GIFT NIFTY proxy
        try:
            gift = yf.Ticker("^NSEI")
            price = gift.history(period="1d")

            data["gift_nifty"] = float(
                price["Close"].iloc[-1]
            )

        except Exception:

            data["gift_nifty"] = None



        # India VIX

        try:

            vix = yf.Ticker("^INDIAVIX")

            data["india_vix"] = float(
                vix.history(period="1d")
                ["Close"]
                .iloc[-1]
            )

        except:

            data["india_vix"] = None



        # USD INR

        try:

            fx = yf.Ticker(
                "USDINR=X"
            )

            data["usdinr"] = float(
                fx.history(period="1d")
                ["Close"]
                .iloc[-1]
            )

        except:

            data["usdinr"] = None



        # Crude

        try:

            crude = yf.Ticker(
                "CL=F"
            )

            data["crude_oil"] = float(
                crude.history(period="1d")
                ["Close"]
                .iloc[-1]
            )

        except:

            data["crude_oil"] = None



        # Gold

        try:

            gold = yf.Ticker(
                "GC=F"
            )

            data["gold"] = float(
                gold.history(period="1d")
                ["Close"]
                .iloc[-1]
            )

        except:

            data["gold"] = None



        return data