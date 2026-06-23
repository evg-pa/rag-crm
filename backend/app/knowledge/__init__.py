"""Knowledge package: KnowledgeAgent for auto-generating document summaries and wiki entries."""

from app.knowledge.knowledge_agent import KnowledgeAgent
from app.knowledge.models import WikiEntry
from app.knowledge.wiki_service import WikiService

__all__ = ["KnowledgeAgent", "WikiEntry", "WikiService"]
