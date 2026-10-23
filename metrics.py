"""Prometheus metrics: long-term numbers for dashboards (Grafana)."""

from prometheus_client import Counter, Gauge, Histogram

# How many requests the gateway handled, and how they ended.
REQUESTS = Counter(
    "gateway_requests_total",
    "Requests handled by the gateway",
    ["model", "served_by", "status"],
)

# Every attempt at a provider: ok, an error category, or circuit_open (skipped).
PROVIDER_ATTEMPTS = Counter(
    "gateway_provider_attempts_total",
    "Attempts at each provider, by outcome",
    ["provider", "outcome"],
)

# How long successful provider calls took, sorted into buckets (seconds).
LATENCY = Histogram(
    "gateway_provider_latency_seconds",
    "Latency of successful provider calls",
    ["provider"],
    buckets=(0.25, 0.5, 1, 2, 4, 8, 16, 32),
)

# Estimated spend, so cost can be shown per team and feature.
COST = Counter(
    "gateway_cost_usd_total",
    "Estimated spend in USD",
    ["tenant", "feature", "provider"],
)

# 1 if the provider's circuit breaker is open, 0 if closed.
CIRCUIT_OPEN = Gauge(
    "gateway_circuit_open",
    "1 if the provider's circuit breaker is open",
    ["provider"],
)