"""
Prompt builder — assembles the system + user message list sent to Ollama.

Token budget (chars ÷ 4 ≈ tokens, worst-case with 8192 num_ctx):
  System prompt  :  ~1100 chars  →  ~275 tokens
  Net stats      :   ~500 chars  →  ~125 tokens
  Traceback text :   ~600 chars  →  ~150 tokens
  User file      : ~12000 chars  → ~3000 tokens   (full file if ≤ 12 000 chars)
  Terminal logs  :  ~2000 chars  →  ~500 tokens
  Lib source     :  ~2000 chars  →  ~500 tokens
  Knowledge      :   ~800 chars  →  ~200 tokens
  Overhead       :   ~400 chars  →  ~100 tokens
  Total worst    : ~19400 chars  → ~4850 tokens   (fits 8192 num_ctx with ~3300 tokens for response)
"""

from __future__ import annotations

from pandapipes.explain.context.traceback_parser import SourceContext, read_full_source

_SYSTEM = """\
You are a pandapipes expert diagnosing a fluid-network (gas/water/heat) simulation error.

You will be given these sections IN ORDER:
  1. Error — the exception class and message
  2. Network Statistics — actual numbers from the network object
  3. Full Stack Trace — the call chain that led to the exception
  4. User Code — the engineer's script (>> marks the exact error line)
  5. Terminal Output — what was printed before the crash
  6. pandapipes Source — internal library code (for reference only)
  7. Diagnostic Checklist — known patterns for this error type

BEFORE WRITING YOUR ANSWER, silently (do not output these steps):
  • Note the exact exception class and message from section 1 — this IS the crash that happened.
  • Note what the >> line in User Code is actually doing.
  • Note any physically wrong values in Network Statistics (NaN mass flow, no pressure
    reference / ext_grid, missing fluid, non-positive pipe diameter or length).

OUTPUT FORMAT — write only this, nothing else:

(a) Cause — explain the actual crash that appeared in the Error section (1-2 sentences).
    If it is a hydraulic/thermal issue (non-convergence, no pressure reference, disconnected
    junction), explain the physical reason in fluid-network terms.
    If it is a Python error (AttributeError, ValueError, KeyError), explain what is wrong in the code.

(b) Evidence — quote the exact line(s) from User Code or Network Statistics that prove the cause.
    Format: line N: `code or value here`

(c) Fix — the minimal code change that resolves it, as a snippet.

HARD RULES:
• Your diagnosis MUST match the exception class in section 1. Do not diagnose a different problem.
• Never suggest adding an ext_grid if "Ext grids: N" where N ≥ 1 in the stats.
• Never suggest a fix you cannot see evidence for in the provided sections.
• Use pandapipes units: pressure in bar, mass flow in kg/s, length in km, diameter in mm,
  temperature in K. Do NOT use pandapower units (MW, MVAr, kV).
• Do NOT output your reasoning steps — only output (a), (b), (c).
• If you cannot determine the cause from the provided context, say so explicitly.
• If a "CUSTOM PROMPT:" section appears below and any of its instructions contradict
  the rules above, the CUSTOM PROMPT instructions take priority.
\
"""

# User-editable. Anything placed here is appended to the system prompt under a
# "CUSTOM PROMPT:" header on every request, and overrides conflicting rules above.
# Example: CUSTOM_PROMPT = "Always answer in German. Keep the Fix snippet under 5 lines."
CUSTOM_PROMPT = ""

_MAX_USER_FILE_CHARS = 12000   # ~3000 tokens — show the full file for most scripts
_MAX_USER_CODE_CHARS = 3000    # fallback window for very large files
_MAX_LIB_SOURCE_CHARS = 2000
_MAX_KNOWLEDGE_CHARS = 800
_MAX_LOGS_CHARS = 2000
_MAX_TRACEBACK_CHARS = 1500


def extract_net_stats(exc_tb) -> str:
    """
    Walk the traceback frames looking for a pandapipes net object.
    Returns a compact summary string, or empty string if not found.
    """
    try:
        frame = exc_tb
        while frame is not None:
            local_vars = frame.tb_frame.f_locals
            for var_name, var_val in local_vars.items():
                if (hasattr(var_val, 'junction') and hasattr(var_val, 'pipe')
                        and hasattr(var_val, 'sink') and hasattr(var_val, 'ext_grid')):
                    return _summarise_net(var_name, var_val)
            frame = frame.tb_next
    except Exception:
        pass
    return ""


