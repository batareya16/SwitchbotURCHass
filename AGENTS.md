# Project Instructions

## Firmware is the capability source of truth

- Treat recovered firmware code and resource tables as the source of truth for remote capabilities. Do not use the current integration catalog or app icon list as proof that a capability is absent.
- When a firmware capability or mapping is unclear, inspect the firmware and Ghidra evidence until the relevant path is resolved. Do not stop at an implementation limitation, classify behavior as unknown, or omit a firmware capability while source images, symbols, resource tables, scripts, or Ghidra projects remain available to inspect.
- Before omitting or declaring a remote profile, icon, glyph, page, or behavior unsupported, inspect the relevant firmware paths and resources. Keep confirmed support, unverified behavior, and integration gaps distinct.
- Recover the full relationship between device type, screen profile, control mode, icon variant, page layout, and rendered artwork from firmware before defining the user-facing Type catalog. Add all confirmed combinations and never invent a mapping to fill a gap.
- Surface firmware-provided screen artwork and button glyphs in Remote Studio for every supported profile. Keep those separate from SwitchBot app/list icons and packet fields.
- For user-facing Native remote setup, present one visual Type choice that applies the matching screen profile, layout and firmware-backed artwork settings together. Keep protocol fields internal unless the firmware proves the selected type needs a user decision.
