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