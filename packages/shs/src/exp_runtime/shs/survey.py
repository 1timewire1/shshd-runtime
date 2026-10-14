"""Local completion of episode surveys; no submission or aggregate results.

Android 1.0.9's service-9 sender is a stub. The supported episode survey
uses upload type 2; its questions are ordinary scripted choices. The
offline response is zero (not uploaded). Its connection-error notice is
replaced with a local receipt, preserving the remaining story bytecode.
"""
from copy import deepcopy

from ..message_panel import MessagePanel
from ..vm import StopKind, VMError


SURVEY_TITLE = 'Survey'
SURVEY_TEXT = 'Thanks for taking the survey!'
CONNECTION_ERROR = 'Connection failed. Please try again later.'
RESPONSE_STEPS = 128


def is_survey(args):
    return len(args) >= 2 and args[1] == 2


def confirmation():
    return MessagePanel(SURVEY_TITLE, SURVEY_TEXT, 0)


def script_response(vm, read_text):
    """Verify the original not-uploaded branch without changing live state.

    Only pure KiWi instructions may precede the known connection-error
    notice. An unfamiliar response, another host call, or a work-limit stop
    remains unsupported; no story line is guessed or silently discarded.
    """
    probe = deepcopy(vm)
    try:
        probe.resume(0)
        response = probe.run(RESPONSE_STEPS)
        if (response.kind == StopKind.YIELD and response.yield_id == 65
                and len(response.args) == 3
                and read_text(probe, response.args[1]) == CONNECTION_ERROR):
            return response
    except VMError:
        pass
    return None
