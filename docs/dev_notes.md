The UI files are:

- eml_ui/client_workspace.py (eml_ui/client_workspace.py:121) — main screens and email selection.
- eml_ui/workspace_panels.py (eml_ui/workspace_panels.py:24) — Gmail connection, AI setup, and drafts.
- workspace.css (assets/workspace.css) — colours, spacing, and styling.


Those collapsible sections are called st.expander. To make any section always visible, replace:

with st.expander("Section name"):
    ...

with:

with st.container():
    ...

Keep the content underneath indented as it is.