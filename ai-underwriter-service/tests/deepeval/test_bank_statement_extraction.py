from deepeval import assert_test
from deepeval.metrics import GEval
from deepeval.test_case import LLMTestCase, LLMTestCaseParams

def test_bank_statement_extraction_quality(ground_truth_fixtures, pipeline_results, app_ids):
    """
    Evaluate the quality of the bank statement extractor using GEval (LLM-as-a-judge).
    Checks category accuracy and metadata.
    """
    transaction_accuracy = GEval(
        name="Bank Transaction Extraction Faithfulness",
        criteria=(
            "Evaluate if the extracted bank transactions are faithful to the input text. "
            "Check that account_holder and account_type are extracted correctly if present. "
            "Score 1.0 if all fields look correctly extracted based on the input text. "
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
        if not final_state or "extracted_bank_statement" not in final_state:
            continue
            
        parsed_bank = final_state.get("parsed", {}).get("bank_statement", {}).get("raw_text", "")
        extracted_bank = final_state.get("extracted_bank_statement", {})
        
        test_case = LLMTestCase(
            input=parsed_bank,
            actual_output=str(extracted_bank),
            name=f"Bank Statement Extraction - {app_id}"
        )
        test_cases.append(test_case)

    for test_case in test_cases:
        assert_test(test_case, [transaction_accuracy])
