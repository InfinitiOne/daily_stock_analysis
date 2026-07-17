from data_provider.jeac_source_policy import assess_evidence, assess_source_chain, get_source_policy


def test_tw_quote_policy_requires_official_and_cross_validation():
    policy = get_source_policy("TW", "quote")
    assert policy is not None
    assert policy.preferred[:2] == ("TWSE", "TPEx")
    assert policy.minimum_sources == 2


def test_single_yfinance_source_is_partial_and_discloses_gaps():
    result = assess_evidence("tw", "quote", ["YfinanceFetcher"])
    assert result.status == "partial"
    assert result.official_source_present is False
    assert result.cross_validated is False
    assert "official_source_missing" in result.limitations
    assert "insufficient_independent_sources" in result.limitations


def test_verified_evidence_requires_explicit_value_comparison():
    result = assess_evidence(
        "tw", "quote", ["TWSE", "YfinanceFetcher"], values_consistent=True
    )
    assert result.status == "verified"
    assert result.official_source_present is True
    assert result.cross_validated is True


def test_source_chain_does_not_claim_cross_validation_without_comparison():
    result = assess_source_chain(
        "tw",
        "institution",
        [{"provider": "TWSE-T86", "result": "ok"}],
    )
    assert result["official_source_present"] is True
    assert result["cross_validated"] is False
    assert "values_not_compared" in result["limitations"]
