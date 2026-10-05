"""LangGraph workflow definition.

normalize -> analyze -> classify -> priority -> actions -> summary -> decide -> [reply] -> finalize
Human approval + sending happen OUTSIDE the graph (reply_service), by design.
"""
from langgraph.graph import END, START, StateGraph

from app.agents import nodes
from app.agents.state import EmailAgentState
from app.ai.llm_base import LLMClient


def build_graph(llm: LLMClient):
    g = StateGraph(EmailAgentState)
    g.add_node("normalize_email", nodes.normalize_email)
    g.add_node("analyze_email", nodes.make_analyze_email(llm))
    g.add_node("classify_email", nodes.classify_email)
    g.add_node("detect_priority", nodes.detect_priority)
    g.add_node("extract_actions", nodes.extract_actions)
    g.add_node("generate_summary", nodes.generate_summary)
    g.add_node("decide_next_action", nodes.decide_next_action)
    g.add_node("generate_reply", nodes.make_generate_reply(llm))
    g.add_node("finalize", nodes.finalize)

    g.add_edge(START, "normalize_email")
    g.add_edge("normalize_email", "analyze_email")
    g.add_conditional_edges("analyze_email", nodes.route_after_analyze,
                            {"classify_email": "classify_email", "finalize": "finalize"})
    g.add_edge("classify_email", "detect_priority")
    g.add_edge("detect_priority", "extract_actions")
    g.add_edge("extract_actions", "generate_summary")
    g.add_edge("generate_summary", "decide_next_action")
    g.add_conditional_edges("decide_next_action", nodes.route_after_decision,
                            {"generate_reply": "generate_reply", "finalize": "finalize"})
    g.add_edge("generate_reply", "finalize")
    g.add_edge("finalize", END)
    return g.compile()
