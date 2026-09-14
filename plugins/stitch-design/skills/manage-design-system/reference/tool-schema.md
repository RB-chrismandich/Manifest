# Design System Tool Schemas

Use these examples to format your Stitch MCP design system tool calls correctly.

## UI Delivery Runtime Inventory

When UI delivery policy is active, only registered Stitch tools with these exact
registry names are classified. Every mutation requires an independently approved
`tool_name` plus canonical input hash; reads remain bound to the approved project
except account discovery.

| Classification | Exact registry names |
| --- | --- |
| Read | `mcp__stitch_list_projects`, `mcp__stitch_get_project`, `mcp__stitch_list_screens`, `mcp__stitch_get_screen`, `mcp__stitch_list_design_systems`, `mcp__stitch_read_url_content` |
| Mutation | `mcp__stitch_create_project`, `mcp__stitch_generate_screen_from_text`, `mcp__stitch_edit_screens`, `mcp__stitch_generate_variants`, `mcp__stitch_upload_design_md`, `mcp__stitch_create_design_system_from_design_md`, `mcp__stitch_update_design_system`, `mcp__stitch_apply_design_system` |

Unknown Stitch tools are denied. The inventory covers the bundled
`generate-design` and `manage-design-system` workflows.

---

## Upload `DESIGN.md`

Route `mcp__stitch_upload_design_md` only through the `/stitch-design:ui-delivery`
policy extension. The request must match the externally approved task digest, project,
and exact content; then reconcile it using the approved post-mutation readback.
The retired `upload_to_stitch.py` script deliberately rejects every upload
invocation and must not be used.

---

## `create_design_system_from_design_md`

Creates a design system for a project using the uploaded `DESIGN.md` file.

```json
{
  "projectId": "4044680601076201931",
  "selectedScreenInstance": {
    "id": "98b50e2ddc9943efb387052637738f61",
    "sourceScreen": "projects/4044680601076201931/screens/98b50e2ddc9943efb387052637738f61"
  },
  "deviceType": "DESKTOP"
}
```

> [!NOTE]
> You must upload `DESIGN.md` via the script first to get the source screen ID, and then fetch the project details with `get_project` to find the corresponding screen instance ID to pass as `id` in `selectedScreenInstance`.

---

## `update_design_system`

Updates an existing design system for a project. This is **required** immediately after calling `create_design_system` to set the theme and display the design system in the UI.

> [!NOTE]
> While `update_design_system` is mandatory after the basic `create_design_system` call, you do **not** need to call it after `create_design_system_from_design_md`. The latter automatically populates and updates all theme tokens directly from the parsed YAML frontmatter of the uploaded `DESIGN.md`.

```json
{
  "name": "assets/15996705518239280238",
  "projectId": "4044680601076201931",
  "designSystem": {
    "displayName": "My Design System",              // OPTIONAL. Display name of the design system
    "theme": {                                      // REQUIRED. The design theme object
      "colorMode": "LIGHT",                         // REQUIRED. Options: LIGHT, DARK
      "headlineFont": "INTER",                      // REQUIRED. Options: INTER, ROBOTO, OPEN_SANS, LATO, MONTSERRAT, NOTO_SANS, NOTO_SERIF, etc.
      "bodyFont": "INTER",                          // REQUIRED. Same font options as headlineFont
      "labelFont": "INTER",                         // OPTIONAL. Same font options as headlineFont
      "roundness": "ROUND_EIGHT",                   // REQUIRED. Options: ROUND_FOUR, ROUND_EIGHT, ROUND_TWELVE, ROUND_FULL
      "customColor": "#0EA5E9",                   // REQUIRED. Primary brand color / seed color for dynamic color system (hex)
      "colorVariant": "FIDELITY",                   // OPTIONAL. Options: FIDELITY, TONAL, VIBRANT, EXPRESSIVE, CONTENT, MONOCHROME, FRUIT_SALAD, RAINBOW
      "overridePrimaryColor": "#996e47",          // OPTIONAL. Override primary color (hex)
      "overrideSecondaryColor": "#0EA5E9",        // OPTIONAL. Override secondary color (hex)
      "overrideTertiaryColor": "#c4956a",         // OPTIONAL. Override tertiary color (hex)
      "overrideNeutralColor": "#0D0D0D",          // OPTIONAL. Override neutral color (hex)
      "designMd": "# Design System..."              // OPTIONAL. Markdown string with detailed design system spec
    }
  }
}
```

