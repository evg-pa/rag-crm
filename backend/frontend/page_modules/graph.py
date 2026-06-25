"""Knowledge Graph — interactive Neo4j graph visualization.

Renders entity nodes and relationship edges from the knowledge graph.
Supports click-to-explore: clicking a node shows related entities and documents.
"""

from __future__ import annotations

import streamlit as st

from utils import api


def _render_graph_stats() -> None:
    """Render KPI cards for graph statistics."""
    try:
        stats = api.get_graph_stats()
    except Exception:
        st.warning("Knowledge graph service is not available. Start Neo4j to enable graph features.")
        return

    if not stats.get("connected", False):
        st.info("📊 Knowledge Graph is not connected. Start the Neo4j service to enable graph features.")
        return

    st.subheader("📊 Graph Statistics")

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Entities", stats.get("entities", 0))
    with col2:
        st.metric("Relationships", stats.get("relationships", 0))
    with col3:
        entity_types = stats.get("entity_types", {})
        st.metric("Entity Types", len(entity_types))

    if entity_types:
        st.caption("Entity types distribution:")
        type_items = sorted(entity_types.items(), key=lambda x: x[1], reverse=True)
        cols = st.columns(min(len(type_items), 4))
        for i, (etype, count) in enumerate(type_items):
            with cols[i % len(cols)]:
                st.metric(f"📌 {etype}", count)


def _render_entity_search() -> None:
    """Search entities and display results."""
    st.subheader("🔍 Entity Search")

    col1, col2 = st.columns([3, 1])
    with col1:
        search_term = st.text_input(
            "Search entities",
            placeholder="Enter entity name (person, org, location, concept...)",
            key="graph_entity_search",
            label_visibility="collapsed",
        )
    with col2:
        entity_type_filter = st.selectbox(
            "Filter type",
            options=["All", "PERSON", "ORGANIZATION", "LOCATION", "CONCEPT", "PRODUCT", "EVENT", "DATE", "OTHER"],
            key="graph_entity_type",
            label_visibility="collapsed",
        )

    if search_term:
        etype = None if entity_type_filter == "All" else entity_type_filter
        try:
            result = api.search_graph_entities(search_term, entity_type=etype)
            entities = result.get("entities", [])
        except Exception:
            st.warning("Failed to search entities. Is Neo4j running?")
            return

        if not entities:
            st.info(f"No entities found matching '{search_term}'")
            return

        st.caption(f"Found {len(entities)} entities")

        for ent in entities:
            name = ent.get("name", "?")
            etype_str = ent.get("type", "?")
            eid = ent.get("entity_id", "")
            confidence = ent.get("confidence", 1.0)

            with st.expander(f"📌 **{name}** · _{etype_str}_ ({confidence:.0%})"):
                if eid:
                    _render_entity_subgraph(eid, name)


def _render_entity_subgraph(entity_id: str, entity_name: str) -> None:
    """Render the subgraph for a single entity with its relationships."""
    if st.button(f"🔗 Explore connections", key=f"explore_{entity_id}"):
        with st.spinner(f"Loading subgraph for {entity_name}..."):
            try:
                subgraph = api.get_graph_entity_subgraph(entity_id)
            except Exception:
                st.error("Failed to load entity subgraph.")
                return

        nodes = subgraph.get("nodes", [])
        edges = subgraph.get("edges", [])

        if not nodes:
            st.info("No connections found.")
            return

        st.caption(f"**{entity_name}** is connected to {len(nodes) - 1} entities via {len(edges)} relationships")

        # Render graph as a table (nodes + edges)
        _render_graph_table(nodes, edges, entity_name)


