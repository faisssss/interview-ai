from app.config import Settings


def test_defaults_match_spec():
    s = Settings(_env_file=None)  # pyright: ignore[reportCallIssue]
    assert s.llm_model_extract == "claude-opus-5-5"
    assert s.llm_effort_extract == "medium"
    assert s.asr_model == "large-v3-turbo"
    assert (s.max_duration_minutes, s.max_upload_mb) == (180, 500)
    assert (s.job_max_attempts, s.job_stale_minutes, s.heartbeat_seconds) == (3, 10, 30.0)


def test_environment_overrides_defaults(monkeypatch):
    monkeypatch.setenv("ASR_PROVIDER", "fake")
    assert Settings(_env_file=None).asr_provider == "fake"  # pyright: ignore[reportCallIssue]