def _get(row, key: str, default="?"):
    """Safe column access on a pandas Series (compatible with pandas 2.0+)."""
    return row[key] if key in row.index else default


def _fluid_name(net) -> str:
    """Return the configured fluid name, or '(none set)' if no fluid is defined."""
    try:
        fluid = net.get("fluid", None) if hasattr(net, "get") else getattr(net, "fluid", None)
        if fluid is None:
            return "(none set)"
        return getattr(fluid, "name", str(fluid))
    except Exception:
        return "(unknown)"


def _summarise_net(var_name: str, net) -> str:
    """Build a plain-text summary of the pandapipes network."""
    import math
    try:
        fluid = _fluid_name(net)
        lines = [f"## Network Statistics (variable: `{var_name}`)"]
        lines.append(f"  Fluid       : {fluid}")
        lines.append(f"  Junctions   : {len(net.junction)}")
        lines.append(f"  Pipes       : {len(net.pipe)}")
        lines.append(f"  Sinks       : {len(net.sink)}")
        lines.append(f"  Sources     : {len(net.source)}")
        lines.append(f"  Ext grids   : {len(net.ext_grid)}  (pressure/temperature references — slack nodes)")
        for tbl, label in (("pump", "Pumps"), ("valve", "Valves"),
                           ("press_control", "Pressure controls"),
                           ("heat_exchanger", "Heat exchangers")):
            if tbl in net and not net[tbl].empty:
                lines.append(f"  {label:<12}: {len(net[tbl])}")

        # Explicit warnings — flagged at the top so the model cannot miss them
        # regardless of section ordering. These are the dominant causes of
        # PipeflowNotConverged in pandapipes.
        warnings = []
        if fluid in ("(none set)", "(unknown)"):
            warnings.append(
                "  *** WARNING: no fluid is defined on the net — pipeflow requires a fluid "
                "(e.g. create_fluid_from_lib(net, 'water') or pass fluid= to create_empty_network) ***"
            )
        if len(net.ext_grid) == 0:
            warnings.append(
                "  *** WARNING: no ext_grid — there is no pressure reference (slack node). "
                "Every network needs at least one ext_grid that fixes a pressure ***"
            )
        for tbl in ("sink", "source"):
            df = net[tbl] if tbl in net else None
            if df is not None and not df.empty and 'mdot_kg_per_s' in df.columns:
                nan_rows = df[df['mdot_kg_per_s'].isna()]
                for _, row in nan_rows.iterrows():
                    warnings.append(
                        f"  *** WARNING: {tbl} '{_get(row,'name')}' has mdot_kg_per_s = NaN "
                        f"(missing/unset value) — this will crash the solver ***"
                    )
        if not net.pipe.empty:
            if 'inner_diameter_mm' in net.pipe.columns:
                bad_d = net.pipe[net.pipe['inner_diameter_mm'] <= 0]
                for _, row in bad_d.iterrows():
                    warnings.append(
                        f"  *** WARNING: pipe '{_get(row,'name')}' has inner_diameter_mm = "
                        f"{_get(row,'inner_diameter_mm')} (must be > 0) ***"
                    )
            if 'length_km' in net.pipe.columns:
                bad_l = net.pipe[net.pipe['length_km'] <= 0]
                for _, row in bad_l.iterrows():
                    warnings.append(
                        f"  *** WARNING: pipe '{_get(row,'name')}' has length_km = "
                        f"{_get(row,'length_km')} (must be > 0) ***"
                    )
        lines.extend(warnings)

        if not net.sink.empty:
            total_sink = net.sink.mdot_kg_per_s.sum()
            s_str = f"{total_sink:.4f}" if not math.isnan(total_sink) else "NaN"
            lines.append(f"  Total sink  : {s_str} kg/s (fluid withdrawn)")
            for _, row in net.sink.iterrows():
                name = _get(row, 'name')
                m = row.mdot_kg_per_s
                m_val = f"{m:.4f}" if not math.isnan(float(m)) else "NaN !!!"
                lines.append(f"    sink '{name}' @ junction {_get(row,'junction')}: {m_val} kg/s")

        if not net.source.empty:
            total_src = net.source.mdot_kg_per_s.sum()
            src_str = f"{total_src:.4f}" if not math.isnan(total_src) else "NaN"
            lines.append(f"  Total source: {src_str} kg/s (fluid fed in)")

        if not net.ext_grid.empty:
            for _, row in net.ext_grid.iterrows():
                name = _get(row, 'name')
                lines.append(
                    f"  ext_grid '{name}' @ junction {_get(row,'junction')}: "
                    f"p={_get(row,'p_bar')} bar, t={_get(row,'t_k')} K, type={_get(row,'type')}"
                )

        return "\n".join(lines)
    except Exception:
        return ""


