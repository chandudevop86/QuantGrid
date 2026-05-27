from scripts.check_no_secrets import find_secrets


def test_secret_scanner_detects_committed_secret_like_value(tmp_path):
    config = tmp_path / "deploy.yml"
    config.write_text('broker_access_token: "fake-token-value-that-is-long-enough"\n', encoding="utf-8")

    assert find_secrets(tmp_path) == ["deploy.yml"]


def test_secret_scanner_allows_placeholder_values(tmp_path):
    config = tmp_path / "deploy.yml"
    config.write_text('broker_access_token: "${BROKER_ACCESS_TOKEN}"\n', encoding="utf-8")

    assert find_secrets(tmp_path) == []
