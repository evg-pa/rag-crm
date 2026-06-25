"""Knowledge Graph visualization page — explore entities and relationships.

Features:
- Graph statistics overview (entity/relationship counts, types)
- Entity search with type filter
- Interactive subgraph visualization
- Document entity explorer
- Query expansion demo
"""

from __future__ import annotations

import streamlit as st

from utils import api, state


def _format_count(n: int) -> str:
    """Format a count nicely."""
    if n >= 1000:
        return f"{n:,}"
    return str(n)


def _entity_type_color(entity_type: str) -> str:
    """Return a consistent colour for each entity type."""
    colors = {
        "PERSON": "#4A90D9",
        "ORGANIZATION": "#E67E22",
        "LOCATION": "#2ECC71",
        "CONCEPT": "#9B59B6",
        "PRODUCT": "#E74C3C",
        "EVENT": "#1ABC9C",
        "DATE": "#95A5A6",
        "OTHER": "#7F8C8D",
    }
    return colors.get(entity_type, "#7F8C8D")


def _render_graph_stats() -> None:
    """Render the knowledge graph stats overview section."""
    st.subheader("📊 Graph Overview")

    try:
        stats = api.get_graph_stats()
    except Exception:
        st.warning("Neo4j is not available. Start the service to see graph data.")
        return

    connected = stats.get("connected", False)
    if not connected:
        st.info("No entities extracted yet. Upload documents to populate the knowledge graph.")
        return

    col1, col2, col3 = st.columns(3)
    col1.metric("Entities", _format_count(stats.get("entities", 0)))
    col2.metric("Relationships", _format_count(stats.get("relationships", 0)))
    col3.metric("Entity Types", _format_count(len(stats.get("entity_types", {}))))

    # Entity type breakdown
    entity_types = stats.get("entity_types", {})
    if entity_types:
        st.subheader("Entity Type Breakdown")
        cols = st.columns(len(entity_types))
        for i, (etype, count) in enumerate(entity_types.items()):
            with cols[i]:
                st.metric(
                    etype,
                    _format_count(count),
                    delta=None,
                )


def _render_entity_search() -> None:
    """Render entity search with type filter."""
    st.subheader("🔍 Search Entities")

    col1, col2 = st.columns([3, 1])
    with col1:
        search_term = st.text_input(
            "Entity name",
            placeholder="e.g., Google, John Smith, New York...",
            key="kg_entity_search",
        )
    with col2:
        entity_type = st.selectbox(
            "Type filter",
            options=["All", "PERSON", "ORGANIZATION", "LOCATION", "CONCEPT", "PRODUCT", "EVENT", "DATE", "OTHER"],
            index=0,
            key="kg_entity_type",
        )

    if search_term:
        try:
            type_filter = None if entity_type == "All" else entity_type
            result = api.search_graph_entities(search_term, entity_type=type_filter, limit=20)
        except Exception:
            st.warning("Neo4j is not available.")
            return

        entities = result.get("results", [])
        count = result.get("count", 0)

        st.caption(f"Found {count} matching entit{'y' if count == 1 else 'ies'}")

        for ent in entities:
            ent_id = ent.get("entity_id", "")
            name = ent.get("name", "Unknown")
            ent_type = ent.get("type", "OTHER")
            color = _entity_type_color(ent_type)

            with st.container():
                c1, c2 = st.columns([4, 1])
                with c1:
                    st.markdown(
                        f"**{name}** &nbsp; <span style='color:{color};font-size:0.8em;'>[{ent_type}]</span>",
                        unsafe_allow_html=True,
                    )
                    st.caption(f"ID: `{ent_id}`")
                with c2:
                    if st.button("🔗 Explore", key=f"explore_{ent_id}"):
                        st.session_state.kg_selected_entity = ent_id
                        st.session_state.kg_selected_name = name
                        st.rerun()


