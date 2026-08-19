from uuid import uuid4

import pytest

from app.core.config import Settings
from app.observability.tracing import NoOpObservation, TracingService


@pytest.mark.unit
def test_tracing_service_unconfigured():
    settings = Settings(
        langfuse_enabled=False,
        gemini_api_key="test-key",
    )
    tracer = TracingService(settings)
    assert not tracer.is_active

    request_id = uuid4()
    with tracer.start_trace(
        name="test-trace", request_id=request_id, input_data={"query": "test"}
    ) as trace:
        assert isinstance(trace, NoOpObservation)
        trace.update(output={"status": "ok"})

        with tracer.span(name="test-span", as_type="retriever", input_data={"limit": 5}) as span:
            assert isinstance(span, NoOpObservation)
            span.update(output=[1, 2, 3])

        with tracer.generation(
            name="test-gen", model="gemini-3.6-flash", input_data="prompt"
        ) as gen:
            assert isinstance(gen, NoOpObservation)
            gen.update(output="summary", usage_details={"input": 10, "output": 20, "total": 30})

    tracer.flush()
    tracer.shutdown()


@pytest.mark.unit
def test_tracing_service_graceful_error_handling():
    settings = Settings(
        langfuse_enabled=True,
        langfuse_public_key="pk-test",
        langfuse_secret_key="sk-test",
        langfuse_base_url="http://invalid-host-for-test:9999",
        gemini_api_key="test-key",
    )
    tracer = TracingService(settings)
    # Even if initialized or failing, operations must not throw unhandled exceptions
    with tracer.start_trace(
        name="test-error-trace", request_id="6823dcdf-de9f-5b94-9baf-b2f850cf9700"
    ) as trace:
        trace.update(output="something")
        with tracer.span(name="span") as span:
            span.update(output=123)
        with tracer.generation(name="gen") as gen:
            gen.update(output="text")

    # Non-UUID request ID should not raise
    with tracer.start_trace(name="test-non-uuid-trace", request_id="custom-req-id") as trace:
        trace.update(output="something")

    tracer.flush()
    tracer.shutdown()

