"""LangGraph multi-agent retrieval pipeline.

Seven specialised agents orchestrated through LangGraph:

1. RouterAgent   — classifies query type
2. RetrieverAgent — executes chosen search strategy
3. RerankerAgent  — re-ranks top-20 candidates
4. AnswerAgent   — builds prompt, calls LLM
5. CriticAgent    — validates answer, catches hallucinations (max 2 retries)
6. MemoryAgent    — stores/retrieves last 5 exchanges per session
7. SynthesizerAgent — produces final polished response
"""

from app.agents.state_graph import build_qa_graph
from app.agents.state import AgentState
from app.agents.memory_agent import clear_all as _clear_memory_store

__all__ = ["AgentState", "build_qa_graph", "_clear_memory_store"]