def _render_subgraph() -> None:
    """Render interactive subgraph visualization for a selected entity."""
    selected_id = st.session_state.get("kg_selected_entity", "")
    selected_name = st.session_state.get("kg_selected_name", "")

    if not selected_id:
        st.info("Search for an entity and click **Explore** to see its subgraph.")
        return

    st.subheader(f"🔗 Subgraph: {selected_name}")

    depth = st.slider("Depth", 1, 4, 2, key="kg_subgraph_depth")

    try:
        subgraph = api.get_graph_entity_subgraph(selected_id, depth=depth)
    except Exception:
        st.warning("Neo4j is not available.")
        return

    nodes = subgraph.get("nodes", [])
    edges_list = subgraph.get("edges", [])

    st.caption(
        f"Showing {len(nodes)} nodes and {len(edges_list)} edges "
        f"within depth {depth}"
    )

    if nodes:
        # Build HTML table for nodes
        st.markdown("#### Nodes")
        node_rows = []
        for n in nodes:
            color = _entity_type_color(n.get("type", "OTHER"))
            label = "⭐ " if n.get("is_center") else ""
            node_rows.append(
                f"<tr><td>{label}<b>{n.get('name', '?')}</b></td>"
                f"<td><span style='color:{color}'>[{n.get('type', '?')}]</span></td></tr>"
            )

        st.markdown(
            "<table style='width:100%'>" + "".join(node_rows) + "</table>",
            unsafe_allow_html=True,
        )

        # Build HTML for edges
        if edges_list:
            st.markdown("#### Relationships")
            edge_rows = []
            for e in edges_list:
                source = e.get("source", "?")
                target = e.get("target", "?")
                rel_type = e.get("type", "RELATED_TO")
                conf = e.get("confidence", 1.0)
                edge_rows.append(
                    f"<tr><td><code>{source[:8]}...</code></td>"
                    f"<td style='text-align:center'>→ <b>{rel_type}</b> →</td>"
                    f"<td><code>{target[:8]}...</code></td>"
                    f"<td style='text-align:right'>{(conf*100):.0f}%</td></tr>"
                )
            st.markdown(
                "<table style='width:100%'>" + "".join(edge_rows) + "</table>",
                unsafe_allow_html=True,
            )
    else:
        st.info("No subgraph data available for this entity.")


def _render_document_entities() -> None:
    """Render entity list for a selected document."""
    st.subheader("📄 Document Entities")

    try:
        docs = api.list_documents()
    except Exception:
        st.warning("Backend not available.")
        return

    if not docs:
        st.info("No documents ingested yet.")
        return

    doc_options = {d["filename"]: d["id"] for d in docs if isinstance(d, dict)}
    selected_doc = st.selectbox(
        "Select document",
        options=list(doc_options.keys()),
        key="kg_doc_select",
    )

    if selected_doc:
        doc_id = doc_options[selected_doc]
        try:
            result = api.get_document_entities(doc_id)
        except Exception:
            st.warning("Neo4j is not available.")
            return

        entities = result.get("entities", [])
        count = result.get("total", 0)

        st.caption(f"Extracted {count} entities from this document")

        if entities:
            for ent in entities:
                name = ent.get("name", "?")
                ent_type = ent.get("type", "OTHER")
                color = _entity_type_color(ent_type)
                st.markdown(
                    f"- **{name}** <span style='color:{color};font-size:0.8em;'>[{ent_type}]</span>",
                    unsafe_allow_html=True,
                )
        else:
            st.info("No entities extracted for this document. Knowledge graph extraction runs after document upload.")


def _render_query_expansion() -> None:
    """Render query expansion demo."""
    st.subheader("🔮 Query Expansion")

    query = st.text_input(
        "Enter a query to expand with related entities",
        placeholder="e.g., artificial intelligence...",
        key="kg_query_expand",
    )

    if query:
        try:
            result = api.expand_graph_query(query)
        except Exception:
            st.warning("Neo4j is not available.")
            return

        expanded = result.get("expanded_entities", [])
        count = result.get("total", 0)

        if count > 0:
            st.success(f"Query expanded with {count} related entities")

            for ent in expanded:
                name = ent.get("matched_entity", "?")
                ent_type = ent.get("matched_type", "?")
                color = _entity_type_color(ent_type)

                st.markdown(f"#### {name} <span style='color:{color};font-size:0.8em;'>[{ent_type}]</span>", unsafe_allow_html=True)

                related = ent.get("related_entities", [])
                if related:
                    for rel in related:
                        if rel and isinstance(rel, dict):
                            rname = rel.get("name", "?")
                            rtype = rel.get("type", "?")
                            rrel = rel.get("relationship_type", "?")
                            st.markdown(f"  - {rname} [{rtype}] — *{rrel}*")
        else:
            st.info("No related entities found in the knowledge graph.")


def render() -> None:
    """Render the knowledge graph page."""
    st.title("🧠 Knowledge Graph")
    st.caption("Explore entities and relationships extracted from your documents")

    # Tabs for different views
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "📊 Overview",
        "🔍 Search Entities",
        "🔗 Subgraph Explorer",
        "📄 Document Entities",
        "🔮 Query Expansion",
    ])

    with tab1:
        _render_graph_stats()

    with tab2:
        _render_entity_search()

    with tab3:
        _render_subgraph()

    with tab4:
        _render_document_entities()

    with tab5:
        _render_query_expansion()
