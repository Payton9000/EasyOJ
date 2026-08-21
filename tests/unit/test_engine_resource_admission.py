def test_judge_engine_configures_bounded_resource_reservations(app):
    engine = app.judge_engine

    assert engine.host_guard.reserved_memory_budget_mb is not None
    assert engine.host_guard.reserved_process_budget is not None
    assert engine.host_guard.reserved_memory_budget_mb >= engine.policy.max_memory_limit_mb
    assert engine.host_guard.reserved_process_budget >= engine.policy.max_processes
    assert engine.host_guard.reserved_memory_mb <= engine.host_guard.reserved_memory_budget_mb
    assert engine.host_guard.reserved_processes <= engine.host_guard.reserved_process_budget
