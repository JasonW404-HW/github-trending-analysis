from src.pipeline.change_scoring import compute_change_score, should_force_reanalysis


def test_compute_change_score_returns_full_for_first_analysis():
    score = compute_change_score(repo={"repo_name": "owner/repo"}, state=None)
    assert score == 100.0


def test_should_force_reanalysis_with_threshold_and_top_bucket():
    reasons = should_force_reanalysis(
        repo={"rank": 3},
        state={
            "last_prompt_hash": "abc",
            "last_model": "m1",
            "last_rank_bucket": "other",
        },
        prompt_hash="abc",
        model="m1",
        change_score=80,
        threshold=50,
        manual_force=False,
        top_bucket_size=5,
    )

    assert "change_score_threshold" in reasons
    assert "top_bucket_entered" in reasons
