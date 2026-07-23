from deepeval import assert_test
from deepeval.metrics import GEval
from deepeval.test_case import LLMTestCase, LLMTestCaseParams

def test_rationale_quality(ground_truth_fixtures, pipeline_results, app_ids):
    """
    Evaluate the quality of the generated rationale text using GEval.
    """
    rationale_quality = GEval(
        name="Rationale Quality",
        criteria=(
            "Evaluate the quality of the underwriting rationale: "
            "1) Does it cite specific rule IDs (e.g., D1_CREDIT_SCORE, R2_FOIR)? "
            "2) Does it reference actual financial figures (credit score, FOIR %, income)? "
            "3) Is it 2-4 sentences, professional, and clear? "
            "4) Is the rationale consistent with the stated decision? "
            "5) Are currency values in INR format? "
            "Score 1.0 if all criteria met, scale down for each violation."
        ),
        evaluation_params=[
            LLMTestCaseParams.INPUT,
            LLMTestCaseParams.ACTUAL_OUTPUT,
        ],
        threshold=0.3,
    )
    
    test_cases = []
    
    for app_id in app_ids:
        fixture = ground_truth_fixtures.get(app_id)
        if not fixture:
            continue
            
        final_state = pipeline_results.get(app_id)
        if not final_state or "decision" not in final_state:
            continue
            
        # The rationale shouldn't be judged on the document, but on the decision it justifies.
        # Input: Metrics and policy result
        metrics = final_state.get("metrics", {})
        policy_result = final_state.get("policy_result", {})
        input_text = f"METRICS: {metrics}\nPOLICY_RESULT: {policy_result}"
        
        # Output: Rationale text
        rationale_text = final_state.get("decision", {}).get("rationale_text", "")
        
        test_case = LLMTestCase(
            input=input_text,
            actual_output=rationale_text,
            name=f"Rationale Quality - {app_id}"
        )
        test_cases.append(test_case)

    for test_case in test_cases:
        assert_test(test_case, [rationale_quality])
