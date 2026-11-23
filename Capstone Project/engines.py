"""
engines.py - the four engines, by name

An engine is a module with a NAME and a run(email) function (see pipeline.py).
They are loaded only when asked for, so a script that uses one framework does not have to import the others.
"""

import importlib

ENGINES = {
    "plain": "engine_plain",           # the hand-built agent loop from Modules 02 to 05
    "sdk": "capstone_sdk",             # OpenAI Agents SDK
    "langgraph": "capstone_langgraph",
    "crewai": "capstone_crewai",
}


def load(name):
    """Import an engine by its short name."""
    if name not in ENGINES:
        raise SystemExit("Unknown engine '" + name + "'. Choose one of: " + ", ".join(ENGINES.keys()))
    return importlib.import_module(ENGINES[name])
