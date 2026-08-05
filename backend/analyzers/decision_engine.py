def decide_action(
    complexity,
    needs_assistance,
    dwell_time
):
    if needs_assistance:

        return {
            "action": "tooltip"
        }

    return {
        "action": "none"
    }