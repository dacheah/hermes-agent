"""Tests enforcing Twin Resolver Parity Contract between display and execution resolvers."""

import pytest
from unittest.mock import patch

from gateway.config import ChannelOverride, GatewayConfig, Platform, PlatformConfig
from gateway.run import GatewayRunner
from gateway.session import SessionSource


@pytest.fixture()
def runner():
    r = object.__new__(GatewayRunner)
    r._session_model_overrides = {}
    r.config = None
    return r


class TestTwinResolverParityContract:
    """Invariant tests: display resolver (_session_route_for_source) and execution
    resolver (_resolve_session_agent_runtime) must share exact model and provider semantics.
    """

    def test_parity_channel_override_valid(self, runner):
        """When a channel override specifies model and provider, both resolvers yield parity."""
        runner.config = GatewayConfig(
            platforms={
                Platform.DISCORD: PlatformConfig(
                    enabled=True,
                    channel_overrides={
                        "chan_1": ChannelOverride(
                            model="channel/custom-model",
                            provider="openrouter",
                        ),
                    },
                ),
            },
        )
        source = SessionSource(
            platform=Platform.DISCORD,
            chat_id="chan_1",
            user_id="user_1",
        )

        expected_route = {
            "provider": "openrouter",
            "api_key": "test_key",
            "base_url": "https://openrouter.ai/api/v1",
            "api_mode": "chat_completions",
        }

        with patch("gateway.run._resolve_gateway_model", return_value="global/default"), \
             patch("gateway.run._resolve_runtime_agent_kwargs", return_value={"provider": "anthropic"}), \
             patch("gateway.run._resolve_runtime_agent_kwargs_for_provider", return_value=dict(expected_route)):
            
            disp_model, disp_route = runner._session_route_for_source(source)
            exec_model, exec_runtime = runner._resolve_session_agent_runtime(
                source=source, user_config={"model": {"default": "global/default"}}
            )

        assert disp_model == exec_model == "channel/custom-model"
        assert disp_route["provider"] == exec_runtime["provider"] == "openrouter"

    def test_parity_failed_provider_fallback(self, runner):
        """When an override provider fails resolution (missing key/unsupported),
        both resolvers safely handle the condition without raising uncaught errors.
        """
        runner.config = GatewayConfig(
            platforms={
                Platform.DISCORD: PlatformConfig(
                    enabled=True,
                    channel_overrides={
                        "chan_broken": ChannelOverride(
                            model="channel/broken-model",
                            provider="broken_provider",
                        ),
                    },
                ),
            },
        )
        source = SessionSource(
            platform=Platform.DISCORD,
            chat_id="chan_broken",
            user_id="user_1",
        )

        with patch("gateway.run._resolve_gateway_model", return_value="global/default"), \
             patch("gateway.run._resolve_runtime_agent_kwargs", return_value={"provider": "anthropic"}), \
             patch("gateway.run._resolve_runtime_agent_kwargs_for_provider", side_effect=ValueError("Provider broken_provider unknown")):
            
            disp_model, disp_route = runner._session_route_for_source(source)
            exec_model, exec_runtime = runner._resolve_session_agent_runtime(
                source=source, user_config={"model": {"default": "global/default"}}
            )

        # Invariant: display resolver paired-fallback gracefully yields (None, None)
        assert disp_model is None
        assert disp_route is None
        # Invariant: execution resolver falls back both model and runtime to global default together
        assert exec_model == "global/default"
        assert exec_runtime.get("provider") == "anthropic"