def _render_graph_table(
    nodes: list[dict],
    edges: list[dict],
    center_name: str,
) -> None:
    """Render graph nodes and edges as structured tables."""
    col_nodes, col_edges = st.columns(2)

    with col_nodes:
        st.caption("**Entities (Nodes)**")
        for node in nodes:
            name = node.get("name", "?")
            etype = node.get("type", "?")
            is_center = node.get("is_center", False)
            prefix = "⭐ " if is_center else "• "
            st.markdown(f"{prefix}**{name}** ({etype})")

    with col_edges:
        st.caption("**Relationships (Edges)**")
        for edge in edges:
            source_id = edge.get("source", "")
            target_id = edge.get("target", "")
            rel_type = edge.get("type", "")
            confidence = edge.get("confidence", 1.0)

            # Resolve names from node list
            source_name = "?"
            target_name = "?"
            for n in nodes:
                if n.get("id") == source_id:
                    source_name = n.get("name", "?")
                if n.get("id") == target_id:
                    target_name = n.get("name", "?")

            st.markdown(f"**{source_name}** → `{rel_type}` → **{target_name}**")


def _render_query_expander() -> None:
    """Query expansion tool: expand a query with related entities."""
    st.subheader("🔮 Query Expansion")

    query_text = st.text_area(
        "Enter query text to expand with related knowledge graph entities:",
        placeholder="e.g. 'What does the contract with Acme Corp say about payment terms?'",
        key="kg_query_expand",
        height=80,
    )

    if query_text and st.button("✨ Expand Query", key="kg_expand_btn"):
        with st.spinner("Expanding query..."):
            try:
                result = api.expand_graph_query(query_text)
            except Exception:
                st.warning("Failed to expand query. Is Neo4j running?")
                return

        expanded = result.get("expanded_entities", [])

        if not expanded:
            st.info("No related entities found for this query.")
            return

        st.success(f"Found {len(expanded)} related entities")

        for match in expanded:
            matched_name = match.get("matched_entity", "?")
            matched_type = match.get("matched_type", "?")
            related = match.get("related_entities", [])

            with st.expander(f"📌 **{matched_name}** ({matched_type})"):
                if related:
                    for rel in related:
                        if rel is None:
                            continue
                        r_name = rel.get("name", "?")
                        r_type = rel.get("type", "?")
                        r_rel = rel.get("relationship_type", "RELATED_TO")
                        st.markdown(f"→ `{r_rel}` → **{r_name}** ({r_type})")
                else:
                    st.caption("No related entities found.")


def _render_document_entities() -> None:
    """Show entities extracted from a specific document."""
    st.subheader("📄 Document Entities")

    # List documents as options
    try:
        docs = api.list_documents()
    except Exception:
        st.warning("Backend not available.")
        return

    if not docs:
        st.info("No documents ingested yet. Upload documents to extract entities.")
        return

    doc_options = {f"{d.get('filename', '?')} ({d.get('id', '')[:8]})": d.get("id") for d in docs}
    selected_doc = st.selectbox(
        "Select a document to view its extracted entities:",
        options=list(doc_options.keys()),
        key="kg_doc_select",
    )

    if selected_doc:
        doc_id = doc_options[selected_doc]
        try:
            result = api.get_document_entities(doc_id)
        except Exception:
            st.warning("Failed to load document entities.")
            return

        entities = result.get("entities", [])
        if not entities:
            st.info("No entities extracted from this document yet. Entities are extracted during ingestion.")
            return

        st.caption(f"Found {len(entities)} entities in this document:")
        for ent in entities:
            name = ent.get("name", "?")
            etype = ent.get("type", "?")
            confidence = ent.get("confidence", 1.0)
            st.markdown(f"• **{name}** · _{etype}_ ({confidence:.0%})")


# ── Main render ─────────────────────────────────────────────────────────────

def render() -> None:
    """Render the Knowledge Graph page."""
    st.title("🕸️ Knowledge Graph")

    st.markdown(
        "Explore entities and relationships extracted from your documents. "
        "The knowledge graph enhances search by connecting related concepts across documents."
    )

    # ── Graph stats ─────────────────────────────────────────────────────
    _render_graph_stats()

    st.divider()

    # ── Entity search ───────────────────────────────────────────────────
    _render_entity_search()

    st.divider()

    # ── Query expansion ─────────────────────────────────────────────────
    _render_query_expander()

    st.divider()

    # ── Document entities ───────────────────────────────────────────────
    _render_document_entities()
