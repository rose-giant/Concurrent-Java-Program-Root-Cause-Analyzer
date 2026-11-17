def classify_result(jpf_result, jpf_details):
    """Verbatim from CONCUR's analyze_code.py -- maps raw JPF output text
    into the paper's Table 1 error taxonomy (DL/RC/SV/UE/NEM/ST/TE/Pass/
    Compilation Errors)."""
    if not jpf_result or (isinstance(jpf_result, list) and len(jpf_result) == 0):
        return "Termination Error"

    first_result = jpf_result[0] if isinstance(jpf_result, list) else jpf_result

    first_detail = ""
    if jpf_details:
        if isinstance(jpf_details, list) and len(jpf_details) > 0:
            first_detail = jpf_details[0]
        elif isinstance(jpf_details, str):
            first_detail = jpf_details

    if "nullpointerexception" in first_result.lower():
        return "Uncaught Exception"

    if "syntax error" in first_result.lower():
        return "Compilation Errors"

    if "no static entry method" in first_result.lower():
        return "No Entry Method"

    if "deadlock" in first_result.lower():
        return "Deadlock"

    has_results = "====================================================== results" in first_result or \
                  "====================================================== results" in first_detail

    if not has_results:
        return "Termination Error"

    if "preciseracedetector" in first_result.lower():
        if first_detail and "waiting proportion: 100.00%" in first_detail.lower():
            return "Starvation"
        return "Race Condition"

    if "no errors detected" in first_result.lower():
        if first_detail:
            if "unique logical threads created during execution: 1" in first_detail.lower():
                return "Single Thread"
            if "waiting proportion: 100.00%" in first_detail.lower():
                return "Starvation"
        return "Pass"

    return "Uncaught Exception"
