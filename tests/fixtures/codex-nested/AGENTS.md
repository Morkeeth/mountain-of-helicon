# Rust/rs

In the rs folder where the rust code lives:

- Use an exact `/*param_name*/` comment before opaque literal arguments.
- All injected fragments must be defined as structs in `core/context`.
- raw response item events (`rawResponseItem/*`), even while experimental
- If you want to wrap a line, use the helpers in tui/src/wrapping.rs.

These guidelines apply to app-server protocol work in `rs`, especially:

- `app-server-protocol/src/protocol/common.rs`
- `app-server-protocol/src/protocol/v2/`
- Expose RPC methods as `<resource>/<method>` (for example, `thread/read`, `app/list`).
- Stale since the v2 split: `app-server-protocol/src/protocol/v2.rs`
