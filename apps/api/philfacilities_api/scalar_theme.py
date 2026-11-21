"""Scalar API reference theme mapped to the PhilFacilities design system.

The colours mirror the tokens in ``apps/web/src/app/globals.css`` (see also
``docs/design-system.md``): white paper, ``#0a0a0a`` ink, ``#0038a8`` primary
blue, ``#fcd116`` sun accent, ``#d1d8e6`` rules, square corners and the
``#ffcf4a`` focus ring. Dark mode maps the same tokens onto ink surfaces with
sun-yellow actions and a lightened blue for links.

Scalar appends its own theme stylesheet after ``customCss``, so the doubled
selectors below keep these values winning regardless of stylesheet order.
Code blocks get their own surfaces and an accessible syntax palette in both
modes; Scalar's highlighter reads the ``--scalar-code-*`` variables.
"""

CUSTOM_CSS = """
:root:root {
  --scalar-radius: 0px;
  --scalar-border-width: 1px;
}

.light-mode.light-mode {
  /* Paper, ink and rules */
  --scalar-background-1: #ffffff;
  --scalar-background-2: #f4f7fc;
  --scalar-background-3: #e8f1ff;
  --scalar-background-accent: #e8f1ff;
  --scalar-color-1: #0a0a0a;
  --scalar-color-2: #5a5a58;
  --scalar-color-3: #5a5a58;
  --scalar-border-color: #d1d8e6;

  /* Primary blue, sun accent and semantic states */
  --scalar-color-accent: #0038a8;
  --scalar-link-color: #0038a8;
  --scalar-link-color-hover: #002b82;
  --scalar-color-blue: #0038a8;
  --scalar-color-yellow: #fcd116;
  --scalar-color-red: #b42318;
  --scalar-button-1: #0038a8;
  --scalar-button-1-hover: #002b82;
  --scalar-button-1-color: #ffffff;

  /* Document sidebar */
  --scalar-sidebar-background-1: #ffffff;
  --scalar-sidebar-color-1: #0a0a0a;
  --scalar-sidebar-color-2: #5a5a58;
  --scalar-sidebar-color-active: #0038a8;
  --scalar-sidebar-border-color: #d1d8e6;
  --scalar-sidebar-item-hover-background: #f4f7fc;
  --scalar-sidebar-item-hover-color: #0038a8;
  --scalar-sidebar-item-active-background: #e8f1ff;
  --scalar-sidebar-search-background: #f4f7fc;
  --scalar-sidebar-search-border-color: #d1d8e6;
  --scalar-sidebar-search-color: #5a5a58;
  --scalar-sidebar-indent-border: #d1d8e6;
  --scalar-sidebar-indent-border-hover: #0038a8;
  --scalar-sidebar-indent-border-active: #0038a8;

  /* Code blocks */
  --pf-code-bg: #f4f7fc;
  --pf-code-border: #d1d8e6;
  --pf-code-fg: #0a0a0a;
  --scalar-code-keyword: #8250df;
  --scalar-code-function: #b45309;
  --scalar-code-number: #b45309;
  --scalar-code-string: #1a7f37;
  --scalar-code-builtin: #0550ae;
  --scalar-code-type: #8250df;
  --scalar-code-parameter: #0a0a0a;
  --scalar-code-property: #0a0a0a;
  --scalar-code-comment: #5a5a58;
  --scalar-code-punctuation: #5a5a58;
}

.dark-mode.dark-mode {
  /* Ink surfaces, paper-coloured text */
  --scalar-background-1: #0a0a0a;
  --scalar-background-2: #1a1a1a;
  --scalar-background-3: #262626;
  --scalar-background-accent: #fcd1161a;
  --scalar-color-1: #f5f5f5;
  --scalar-color-2: #bdbdbb;
  --scalar-color-3: #8d8d8b;
  --scalar-border-color: #363636;

  /* Sun actions and a readable light blue for links */
  --scalar-color-accent: #8fb8ff;
  --scalar-link-color: #8fb8ff;
  --scalar-link-color-hover: #b9d2ff;
  --scalar-color-blue: #8fb8ff;
  --scalar-color-yellow: #fcd116;
  --scalar-color-red: #ff7b72;
  --scalar-button-1: #fcd116;
  --scalar-button-1-hover: #e5bd14;
  --scalar-button-1-color: #0a0a0a;

  /* Document sidebar */
  --scalar-sidebar-background-1: #0a0a0a;
  --scalar-sidebar-color-1: #f5f5f5;
  --scalar-sidebar-color-2: #bdbdbb;
  --scalar-sidebar-color-active: #fcd116;
  --scalar-sidebar-border-color: #363636;
  --scalar-sidebar-item-hover-background: #1a1a1a;
  --scalar-sidebar-item-hover-color: #fcd116;
  --scalar-sidebar-item-active-background: #262626;
  --scalar-sidebar-search-background: #1a1a1a;
  --scalar-sidebar-search-border-color: #363636;
  --scalar-sidebar-search-color: #bdbdbb;
  --scalar-sidebar-indent-border: #363636;
  --scalar-sidebar-indent-border-hover: #fcd116;
  --scalar-sidebar-indent-border-active: #fcd116;

  /* Code blocks */
  --pf-code-bg: #2b2b2b;
  --pf-code-border: #3d3d3d;
  --pf-code-fg: #e6e6e6;
  --scalar-code-keyword: #d2a8ff;
  --scalar-code-function: #f0883e;
  --scalar-code-number: #f0883e;
  --scalar-code-string: #7ee787;
  --scalar-code-builtin: #79c0ff;
  --scalar-code-type: #d2a8ff;
  --scalar-code-parameter: #e6e6e6;
  --scalar-code-property: #e6e6e6;
  --scalar-code-comment: #6a9955;
  --scalar-code-punctuation: #c9d1d9;
}

/* Code samples and fenced code share the same surface in both modes. */
.scalar-app .scalar-code-block,
.scalar-app .markdown pre,
.scalar-app .scalar-markdown pre {
  background: var(--pf-code-bg);
  border: 1px solid var(--pf-code-border);
  color: var(--pf-code-fg);
}

.scalar-code-block-pre {
  color: var(--pf-code-fg);
}

/* The measured product focus ring, visible on paper and on ink. */
.light-mode.light-mode :focus-visible,
.dark-mode.dark-mode :focus-visible {
  outline: 3px solid #ffcf4a;
  outline-offset: 3px;
}
"""
