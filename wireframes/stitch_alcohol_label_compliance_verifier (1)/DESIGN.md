# Design System Specification: The Precision Monolith

## 1. Overview & Creative North Star
**Creative North Star: The High-Resolution Auditor**

This design system rejects the "airy" and "floating" trends of consumer SaaS in favor of **Precise Brutalism**. It is designed for the compliance officer who requires extreme information density without cognitive overload. The aesthetic is "local-first"—it feels like a powerful, native workstation tool rather than a generic web app. 

The system breaks the "template" look by using intentional asymmetry and **Tonal Layering**. Instead of standard grids, we utilize massive typographic contrast and weighted "monolithic" containers that prioritize data integrity and focus. Every element is intentional; there is no "fluff."

---

## 2. Colors & Surface Architecture

The palette is anchored in deep oceanic blacks (`on-surface: #0a3747`) and clinical, high-contrast whites (`surface: #f4faff`). This provides a laboratory-grade environment for auditing.

### The "No-Line" Rule
**Explicit Instruction:** 1px solid borders are strictly prohibited for sectioning or layout. Boundaries must be defined solely through background color shifts or subtle tonal transitions.
*   **Application:** A sidebar should be `surface-container-low` (#e7f6ff) sitting against a `surface` (#f4faff) main viewport. Use `surface-container-highest` (#c1e8fd) for active, focused zones.

### Surface Hierarchy & Nesting
Treat the UI as a physical stack of fine paper.
*   **Base Layer:** `surface` (#f4faff).
*   **The Review Workspace:** `surface-container-low` (#e7f6ff) for the general background.
*   **Actionable Data Cards:** `surface-container-lowest` (#ffffff) to provide "pop" and clarity.
*   **Focused Overlays:** `surface-container-high` (#cdedfe) for side-panels or inspector views.

### The "Glass & Gradient" Rule
To elevate the utility-first look into a "high-end" experience:
*   **Floating Elements:** Use Glassmorphism for floating toolbars. Apply `surface-container-lowest` at 80% opacity with a `20px` backdrop-blur.
*   **Signature Textures:** For primary calls to action or header backgrounds, use a subtle linear gradient from `primary` (#2b5bb5) to `primary-dim` (#1a4ea8) at a 135-degree angle. This adds a "weighted" feel that flat hex codes lack.

---

## 3. Typography: The Information Hierarchy

We employ a dual-font strategy to balance editorial authority with technical precision.

*   **Inter (Foundational):** Used for all `Display`, `Headline`, `Title`, and `Body` scales. It provides the neutral, Swiss-style clarity required for complex data.
*   **Public Sans (Technical):** Reserved exclusively for `Label` scales. Its slightly more technical, sturdy rhythm is used for metadata, table headers, and status tags to signal "this is data" versus "this is instruction."

**Hierarchy Goals:**
*   **Display-LG (#0a3747):** Used for high-level compliance scores. 
*   **Title-SM (#3e6475):** Used for section headers to provide a sophisticated, muted contrast against the bold black data.
*   **Body-MD (Inter):** The workhorse for legal text and review notes.

---

## 4. Elevation & Depth

We achieve depth through light physics rather than digital "shadow" effects.

*   **The Layering Principle:** Stacking is the primary method of elevation. Place a `surface-container-lowest` card on a `surface-container-low` background to create a "soft lift."
*   **Ambient Shadows:** For floating modals, use a "Tinted Ambient Shadow": 
    *   `box-shadow: 0 12px 40px rgba(10, 55, 71, 0.08);` 
    *   This uses the `on-surface` color (#0a3747) as the shadow base, making the shadow feel like a natural light obstruction rather than a gray smudge.
*   **The "Ghost Border" Fallback:** If a border is required for high-density tables, use `outline-variant` (#91b8cb) at **15% opacity**. It should be felt, not seen.

---

## 5. Components

### Buttons: The "Robust" Standard
*   **Primary:** Gradient of `primary` to `primary-dim`. `0.25rem` (DEFAULT) roundedness. No border. Text is `on-primary` (#f7f7ff).
*   **Secondary:** `surface-container-highest` background with `on-primary-container` (#194da7) text. 
*   **Tertiary/Warning:** For 'Needs Review' actions, use `tertiary-container` (#fc6018) to grab immediate attention without being an "Error."

### Status Indicators (The Compliance Core)
*   **Match (Success):** Use a custom Emerald (approx #1e7d32) text on `surface-container-lowest`.
*   **Needs Review (Amber):** `tertiary` (#a93900) text on `tertiary-container` (#fc6018) at 20% opacity.
*   **Mismatch (Error):** `error` (#9e3f4e) text on `error-container` (#ff8b9a).

### Data Tables & Workstation Lists
*   **No Dividers:** Forbid the use of 1px lines between rows.
*   **Alternating Tones:** Use a subtle shift from `surface-container-lowest` to `surface-container-low` on hover to indicate row selection.
*   **Information Density:** Use `body-sm` for table content to maximize visible data. Header labels must be `label-sm` (Public Sans) in uppercase with 0.05em letter spacing for an authoritative, "auditor" feel.

### Input Fields
*   **Professional State:** High-contrast `surface-container-lowest` backgrounds. On focus, use a 2px "Ghost Border" using `primary` (#2b5bb5) but at 40% opacity. Avoid the "glow" effect; keep it sharp.

---

## 6. Do's and Don'ts

### Do
*   **DO** use whitespace as a separator. If two sections feel cramped, increase the padding—do not add a line.
*   **DO** use `surface-container-highest` for "Global Navigation" or "Fixed Sidebars" to ground the application.
*   **DO** lean into high-contrast text. Accessibility in compliance is non-negotiable; ensure `on-surface` is the default for all critical data.

### Don't
*   **DON'T** use shadows on every card. Only use shadows for elements that physically "move" over the UI (modals, dropdowns).
*   **DON'T** use rounded corners larger than `lg` (0.5rem). This is a professional tool; keep the geometry sharp and serious.
*   **DON'T** use pure black (#000) for text. Always use `on-surface` (#0a3747) to maintain the sophisticated tonal palette.
*   **DON'T** use animations that take longer than 150ms. Transitions should be "instant but smooth" to respect the user's efficiency.