### Field Reference

#### Required Fields

| Field | Type | Description |
|:------|:-----|:------------|
| `colorMode` | enum | `LIGHT` or `DARK` |
| `headlineFont` | enum | Font for headlines and display text. See font options below. |
| `bodyFont` | enum | Font for body text. See font options below. |
| `roundness` | enum | `ROUND_FOUR`, `ROUND_EIGHT`, `ROUND_TWELVE`, `ROUND_FULL` |
| `customColor` | hex | Primary brand / seed color for the dynamic color system (e.g., `#E8732A`) |

#### Optional Fields

| Field | Type | Description |
|:------|:-----|:------------|
| `displayName` | string | Human-readable name for the design system |
| `labelFont` | enum | Font for labels and captions. Defaults to `bodyFont` if omitted. |
| `colorVariant` | enum | `FIDELITY`, `TONAL`, `VIBRANT`, `EXPRESSIVE`, `CONTENT`, `MONOCHROME`, `FRUIT_SALAD`, `RAINBOW` |
| `overridePrimaryColor` | hex | Override primary color (e.g., `#E8732A`) |
| `overrideSecondaryColor` | hex | Override secondary color (e.g., `#1B6B93`) |
| `overrideTertiaryColor` | hex | Override tertiary color (e.g., `#F2A541`) |
| `overrideNeutralColor` | hex | Override neutral color (e.g., `#FAF7F2`) |
| `spacingScale` | integer | Spacing scale factor (observed value: `3`) |
| `designMd` | string | Markdown string with detailed design system specifications |

#### Font Options

The following font enum values are confirmed to work (server-validated):

| Value | Font Name |
|:------|:----------|
| `INTER` | Inter |
| `ROBOTO` | Roboto |
| `OPEN_SANS` | Open Sans |
| `LATO` | Lato |
| `MONTSERRAT` | Montserrat |
| `NOTO_SANS` | Noto Sans |
| `NOTO_SERIF` | Noto Serif |
| `PLUS_JAKARTA_SANS` | Plus Jakarta Sans |
| `BE_VIETNAM_PRO` | Be Vietnam Pro |

> [!WARNING]
> Omit the legacy `font` field when updating the design system to avoid "invalid argument" errors.

> [!NOTE]
> The `namedColors` object above is abbreviated. The full response contains 50+
> Material 3 color tokens including all container, fixed, and inverse variants.

---

## `apply_design_system`

Applies a design system to one or more screens in a project.

> [!IMPORTANT]
> `selectedScreenInstances` must contain **only** `id` and `sourceScreen` — do NOT
> include position/dimension fields (`x`, `y`, `width`, `height`) or the request
> will fail with "invalid argument". Get the screen instance IDs from
> `get_project`.

```json
{
  "projectId": "4044680601076201931",
  "assetId": "c277fcdfc1e04baf91b92d975ff4c54a",
  "selectedScreenInstances": [
    {
      "id": "98b50e2ddc9943efb387052637738f61",
      "sourceScreen": "projects/4044680601076201931/screens/98b50e2ddc9943efb387052637738f61"
    },
    {
      "id": "ab12cd34ef56789012345678abcdef01",
      "sourceScreen": "projects/4044680601076201931/screens/ab12cd34ef56789012345678abcdef01"
    }
  ]
}
```

**How to get the required IDs:**

1. Call `get_project` to retrieve `screenInstances` — each has an `id` and
   `sourceScreen`.
2. Call `list_design_systems` to retrieve the design system `name` (format:
   `assets/{assetId}`) — use the part after `assets/` as the `assetId`.
3. Filter out any instances with `type: "DESIGN_SYSTEM_INSTANCE"` — only pass
   real screens.
