"""LangGraph construction — wires all agent nodes into a review pipeline graph."""

from __future__ import annotations

import logging

from langgraph.graph import StateGraph, END

from review_agent.agents.state import ReviewState
from review_agent.agents.triage import triage_node
from review_agent.agents.bug_detector import bug_detector_node
from review_agent.agents.security_scanner import security_scanner_node
from review_agent.agents.smell_detector import smell_detector_node
from review_agent.agents.fix_suggester import fix_suggester_node
from review_agent.agents.aggregator import aggregator_node

logger = logging.getLogger(__name__)


def _should_run_security(state: ReviewState) -> str:
    """Conditional edge: route to security scan or skip."""
    return "skip" if state.get("skip_security", False) else "run"


def _should_run_smell(state: ReviewState) -> str:
    """Conditional edge: route to smell scan or skip."""
    return "skip" if state.get("skip_smell", False) else "run"


def _noop_security(state: ReviewState) -> ReviewState:
    return {**state, "security_findings": []}


def _noop_smell(state: ReviewState) -> ReviewState:
    return {**state, "smell_findings": []}


def build_graph() -> StateGraph:
    """Build and compile the LangGraph review pipeline."""
    workflow = StateGraph(ReviewState)

    # Register nodes
    workflow.add_node("triage", triage_node)
    workflow.add_node("bug_detector", bug_detector_node)
    workflow.add_node("security_scanner", security_scanner_node)
    workflow.add_node("security_skip", _noop_security)
    workflow.add_node("smell_detector", smell_detector_node)
    workflow.add_node("smell_skip", _noop_smell)
    workflow.add_node("fix_suggester", fix_suggester_node)
    workflow.add_node("aggregator", aggregator_node)

    # Set entrypoint
    workflow.set_entry_point("triage")

    # Triage fans out to all three analysis nodes
    workflow.add_edge("triage", "bug_detector")

    # Conditional edges for security
    workflow.add_conditional_edges(
        "triage",
        _should_run_security,
        {"run": "security_scanner", "skip": "security_skip"},
    )

    # Conditional edges for smell
    workflow.add_conditional_edges(
        "triage",
        _should_run_smell,
        {"run": "smell_detector", "skip": "smell_skip"},
    )

    # All three (or their skips) fan into fix_suggester
    workflow.add_edge("bug_detector", "fix_suggester")
    workflow.add_edge("security_scanner", "fix_suggester")
    workflow.add_edge("security_skip", "fix_suggester")
    workflow.add_edge("smell_detector", "fix_suggester")
    workflow.add_edge("smell_skip", "fix_suggester")

    # Fix suggester → aggregator → END
    workflow.add_edge("fix_suggester", "aggregator")
    workflow.add_edge("aggregator", END)

    return workflow.compile()
