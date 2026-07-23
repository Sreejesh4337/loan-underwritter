from deepeval import assert_test
from deepeval.metrics import GEval
from deepeval.test_case import LLMTestCase, LLMTestCaseParams

def test_kyc_extraction_quality(ground_truth_fixtures, pipeline_results, app_ids):
    """
    Evaluate the quality of the KYC extractor using GEval (LLM-as-a-judge).
    Checks if the structured JSON matches the document facts exactly.
    """
    # Define the metric
    extraction_accuracy = GEval(
        name="KYC Extraction Faithfulness",
        criteria=(
            "Evaluate if the extracted KYC JSON accurately matches the facts in the input document text. "
            "Score 1.0 if the extracted fields are present in the text and not hallucinated. "
            "Score 0.0 if there are blatant hallucinations."
        ),
        evaluation_params=[
            LLMTestCaseParams.INPUT,
            LLMTestCaseParams.ACTUAL_OUTPUT,
        ],
        threshold=0.0,
    )
    
    test_cases = []
    
    for app_id in app_ids:
        fixture = ground_truth_fixtures.get(app_id)
        if not fixture:
            continue
            
        final_state = pipeline_results.get(app_id)
        if not final_state or "extracted_kyc" not in final_state:
            continue
            
        # The input is the raw parsed document text
        parsed_kyc = final_state.get("parsed", {}).get("kyc", {}).get("raw_text", "")
        
        # The actual output is the LLM-extracted structured JSON
        extracted_kyc = final_state.get("extracted_kyc", {})
        
        test_case = LLMTestCase(
            input=parsed_kyc,
            actual_output=str(extracted_kyc),
            name=f"KYC Extraction - {app_id}"
        )
        test_cases.append(test_case)

    # Run the evaluation for all test cases
    for test_case in test_cases:
        assert_test(test_case, [extraction_accuracy])
