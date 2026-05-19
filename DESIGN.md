<!-- SEED: re-run /impeccable document once there's code to capture the actual tokens and components. -->
---
name: KnowledgeBase Review Console
description: Calm, precise review-and-insights surface for an LLM-fed wiki, handoffs, and rejection patterns.
---

# Design System: KnowledgeBase Review Console

## 1. Overview

**Creative North Star: "The Workshop Bench"**

This is a single-operator review console for a personal LLM-fed wiki. The metaphor is a well-lit workshop bench: tools laid out exactly where the hand expects them, surfaces clean, nothing decorative. Wiki reading happens elsewhere (Antigravity / Obsidian); this surface exists strictly to **decide** — approve, reject, inspect a pattern — and to surface the *shape* of those decisions over time.

The aesthetic family is the restrained-operations cluster: Linear, Plausible, Stripe Dashboard, Raycast. Tinted slate-blue neutrals carry almost the whole UI. One accent appears on ≤5% of any screen, and only for live state (focus, current selection, the row a destructive action is about to land on). Density is deliberate; whitespace is structural, not decorative. Status is conveyed by position, glyph, and label — never by color alone.

The system explicitly rejects: the four-up KPI strip, the giant-number-with-trend-arrow card, gradient accents, "Welcome back!" greetings, decorative sparklines, soft pastels, rounded-everything, illustration-heavy empty states, and the Filament / Django-Admin / Retool look. If a screen could be confused with a generic SaaS dashboard at a glance, it has failed.

**Key Characteristics:**
- Restrained color strategy: tinted slate-blue neutrals + a single signal accent ≤5%
- Single technical/geometric sans across the entire UI
- Responsive motion language: feedback + short transitions; no choreography
- Operator-grade density; whitespace is structural, not breathing room
- Lint-grade honesty: state is truthful, never decorative

## 2. Colors

A near-monochrome cool-slate palette. Neutrals do almost all the work. The accent earns its place by appearing rarely.

