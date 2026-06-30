"""Neo4j Knowledge Graph — entity/relationship extraction and graph-enhanced search.

Module layout:
- driver.py       — Neo4j async driver singleton, connection management
- graph_service.py — entity CRUD, relationship storage, graph queries
- entity_extractor.py — LLM-based entity extraction from document text
- relationship_extractor.py — LLM inference + co-occurrence analysis
- graph_agent.py   — LangGraph node: graph-enhanced search / query expansion
"""

from app.knowledge_graph.driver import (
    check_neo4j_connection,
    close_neo4j_driver,
    get_neo4j_driver,
)
from app.knowledge_graph.graph_service import GraphService

__all__ = [
    "get_neo4j_driver",
    "check_neo4j_connection",
    "close_neo4j_driver",
    "GraphService",
]
