# Memory Steward TUI

Terminal Glass Pane for the Memory Steward MCP server.

## Purpose

The TUI is a Textual client, not a new management API. It discovers FastMCP tools and their input JSON Schemas at runtime, groups tools by plane, builds scalar forms dynamically, invokes the selected tool, and renders structured/text results.

## Connectivity

Default MCP URL:

~~~text
http://127.0.0.1:8081/mcp
~~~

Override with `STEWARD_MCP_URL`.

For the default local workflow, establish the repository loopback port-forward first:

~~~bash
task ops:mcp:forward
~~~

Then launch the installed `steward-tui` entry point.

## UI behavior

- left pane: live-discovered tools grouped by inferred plane;
- detail pane: tool title and description;
- form: generated from JSON Schema scalar fields;
- invoke button: calls `Client.call_tool(..., raise_on_error=False)`;
- result log: structured content, text blocks, and tool errors;
- `r`: refresh tool list;
- `q`: quit.

## Supported scalar schema fields

The form builder handles string, integer, number, and boolean inputs. Optional empty values are omitted; required empty values are rejected client-side. Complex/unrecognized schema forms fall back conservatively rather than embedding server policy in the UI.

## Tests

The component contains tests for application/schema behavior. Keep tests focused on schema parsing, coercion, plane grouping, and invocation rendering; server-side tool policy belongs to `memory_steward_mcp` tests.

## Authority boundary

The TUI must never duplicate or reinterpret mutation policy. The MCP server is the schema and behavior authority. Destructive tools remain explicit operator actions.
