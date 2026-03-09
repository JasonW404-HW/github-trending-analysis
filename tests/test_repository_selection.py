from src.pipeline.repository_selection import (
    build_repository_search_text,
    collect_keyword_matches,
    normalize_keywords,
    normalize_match_mode,
    select_repositories_for_analysis,
)


def test_build_repository_search_text_combines_and_lowercases_fields():
    repo = {
        "repo_name": "Owner/Project",
        "name": "Project",
        "owner": "Owner",
        "description": "Awesome AI toolkit",
        "language": "Python",
        "topics": ["AI", "Toolkit"],
    }

    text = build_repository_search_text(repo)

    assert "owner/project" in text
    assert "awesome ai toolkit" in text
    assert "python" in text
    assert "ai toolkit" in text


def test_collect_keyword_matches_is_case_insensitive():
    repo = {
        "repo_name": "owner/agentx",
        "description": "A coding assistant",
        "topics": ["LLM", "Automation"],
    }

    hits = collect_keyword_matches(repo, ["assistant", "llm", "missing"])

    assert hits == ["assistant", "llm"]


def test_normalize_keywords_filters_empty_values():
    assert normalize_keywords([" ai ", "", "   ", "ml"]) == ["ai", "ml"]


def test_normalize_match_mode_defaults_to_any_for_invalid_value():
    assert normalize_match_mode("invalid") == "any"
    assert normalize_match_mode("ALL") == "all"


def test_select_repositories_returns_empty_when_top_n_non_positive():
    result = select_repositories_for_analysis(repos=[{"repo_name": "a/b"}], top_n=0)

    assert result.repos == []
    assert result.total_count == 1
    assert result.selected_count == 0


def test_select_repositories_without_keywords_uses_rank_order():
    repos = [
        {"repo_name": "a/one", "rank": 2},
        {"repo_name": "a/two", "rank": 1},
    ]

    result = select_repositories_for_analysis(repos, top_n=1, keywords=[])

    assert result.selected_count == 1
    assert result.repos[0]["repo_name"] == "a/one"
    assert result.keywords == []


def test_select_repositories_any_mode_adds_hits_and_scores():
    repos = [
        {"repo_name": "a/one", "description": "python ai", "rank": 3},
        {"repo_name": "a/two", "description": "python", "rank": 1},
        {"repo_name": "a/three", "description": "rust", "rank": 2},
    ]

    result = select_repositories_for_analysis(
        repos,
        top_n=2,
        keywords=["python", "ai"],
        match_mode="any",
    )

    assert [repo["repo_name"] for repo in result.repos] == ["a/one", "a/two"]
    assert result.repos[0]["keyword_hits"] == ["python", "ai"]
    assert result.repos[0]["search_score"] == 2


def test_select_repositories_all_mode_requires_all_keywords():
    repos = [
        {"repo_name": "a/one", "description": "python ai"},
        {"repo_name": "a/two", "description": "python only"},
    ]

    result = select_repositories_for_analysis(
        repos,
        top_n=5,
        keywords=["python", "ai"],
        match_mode="all",
    )

    assert [repo["repo_name"] for repo in result.repos] == ["a/one"]
    assert result.match_mode == "all"
