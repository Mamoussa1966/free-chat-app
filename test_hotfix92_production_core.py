from production_core import (
    FreeCascadeController, ProviderExecutionContract, RequestLifecycle,
    RequestState, RoundState, SharedContextStateMachine, TransactionBridgeGuard,
)


def test_request_lifecycle_and_round_state_machine():
    life = RequestLifecycle.begin("req-92")
    assert life.state is RequestState.RUNNING
    life.start_round(1)
    life.finish_round(1, 2, 3)
    assert life.rounds[1] is RoundState.PARTIAL
    life.finish(True)
    assert life.state is RequestState.COMPLETED
    assert all(e.request_id == "req-92" for e in life.audit)


def test_free_cascade_preserves_explicit_order_and_max_ten():
    c = FreeCascadeController([f"m{i}" for i in range(1, 15)])
    assert [c.next_model() for _ in range(12)] == [f"m{i}" for i in range(1, 11)] + [None, None]
    assert FreeCascadeController.should_continue("QUOTA_EXCEEDED", True)
    assert not FreeCascadeController.should_continue("AUTHENTICATION_ERROR", True)


def test_provider_success_contract_requires_actual_attested_model():
    good = {
        "status": "SUCCESS", "seat": "gemini", "content": "answer",
        "model": "gemini-a", "executed_model": "gemini-a",
        "provider_reported_model": "gemini-a", "attempted_models": ["gemini-a"],
    }
    ProviderExecutionContract.validate_success(good, "gemini")
    bad = dict(good, provider_reported_model="gemini-b")
    try:
        ProviderExecutionContract.validate_success(bad, "gemini")
    except ValueError:
        pass
    else:
        raise AssertionError("identity mismatch must fail closed")


def test_shared_context_and_bridge_require_commit_before_read_and_isolate_target():
    ctx = SharedContextStateMachine()
    ctx.begin_write(); ctx.commit(); ctx.open_barrier()
    assert ctx.state.value == "BARRIER_OPEN"
    bridge = TransactionBridgeGuard()
    bridge.stage("deepseek", "gemini", "BRIDGE_TEST")
    try:
        bridge.read("gemini")
    except RuntimeError:
        pass
    else:
        raise AssertionError("read before commit must fail")
    bridge.commit(); bridge.barrier(); bridge.read("gemini")
    assert bridge.state.value == "BARRIER_OPEN"
