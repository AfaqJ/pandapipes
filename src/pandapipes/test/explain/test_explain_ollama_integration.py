# Copyright (c) 2020-2026 by Fraunhofer Institute for Energy Economics
# and Energy System Technology (IEE), Kassel, and University of Kassel. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be found in the LICENSE file.

import os
import re

import pytest

from pandapipes.explain.core.config import get_config
from pandapipes.explain.llm import client as llm_client
from pandapipes.explain.llm import prompt as llm_prompt
from pandapipes.test.explain.test_explain_diagnostic_scenarios import SCENARIOS, _context_for

pytestmark = pytest.mark.skipif(
    os.environ.get("PANDAPIPES_EXPLAIN_RUN_OLLAMA") != "1",
    reason="Set PANDAPIPES_EXPLAIN_RUN_OLLAMA=1 to run slow local Ollama integration tests.",
)


def _needle_terms(expected):
    match = re.search(r"net\.([a-z_]+)\.loc\[[^]]+], '([^']+)']", expected)
    if match:
        return [match.group(1), match.group(2)]
    if "no fluid" in expected:
        return ["fluid"]
    if "ext_grid is empty" in expected:
        return ["ext_grid"]
    if "unsupplied junctions" in expected:
        return ["unsupplied", "ext_grid"]
    return [expected.split()[0]]


@pytest.mark.parametrize("name, factory, expected", SCENARIOS)
def test_ollama_response_mentions_specific_root_cause(name, factory, expected):
    if not llm_client.is_available():
        pytest.skip("Ollama server is not reachable.")

    configured_model = os.environ.get("PANDAPIPES_EXPLAIN_OLLAMA_MODEL")
    if configured_model:
        get_config().model = configured_model

    diagnostics, prompt_context = _context_for(factory())
    assert expected in prompt_context

    cfg = get_config()
    messages = [
        {
            "role": "system",
            "content": llm_prompt._SYSTEM,
        },
        {
            "role": "user",
            "content": prompt_context,
        },
    ]
    response = llm_client.chat(messages)
    assert response, f"Ollama model {cfg.model!r} returned no response for {name}"

    lowered = response.lower()
    missing = [term for term in _needle_terms(expected) if term.lower() not in lowered]
    assert not missing, f"{name}: missing {missing} in response:\n{response}\n\nDiagnostics:\n{diagnostics}"
