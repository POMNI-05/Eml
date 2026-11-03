The UI files are:

- client_workspace.py (client_workspace.py:121) — main screens and email selection.
- workspace_panels.py (workspace_panels.py:24) — Gmail connection, AI setup, and drafts.
- workspace.css (assets/workspace.css) — colours, spacing, and styling.


Those collapsible sections are called st.expander. To make any section always visible, replace:

with st.expander("Section name"):
    ...

with:

with st.container():
    ...

Keep the content underneath indented as it is.