### Primary
- **Signal** *(`[to be resolved during implementation]`)*: the one accent. Used only for live state — focus rings, the currently-selected review row, the active filter chip, the destructive-action confirmation. Target use: ≤5% of any screen. Hue direction: a single saturated step away from the neutral ramp's hue, leaning slightly cool. Not violet (Linear's lane), not red (Raycast's lane); pick a neighboring tone during implementation.

### Neutral
The whole surface and text system lives here. All neutrals are **tinted toward a single cool-slate hue** (small chroma, ~0.005–0.012); never pure greys, never `#000` or `#fff`.

- **Bench** *(deepest surface)*: the page background. Slightly warmer than panel surfaces so panels feel raised without shadow.
- **Panel** *(primary surface)*: cards, the review pane, the dashboard panels.
- **Rail** *(secondary surface)*: nav rail, secondary toolbars, condensed table rows.
- **Hairline** *(divider)*: the project's primary delineator. 1px, low-contrast, used liberally instead of shadows.
- **Ink** *(body text)*: ≥4.5:1 against Panel; the main reading color.
- **Ink-Muted** *(secondary text)*: timestamps, paths, frontmatter keys, byline-style metadata. ≥4.5:1 in the contexts it appears.
- **Ink-Dim** *(tertiary text)*: shortcut hints, "n items" counts, disabled labels. ≥3:1 minimum; never used for primary content.

*Hex / OKLCH values to be resolved during implementation. Generate the ramp in OKLCH around a single cool-slate hue.*

### Status (semantic, not decorative)
- **Accepted**: not a color. A solid check glyph and a position change (the row leaves the queue). If a tint is needed, a quiet positive-leaning neutral; never a saturated green.
- **Rejected**: a small ring or hollow glyph, again not pure red. Pair every rejected pill with its TTL countdown so red never means "alarm" — it means "scheduled deletion".
- **Pending / Awaiting**: no color at all. Position in the queue is the status.
- **Expiring soon (TTL ≤ 24h)**: the Signal accent, used here as a deadline cue, not decoration.

### Named Rules

**The One Accent Rule.** Across any single screen, Signal occupies ≤5% of the pixels. If it covers more, something has been treated as decoration. Remove it.

**The Tinted Neutrals Rule.** Every neutral is tinted toward the cool-slate hue. `#000`, `#fff`, and untinted greys are forbidden. The tint is the brand.

**The Color-Plus-Glyph Rule.** No status — accepted, rejected, pending, expiring — is communicated by color alone. Color is paired with a glyph, a label, or position. Color-blind users see the same state as anyone else.

## 3. Typography

**Display Font:** a single technical/geometric sans across the entire UI *(family to be chosen at implementation — Inter, Geist, IBM Plex Sans, and Söhne are all in-register; pick one with a mono companion or excellent tabular figures)*.
**Body Font:** same family.
**Mono companion:** *(to be chosen at implementation; should pair with the display/body family)*. Used for paths, slugs, hashes, frontmatter keys, lint codes, TTL countdowns.

**Character:** One typeface across the UI gives the console a single, neutral voice. The mono companion is used sparingly and only for content that is *literally a string of code or path* — never for emphasis. Tabular figures are mandatory for any column of numbers (counts, percentages, TTLs).

### Hierarchy
- **Display** *(weight 500, ~28–32px, line-height 1.15)*: page headings (e.g. "Review Queue", "Dashboard"). Single instance per screen.
- **Headline** *(weight 500, ~20px, line-height 1.25)*: section headings inside a screen.
- **Title** *(weight 500, ~15px, line-height 1.3)*: card / row titles (wiki page title in the review queue, handoff doc title, dashboard panel header).
- **Body** *(weight 400, 14–15px, line-height 1.5, max width 65–75ch)*: descriptive text, page summaries, dashboard prose. Body never goes below 14px effective.
- **Body-Mono** *(weight 400, ~13–14px)*: paths, slugs, lint codes, TTL strings. Tabular figures on.
- **Label** *(weight 500, 11–12px, letter-spacing +0.04em, uppercase)*: small metadata labels — "type", "source", "captured\_at". Used sparingly; never for body content.

### Named Rules

**The One Family Rule.** A single typographic family carries the entire UI. Pairing a display serif with a body sans is in-register for editorial brand work, not for this operations console; it is prohibited here.

**The Tabular Figures Rule.** Every column of numbers — counts, percentages, TTL countdowns, IDs — uses tabular figures. Numbers must align vertically. Proportional figures in a stat column are a defect.

**The Mono-for-Strings Rule.** Mono is reserved for content that *is* a literal string: paths, slugs, hashes, lint codes, frontmatter keys. Mono used for "technical feel" or emphasis is prohibited.

## 4. Elevation

Flat by default. Depth is conveyed by **tonal layering** between Bench (page), Panel (primary surface), and Rail (secondary surface) — never by shadow on resting elements. Hairline dividers do almost all the structural work that shadows would do in a more decorative system.

The only acceptable shadows are **state shadows**, applied transiently:
- A subtle focus halo on the currently-focused interactive element (paired with the Signal accent ring).
- A faint lift on a row when it's the target of a hover-pending destructive action.
- Modals, when they exist, sit on a low-opacity scrim, not a glassy blur. Glassmorphism is forbidden anywhere in this system.

### Named Rules

**The Flat-By-Default Rule.** Surfaces are flat at rest. Shadow appears only as a response to state (focus, destructive-target hover). Persistent decorative shadows on cards, panels, or rails are prohibited.

**The Hairline-Not-Shadow Rule.** Where another design would reach for a soft shadow to separate surfaces, this system reaches for a 1px hairline. Hairlines are the project's primary tool for structure.

## 5. Components

*Component specification deferred until implementation. The console has no components yet; the next pass of `/impeccable document` will run in scan mode and capture the real primitives — review row, dashboard panel, handoff card, TTL countdown, filter chip, command palette — directly from the codebase.*

## 6. Do's and Don'ts

### Do:
- **Do** tint every neutral toward the cool-slate hue (chroma ~0.005–0.012). Pure greys, `#000`, and `#fff` are forbidden.
- **Do** keep the Signal accent on ≤5% of any screen, reserved for live state and the next destructive action.
- **Do** pair every status (accepted / rejected / pending / expiring) with a glyph or label, never color alone.
- **Do** use tabular figures in every column of numbers — counts, percentages, TTL strings, IDs.
- **Do** prefer 1px hairlines over shadows to separate surfaces.
- **Do** keep body text ≥14px effective and body line length within 65–75ch.
- **Do** honor `prefers-reduced-motion: reduce`: remove transitions, fall back to opacity / instant state changes only.
- **Do** put real values on screen — real counts, real timestamps, real lint codes. Fake skeletons or rounded-down numbers that hide errors are forbidden.

### Don't:
- **Don't** build the four-up KPI strip (Total / Active / Pending / +12% MoM). It is the SaaS-dashboard cliché the PRODUCT.md explicitly rejects.
- **Don't** use the giant-number-with-trend-arrow card. A correctly chosen number in its own context beats a hero metric every time.
- **Don't** use decorative sparklines. Charts must explain a rejection or acceptance pattern; if a chart doesn't answer a question, delete it.
- **Don't** apply gradients anywhere — on text (`background-clip: text` is banned), on backgrounds, on accents.
- **Don't** use side-stripe borders (`border-left` or `border-right` > 1px as a colored accent). On rows, status pills, callouts: forbidden.
- **Don't** apply glassmorphism — backdrop-blur as decoration, "glassy" panels, frosted nav. Forbidden anywhere in this system.
- **Don't** wrap content in identical card grids. Cards are the lazy answer; nested cards are always wrong.
- **Don't** write "Welcome back!", "Awesome!", or any encouragement copy. The voice is short, factual, second-person only when necessary; never marketing.
- **Don't** show illustration-heavy empty states. Empty states are short factual sentences (e.g. "No pages awaiting review. Last cron completed at 03:17.") with the next action, if any, in plain text.
- **Don't** drift toward Filament / Django-Admin / Retool aesthetics — uniform tables, generic action menus, framework-default forms. The PRODUCT.md anti-reference is the line.
- **Don't** drift toward consumer-warm notebook aesthetics — soft pastels, rounded-everything, friendly serifs, mascots. Wrong register for this tool.
- **Don't** add Notion/WYSIWYG editing affordances — slash menus, drag handles, block editors. This is a review surface, not an editing surface.
- **Don't** animate CSS layout properties. Animate transform and opacity only. No bounce, no elastic; ease out with quart/quint/expo curves.
- **Don't** rely on color alone to communicate any status, ever.
