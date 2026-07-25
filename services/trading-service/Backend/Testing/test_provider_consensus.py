from datetime import datetime

from Backend.application.provider_consensus_engine import (
    ProviderConsensusEngine
)


class FakeProvider:

    name = "fake_provider"

    def get_quote(self, symbol):

        return {
            "ltp": 23850,
            "bid": 23849,
            "ask": 23851,
            "volume": 100000,
            "timestamp": datetime.now(),
            "received_at": datetime.now(),
        }


def test_provider_snapshot():

    engine = ProviderConsensusEngine(
        providers=[
            FakeProvider()
        ]
    )

    snapshots = engine.get_provider_snapshots(
        "NIFTY"
    )

    assert len(snapshots) == 1

    assert snapshots[0].provider == "fake_provider"

    assert snapshots[0].ltp == 23850


if __name__ == "__main__":

    test_provider_snapshot()

    print("TEST PASSED")
    
def test_provider_health():

    engine = ProviderConsensusEngine(
        providers=[
            FakeProvider()
        ]
    )

    snapshots = engine.get_provider_snapshots(
        "NIFTY"
    )

    result = engine.validate_provider_health(
        snapshots
    )

    assert result[0].healthy is True

    print("HEALTH TEST PASSED")    
    
def test_live_suitability():

    engine = ProviderConsensusEngine(
        providers=[
            FakeProvider()
        ]
    )

    snapshots = engine.get_provider_snapshots(
        "NIFTY"
    )

    snapshots = engine.validate_provider_health(
        snapshots
    )

    snapshots = engine.validate_live_suitability(
        snapshots
    )

    assert snapshots[0].live_suitable is True

    print("LIVE SUITABILITY TEST PASSED")
def test_compare_prices():

    engine = ProviderConsensusEngine(
        providers=[
            FakeProvider()
        ]
    )

    snapshots = engine.get_provider_snapshots(
        "NIFTY"
    )

    result = engine.compare_prices(
        snapshots
    )

    print(result)

    assert result["status"] == "OK"
    assert result["average_price"] == 23850


    print("PRICE COMPARE TEST PASSED")
    
def test_compare_bid_ask():

    engine = ProviderConsensusEngine(
        providers=[
            FakeProvider()
        ]
    )

    snapshots = engine.get_provider_snapshots(
        "NIFTY"
    )

    result = engine.compare_bid_ask(
        snapshots
    )

    print(result)

    assert result["status"] == "OK"
    assert result["average_spread"] == 2

    print("BID ASK TEST PASSED")
def test_compare_volume():

    engine = ProviderConsensusEngine(
        providers=[
            FakeProvider()
        ]
    )

    snapshots = engine.get_provider_snapshots(
        "NIFTY"
    )

    result = engine.compare_volume(
        snapshots
    )

    print(result)

    assert result["status"] == "OK"
    assert result["average_volume"] == 100000

    print("VOLUME TEST PASSED")
def test_compare_timestamps():

    engine = ProviderConsensusEngine(
        providers=[
            FakeProvider()
        ]
    )

    snapshots = engine.get_provider_snapshots(
        "NIFTY"
    )

    result = engine.compare_timestamps(
        snapshots
    )

    print(result)

    assert result["status"] == "OK"

    print("TIMESTAMP TEST PASSED")
def test_calculate_latency():

    engine = ProviderConsensusEngine(
        providers=[
            FakeProvider()
        ]
    )

    snapshots = engine.get_provider_snapshots(
        "NIFTY"
    )

    snapshots[0].latency_ms = 120


    result = engine.calculate_latency(
        snapshots
    )

    print(result)


    assert result["status"] == "OK"
    assert result["average_latency_ms"] == 120


    print("LATENCY TEST PASSED")    