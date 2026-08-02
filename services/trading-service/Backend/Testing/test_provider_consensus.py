from datetime import datetime

from Backend.application.provider_consensus_engine import (
    ProviderConsensusEngine
)


class FakeProvider:

    provider_name = "fake_provider"
    name = "fake_provider"
    live_suitable = True

    def health_check(self):
        return {
            "healthy": True,
            "latency_ms": 50,
            "message": "OK"
        }

    def get_ltp(self, symbol):

        return {
            "ltp": 23850,
            "bid": 23849,
            "ask": 23851,
            "volume": 100000,
            "timestamp": datetime.now(),
        }


def create_engine():

    return ProviderConsensusEngine(
        providers=[
            FakeProvider()
        ]
    )


def test_provider_snapshot():

    engine = create_engine()

    snapshots = engine.get_provider_snapshots(
        "NIFTY"
    )

    assert len(snapshots) == 1
    assert snapshots[0].provider == "fake_provider"
    assert snapshots[0].ltp == 23850

    print("SNAPSHOT TEST PASSED")


def test_provider_health():

    engine = create_engine()

    snapshots = engine.get_provider_snapshots(
        "NIFTY"
    )

    result = engine.validate_provider_health(
        snapshots
    )

    assert result[0].healthy is True

    print("HEALTH TEST PASSED")


def test_live_suitability():

    engine = create_engine()

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

    engine = create_engine()

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

    engine = create_engine()

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

    engine = create_engine()

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

    engine = create_engine()

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

    engine = create_engine()

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


def test_calculate_feed_delay():

    engine = create_engine()

    snapshots = engine.get_provider_snapshots(
        "NIFTY"
    )

    snapshots[0].feed_delay_seconds = 2

    result = engine.calculate_feed_delay(
        snapshots
    )

    print(result)

    assert result["status"] == "OK"
    assert result["average_delay_seconds"] == 2

    print("FEED DELAY TEST PASSED")


def test_provider_scores():

    engine = create_engine()

    snapshots = engine.get_provider_snapshots(
        "NIFTY"
    )

    result = engine.calculate_provider_scores(
        snapshots
    )

    print(result)

    assert "fake_provider" in result
    assert result["fake_provider"] > 0

    print("PROVIDER SCORE TEST PASSED")


def test_calculate_confidence():

    engine = create_engine()

    snapshots = engine.get_provider_snapshots(
        "NIFTY"
    )

    result = engine.calculate_confidence(
        snapshots
    )

    print(result)

    assert result > 0
    assert result <= 100

    print("CONFIDENCE TEST PASSED")


def test_select_best_provider():

    engine = create_engine()

    snapshots = engine.get_provider_snapshots(
        "NIFTY"
    )

    result = engine.select_best_provider(
        snapshots
    )

    print(result)

    assert result.provider == "fake_provider"

    print("SELECT PROVIDER TEST PASSED")


def test_failover_provider():

    engine = create_engine()

    snapshots = engine.get_provider_snapshots(
        "NIFTY"
    )

    result = engine.perform_failover(
        snapshots
    )

    print(result)

    assert result.provider == "fake_provider"

    assert (
        result.diagnostics["failover_selected"]
        is True
    )

    print("FAILOVER TEST PASSED")


def test_build_consensus():

    engine = create_engine()

    result = engine.build_consensus(
        "NIFTY"
    )

    print(result)

    assert result.accepted is True

    assert (
        result.selected_provider
        == "fake_provider"
    )

    assert (
        result.consensus_price
        == 23850
    )

    print("BUILD CONSENSUS TEST PASSED")


if __name__ == "__main__":

    test_provider_snapshot()
    test_provider_health()
    test_live_suitability()
    test_compare_prices()
    test_compare_bid_ask()
    test_compare_volume()
    test_compare_timestamps()
    test_calculate_latency()
    test_calculate_feed_delay()
    test_provider_scores()
    test_calculate_confidence()
    test_select_best_provider()
    test_failover_provider()
    test_build_consensus()

    print(
        "ALL PROVIDER CONSENSUS TESTS PASSED"
    )