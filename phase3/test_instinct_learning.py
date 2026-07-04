

# -----------------------------------------------------------------------
# Observation data source tests (ECC Phase 3 + hook-based observations)
# -----------------------------------------------------------------------

def test_load_observations_returns_empty_when_file_missing(tmp_path, monkeypatch):
    """observations.jsonl missing → returns empty dict (no crash)."""
    # Point OBSERVATIONS_FILE to non-existent path
    monkeypatch.setattr(
        "phase3.instinct_learning.OBSERVATIONS_FILE",
        tmp_path / "nonexistent.jsonl"
    )
    from phase3.instinct_learning import load_observations
    result = load_observations()
    assert result == {}


def test_load_observations_skips_old_entries(tmp_path, monkeypatch):
    """Entries older than max_age_hours are filtered out."""
    import json, time
    obs_file = tmp_path / "observations.jsonl"
    monkeypatch.setattr(
        "phase3.instinct_learning.OBSERVATIONS_FILE",
        obs_file
    )

    now = time.time()
    old_ts = now - (49 * 3600)   # 49h ago — should be filtered
    recent_ts = now - (1 * 3600)  # 1h ago — should be kept

    # Must have >= 3 tool calls per session (load_observations filters < 3)
    obs_file.write_text(
        json.dumps({"ts": old_ts, "tool": "terminal", "session_id": "old-sess", "args_keys": []}) + "\n"
        + json.dumps({"ts": old_ts, "tool": "read_file", "session_id": "old-sess", "args_keys": []}) + "\n"
        + json.dumps({"ts": old_ts, "tool": "patch", "session_id": "old-sess", "args_keys": []}) + "\n"
        + json.dumps({"ts": recent_ts, "tool": "terminal", "session_id": "new-sess", "args_keys": []}) + "\n"
        + json.dumps({"ts": recent_ts, "tool": "read_file", "session_id": "new-sess", "args_keys": []}) + "\n"
        + json.dumps({"ts": recent_ts, "tool": "patch", "session_id": "new-sess", "args_keys": []}) + "\n"
    )

    from phase3.instinct_learning import load_observations
    result = load_observations(max_age_hours=48.0)
    assert "old-sess" not in result
    assert "new-sess" in result
    assert len(result["new-sess"]) == 3


def test_extract_tool_sequences_from_observations_basic(tmp_path, monkeypatch):
    """Same session appearing twice produces sequences with count >= 2."""
    monkeypatch.setattr(
        "phase3.instinct_learning.OBSERVATIONS_FILE",
        tmp_path / "observations.jsonl"
    )
    from phase3.instinct_learning import extract_tool_sequences_from_observations

    obs = {
        "s1": ["terminal", "read_file", "patch", "write_file"],
        "s2": ["terminal", "read_file", "patch", "write_file"],
    }
    seqs = extract_tool_sequences_from_observations(obs, min_count=2)
    # (terminal,read_file) appears in both sessions → count=2
    two_grams = [s for s in seqs if len(s.tools) == 2]
    assert any(s.count >= 2 for s in two_grams), "cross-session 2-gram should have count >= 2"


def test_extract_tool_sequences_from_observations_empty():
    """Empty obs dict → returns empty list (no crash)."""
    from phase3.instinct_learning import extract_tool_sequences_from_observations
    result = extract_tool_sequences_from_observations({})
    assert result == []
