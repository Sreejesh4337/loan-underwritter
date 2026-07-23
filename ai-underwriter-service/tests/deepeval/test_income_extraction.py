from deepeval import assert_test
from deepeval.metrics import GEval
from deepeval.test_case import LLMTestCase, LLMTestCaseParams

def test_income_extraction_quality(ground_truth_fixtures, pipeline_results, app_ids):
    """
    Evaluate the quality of the income extractor using GEval (LLM-as-a-judge).
    """
    income_accuracy = GEval(
        name="Income Extraction Faithfulness",
        criteria=(
            "Evaluate if the extracted income JSON accurately matches the facts in the input document text. "
            "Score 1.0 if the extracted fields are present in the text and not hallucinated. "
            "Score 0.0 if there are blatant hallucinations."
        ),
        evaluation_params=[
            LLMTestCaseParams.INPUT,
            LLMTestCaseParams.ACTUAL_OUTPUT,
        ],
        threshold=0.8,
    )
    
    test_cases = []
    
    for app_id in app_ids:
        fixture = ground_truth_fixtures.get(app_id)
        if not fixture:
            continue
            
        final_state = pipeline_results.get(app_id)
        if not final_state or "extracted_income" not in final_state:
            continue
            
        # For the income doc we reconstructed a string in the code, but we can pass the raw parsed here
        parsed_income = final_state.get("parsed", {}).get("income", {})
        input_text = str(parsed_income)
        
        extracted_income = final_state.get("extracted_income", {})
        test_case = LLMTestCase(
            input=input_text,
            actual_output=str(extracted_income),
            name=f"Income Extraction - {app_id}"
        )
        test_cases.append(test_case)

    for test_case in test_cases:
        assert_test(test_case, [income_accuracy])
