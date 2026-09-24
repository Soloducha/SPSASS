"""Tests for SMTP settings and alert channels validation (T1)."""


import pytest
from app.api.v1.schemas import AlertRuleCreate, AlertRuleUpdate, EmailChannel, WebhookChannel
from app.core.config import Settings, get_settings
from pydantic import ValidationError


class TestSMTPDefaults:
    """Tests for SMTP settings defaults and env override."""

    def test_defaults_disable_email(self) -> None:
        """Default settings leave smtp_enabled == False."""
        settings = Settings()
        assert settings.SMTP_HOST == ""
        assert settings.SMTP_PORT == 587
        assert settings.SMTP_USER == ""
        assert settings.SMTP_PASSWORD == ""
        assert settings.SMTP_FROM == ""
        assert settings.SMTP_STARTTLS is True
        assert settings.smtp_enabled is False

    def test_env_override_enables_smtp(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Override via env vars enables smtp_enabled."""
        monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
        monkeypatch.setenv("SMTP_PORT", "465")
        monkeypatch.setenv("SMTP_USER", "user")
        monkeypatch.setenv("SMTP_PASSWORD", "pass")
        monkeypatch.setenv("SMTP_FROM", "alerts@example.com")
        monkeypatch.setenv("SMTP_STARTTLS", "false")

        # Clear lru_cache to force re-read
        get_settings.cache_clear()
        settings = Settings()

        assert settings.SMTP_HOST == "smtp.example.com"
        assert settings.SMTP_PORT == 465
        assert settings.SMTP_USER == "user"
        assert settings.SMTP_PASSWORD == "pass"
        assert settings.SMTP_FROM == "alerts@example.com"
        assert settings.SMTP_STARTTLS is False
        assert settings.smtp_enabled is True

    def test_smtp_enabled_requires_both_host_and_from(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """smtp_enabled is True only when both HOST and FROM are set."""
        get_settings.cache_clear()

        # Only host
        monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
        monkeypatch.delenv("SMTP_FROM", raising=False)
        settings = Settings()
        assert settings.smtp_enabled is False

        # Only from
        get_settings.cache_clear()
        monkeypatch.delenv("SMTP_HOST", raising=False)
        monkeypatch.setenv("SMTP_FROM", "alerts@example.com")
        settings = Settings()
        assert settings.smtp_enabled is False

        # Both set
        get_settings.cache_clear()
        monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
        monkeypatch.setenv("SMTP_FROM", "alerts@example.com")
        settings = Settings()
        assert settings.smtp_enabled is True


class TestChannelModels:
    """Tests for channel validation models."""

    def test_valid_webhook_channel(self) -> None:
        """Valid webhook channel passes."""
        channel = WebhookChannel(url="https://example.com/webhook", headers={"X-Custom": "value"})  # type: ignore[arg-type]
        assert str(channel.url) == "https://example.com/webhook"
        assert channel.headers == {"X-Custom": "value"}

    def test_webhook_channel_defaults_headers(self) -> None:
        """Webhook channel defaults headers to empty dict."""
        channel = WebhookChannel(url="https://example.com/webhook")  # type: ignore[arg-type]
        assert str(channel.url) == "https://example.com/webhook"
        assert channel.headers == {}

    def test_webhook_channel_invalid_url_fails(self) -> None:
        """Invalid webhook URL fails validation."""
        with pytest.raises(ValidationError) as exc:
            WebhookChannel(url="not-a-url")  # type: ignore[arg-type]
        assert "url" in str(exc.value).lower()

    def test_valid_email_channel(self) -> None:
        """Valid email channel passes."""
        channel = EmailChannel(to=["user1@example.com", "user2@example.com"])
        assert channel.to == ["user1@example.com", "user2@example.com"]

    def test_email_channel_empty_to_fails(self) -> None:
        """Email channel with empty 'to' list fails."""
        with pytest.raises(ValidationError) as exc:
            EmailChannel(to=[])
        assert "to" in str(exc.value).lower()

    def test_email_channel_invalid_email_fails(self) -> None:
        """Email channel with invalid email fails."""
        with pytest.raises(ValidationError) as exc:
            EmailChannel(to=["not-an-email"])
        assert "to" in str(exc.value).lower()


class TestAlertRuleChannelsValidation:
    """Tests for AlertRuleCreate/Update channels validation."""

    # ── Valid cases ──

    def test_create_valid_webhook_only(self) -> None:
        """Create with valid webhook channel passes."""
        rule = AlertRuleCreate(
            entity_type="server",  # type: ignore[arg-type]
            metric="cpu_usage",
            operator="gt",  # type: ignore[arg-type]
            threshold=80.0,
            channels={"webhook": {"url": "https://example.com/webhook"}},
        )
        assert rule.channels == {"webhook": {"url": "https://example.com/webhook", "headers": {}}}

    def test_create_valid_email_only(self) -> None:
        """Create with valid email channel passes."""
        rule = AlertRuleCreate(
            entity_type="server",  # type: ignore[arg-type]
            metric="cpu_usage",
            operator="gt",  # type: ignore[arg-type]
            threshold=80.0,
            channels={"email": {"to": ["ops@example.com"]}},
        )
        assert rule.channels == {"email": {"to": ["ops@example.com"]}}

    def test_create_valid_both_channels(self) -> None:
        """Create with both webhook and email channels passes."""
        rule = AlertRuleCreate(
            entity_type="server",  # type: ignore[arg-type]
            metric="cpu_usage",
            operator="gt",  # type: ignore[arg-type]
            threshold=80.0,
            channels={
                "webhook": {"url": "https://example.com/webhook", "headers": {"Auth": "token"}},  # type: ignore[arg-type]
                "email": {"to": ["ops@example.com", "dev@example.com"]},
            },
        )
        assert "webhook" in rule.channels
        assert "email" in rule.channels
        assert rule.channels["webhook"]["headers"] == {"Auth": "token"}

    def test_update_valid_channels(self) -> None:
        """Update with valid channels passes."""
        rule = AlertRuleUpdate(
            channels={"webhook": {"url": "https://example.com/new-webhook"}},
        )
        assert rule.channels == {"webhook": {"url": "https://example.com/new-webhook", "headers": {}}}

    def test_update_none_channels(self) -> None:
        """Update with channels=None passes (no change)."""
        rule = AlertRuleUpdate(threshold=90.0, channels=None)
        assert rule.channels is None

    # ── Invalid cases ──

    def test_create_empty_channels_fails(self) -> None:
        """Create with empty channels dict fails."""
        with pytest.raises(ValidationError) as exc:
            AlertRuleCreate(
                entity_type="server",  # type: ignore[arg-type]
                metric="cpu_usage",
                operator="gt",  # type: ignore[arg-type]
                threshold=80.0,
                channels={},
            )
        assert "at least one channel" in str(exc.value).lower()

    def test_create_unknown_channel_key_fails(self) -> None:
        """Create with unknown channel key fails."""
        with pytest.raises(ValidationError) as exc:
            AlertRuleCreate(
                entity_type="server",  # type: ignore[arg-type]
                metric="cpu_usage",
                operator="gt",  # type: ignore[arg-type]
                threshold=80.0,
                channels={"sms": {}},
            )
        assert "unknown channel keys" in str(exc.value).lower()
        assert "sms" in str(exc.value).lower()

    def test_create_webhook_missing_url_fails(self) -> None:
        """Create with webhook missing url fails."""
        with pytest.raises(ValidationError) as exc:
            AlertRuleCreate(
                entity_type="server",  # type: ignore[arg-type]
                metric="cpu_usage",
                operator="gt",  # type: ignore[arg-type]
                threshold=80.0,
                channels={"webhook": {}},
            )
        assert "url" in str(exc.value).lower()

    def test_create_webhook_invalid_url_fails(self) -> None:
        """Create with webhook invalid URL fails."""
        with pytest.raises(ValidationError) as exc:
            AlertRuleCreate(
                entity_type="server",  # type: ignore[arg-type]
                metric="cpu_usage",
                operator="gt",  # type: ignore[arg-type]
                threshold=80.0,
                channels={"webhook": {"url": "not-a-url"}},  # type: ignore[arg-type]
            )
        assert "url" in str(exc.value).lower()

    def test_create_email_empty_to_fails(self) -> None:
        """Create with email empty 'to' list fails."""
        with pytest.raises(ValidationError) as exc:
            AlertRuleCreate(
                entity_type="server",  # type: ignore[arg-type]
                metric="cpu_usage",
                operator="gt",  # type: ignore[arg-type]
                threshold=80.0,
                channels={"email": {"to": []}},
            )
        assert "to" in str(exc.value).lower()

    def test_create_email_invalid_email_fails(self) -> None:
        """Create with email invalid email format fails."""
        with pytest.raises(ValidationError) as exc:
            AlertRuleCreate(
                entity_type="server",  # type: ignore[arg-type]
                metric="cpu_usage",
                operator="gt",  # type: ignore[arg-type]
                threshold=80.0,
                channels={"email": {"to": ["not-an-email"]}},
            )
        assert "to" in str(exc.value).lower()

    def test_update_empty_channels_fails(self) -> None:
        """Update with empty channels dict fails (same rule as create)."""
        with pytest.raises(ValidationError) as exc:
            AlertRuleUpdate(channels={})
        assert "at least one channel" in str(exc.value).lower()

    def test_update_unknown_channel_key_fails(self) -> None:
        """Update with unknown channel key fails."""
        with pytest.raises(ValidationError) as exc:
            AlertRuleUpdate(channels={"telegram": {}})
        assert "unknown channel keys" in str(exc.value).lower()

    def test_update_webhook_missing_url_fails(self) -> None:
        """Update with webhook missing url fails."""
        with pytest.raises(ValidationError) as exc:
            AlertRuleUpdate(channels={"webhook": {}})
        assert "url" in str(exc.value).lower()

    def test_update_email_empty_to_fails(self) -> None:
        """Update with email empty 'to' list fails."""
        with pytest.raises(ValidationError) as exc:
            AlertRuleUpdate(channels={"email": {"to": []}})
        assert "to" in str(exc.value).lower()
