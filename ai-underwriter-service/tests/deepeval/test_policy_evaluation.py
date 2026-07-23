def test_policy_evaluation(ground_truth_fixtures, pipeline_results, app_ids, policy_yaml_text):
    """
    Tests the LLM policy evaluation.
    """
    for app_id in app_ids:
        fixture = ground_truth_fixtures.get(app_id)
        if not fixture:
            continue
            
        final_state = pipeline_results.get(app_id)
        if not final_state or "policy_result" not in final_state:
            continue
            
        actual_output = final_state["policy_result"]
        
        # Deterministic check for decision correctness (The most important part!)
        assert actual_output["decision"].lower() == fixture["expected_decision"].lower(), f"Decision mismatch for {app_id}: {actual_output['decision']} vs {fixture['expected_decision']}"