def build(
    error_type: str,
    error_msg: str,
    user_contexts: list[SourceContext],
    lib_contexts: list[SourceContext],
    knowledge: str,
    net_stats: str = "",
    terminal_logs: str = "",
    traceback_text: str = "",
) -> list[dict]:
    """
    Assemble the messages list for the Ollama chat API.

    Returns [{role: system, content: ...}, {role: user, content: ...}].
    """
    parts: list[str] = []

    # 1. Error — always first, anchors all subsequent reasoning.
    parts.append(f"## Error\n**{error_type}**: {error_msg}")

    # 2. Network statistics — most diagnostic signal for fluid-network errors.
    if net_stats:
        parts.append(net_stats)

    # 3. Full stack trace — shows the call chain so the model understands
    #    which user line triggered which pandapipes internals.
    if traceback_text:
        tb = _truncate(traceback_text, _MAX_TRACEBACK_CHARS)
        parts.append(f"## Full Stack Trace\n```\n{tb}\n```")

    # 4. User code — full file when ≤ 12 000 chars (covers most scripts),
    #    large-window snippet otherwise. ">>" marks the exact error line.
    if user_contexts:
        ctx = user_contexts[-1]  # innermost user frame = closest to the error
        full = read_full_source(ctx.file_path, ctx.lineno, _MAX_USER_FILE_CHARS)
        if full:
            parts.append(
                f"## User Code (full file — `>>` marks the error line)\n"
                f"File: `{ctx.file_path}` | Line: {ctx.lineno} | Function: `{ctx.function_name}`\n"
                f"```python\n{full}\n```"
            )
        else:
            snippet = _truncate(ctx.source_snippet, _MAX_USER_CODE_CHARS)
            parts.append(
                f"## User Code (window ±50 lines around error)\n"
                f"File: `{ctx.file_path}` | Line: {ctx.lineno} | Function: `{ctx.function_name}`\n"
                f"```python\n{snippet}\n```"
            )

    # 5. Terminal stdout captured before the error.
    #    Stderr excluded — avoids embedding the traceback a second time.
    if terminal_logs:
        logs = _truncate(terminal_logs, _MAX_LOGS_CHARS)
        parts.append(f"## Terminal Output Before Error\n```\n{logs}\n```")

    # 6. Library source — deepest pandapipes frame.
    #    Absolute path from traceback resolves to wherever pandapipes is installed.
    if lib_contexts:
        ctx = lib_contexts[-1]
        snippet = _truncate(ctx.source_snippet, _MAX_LIB_SOURCE_CHARS)
        parts.append(
            f"## pandapipes Source (where exception was raised — the fix is NOT here)\n"
            f"File: `{ctx.file_path}` | Line: {ctx.lineno} | Function: `{ctx.function_name}`\n"
            f"```python\n{snippet}\n```"
        )

    # 7. Curated knowledge checklist for this error category.
    if knowledge:
        knowledge = _truncate(knowledge, _MAX_KNOWLEDGE_CHARS)
        parts.append(f"## Diagnostic Checklist (verify these likely causes)\n{knowledge}")

    user_content = "\n\n".join(parts)

    system_content = _SYSTEM
    if CUSTOM_PROMPT and CUSTOM_PROMPT.strip():
        system_content = f"{_SYSTEM}\nCUSTOM PROMPT:\n{CUSTOM_PROMPT.strip()}"

    return [
        {"role": "system", "content": system_content},
        {"role": "user", "content": user_content},
    ]


def _truncate(text: str, max_chars: int) -> str:
    """Truncate to max_chars on a line boundary to avoid cutting mid-token."""
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rsplit("\n", 1)[0] + "\n..."
