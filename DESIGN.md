---
name: Study Assistant
description: A calm, focused workspace for learning from a personal library.
colors:
  ink: "#111"
  paper: "#fff"
  rail: "#fbfbfa"
  soft-surface: "#fafafa"
  divider: "#e6e6e6"
  field-border: "#ccc"
  muted: "#666"
  quiet: "#999"
  focus-blue: "#175dc1"
  success: "#27643a"
  error: "#9d2929"
typography:
  display:
    fontFamily: "IBM Plex Sans, system-ui, sans-serif"
    fontSize: "30px"
    fontWeight: 600
    lineHeight: 1.2
  title:
    fontFamily: "IBM Plex Sans, system-ui, sans-serif"
    fontSize: "23px"
    fontWeight: 400
    lineHeight: 1.35
  body:
    fontFamily: "IBM Plex Sans, system-ui, sans-serif"
    fontSize: "14px"
    fontWeight: 400
    lineHeight: 1.5
  label:
    fontFamily: "IBM Plex Mono, monospace"
    fontSize: "11px"
    fontWeight: 400
    lineHeight: 1.4
rounded:
  tight: "3px"
  compact: "4px"
  field: "5px"
  message: "14px 14px 2px"
  circular: "50%"
spacing:
  xs: "4px"
  sm: "8px"
  md: "12px"
  lg: "16px"
  xl: "24px"
  content: "28px"
components:
  button-primary:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.paper}"
    rounded: "{rounded.tight}"
    padding: "9px 14px"
  button-primary-hover:
    backgroundColor: "#333"
  navigation-active:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.paper}"
    rounded: "{rounded.compact}"
    padding: "10px 12px"
  field:
    backgroundColor: "{colors.paper}"
    rounded: "{rounded.field}"
    padding: "7px 8px 7px 14px"
  card:
    backgroundColor: "{colors.paper}"
    padding: "18px"
---

# Design System: Study Assistant

## Overview

**Creative North Star: "The Focused Study Desk"**

Study Assistant is a quiet, utilitarian workspace that keeps learning actions close at hand. The interface earns its sense of completeness through predictable navigation, consistent controls, direct language, and visible system feedback rather than decorative flourishes.

The visual field stays intentionally spare: paper-white work areas, a slightly warm rail, near-black actions, and thin gray boundaries. Information is organized like a well-kept desk: a stable place for tools, a clear working surface, and only the cues needed to complete the next study task.

**Key Characteristics:**

- Quietly utilitarian controls with high contrast actions.
- Compact, dense layout that protects reading and working space.
- Clear status, selection, error, and progress feedback.
- IBM Plex Sans for approachable utility; IBM Plex Mono for provenance and metadata.

## Colors

The palette is almost entirely neutral so the interface remains calm during extended study sessions; color is reserved for actionable state and accessibility feedback.

### Primary

- **Desk Ink:** Near-black used for primary actions, active navigation, strong text, and the primary user chat bubble.
- **Paper:** White used for the application canvas, controls, and cards.

### Neutral

- **Warm Rail:** Off-white used behind the primary navigation and secondary workspace rail.
- **Soft Surface:** Pale gray used for contained helper areas, review items, and selected answers.
- **Hairline Divider:** Light gray used to establish quiet structure between regions.
- **Field Edge:** Mid-light gray used for inputs, selectable options, and contained controls.
- **Working Gray:** Used for supporting body text and secondary actions.
- **Quiet Metadata:** Used for labels, source metadata, inactive progress, and restrained helper text.

### Tertiary

- **Focus Blue:** Reserved for the visible keyboard focus ring.
- **Completion Green:** Used for successful library and correct-answer feedback.
- **Correction Red:** Used for errors, destructive actions, and incorrect-answer feedback.

**The Color-Has-a-Job Rule.** Color must communicate focus, completion, or correction. The neutral palette carries the rest of the interface.

## Typography

**Display Font:** IBM Plex Sans (with system-ui, sans-serif fallback)

**Body Font:** IBM Plex Sans (with system-ui, sans-serif fallback)

**Label/Mono Font:** IBM Plex Mono (with monospace fallback)

**Character:** IBM Plex Sans gives task instructions and reading a clear, human utility voice. IBM Plex Mono separates source information, model controls, filenames, and keyboard cues from ordinary reading without making them compete for attention.

### Hierarchy

- **Display** (600, 30px, 1.2): Used for workspace page titles such as Resources and exam history.
- **Headline** (400, 29px, normal): Used for the exam configuration title and primary empty-state heading.
- **Title** (400, 23px, 1.35): Used for an exam question.
- **Body** (400, 14px, 1.5): Used for application copy, messages, and empty states.
- **Label** (400–600, 10–12px, 0.08em tracking where uppercase): Used for source provenance, section labels, controls, and compact metadata.

**The Reading-First Rule.** Larger type introduces the current task; small mono and uppercase labels only identify supporting context.

## Layout

Desktop uses a fixed 200px application rail and a flexible main workspace. The rail holds product identity and navigation, while the main area supplies a persistent top bar and a task-specific work surface. Chat reading is constrained to a 720px column; resource and history work areas expand to 900px; exam flows use a 760px column.

The interface favors a compact 4px-based rhythm, with frequent 8px, 12px, 16px, 24px, and 28px steps. At 700px and below, the rail becomes a sticky horizontal navigation bar, multi-column form controls collapse to one column, and page padding reduces from 28px to 18px. At 420px and below, navigation receives its own row.

**The Stable Tools Rule.** Navigation stays visible while the task surface changes; responsive layouts preserve that orientation before adding more density.

## Elevation & Depth

The system is flat by default. Thin borders, background changes, and selected states define regions; no shadow vocabulary is used. This keeps a long-lived application workspace visually calm and makes feedback states more noticeable.

**The Flat-By-Default Rule.** Use a border, tonal shift, or explicit state treatment to separate content. Do not add decorative shadows.

## Shapes

Geometry is mostly square and compact. Primary controls use tight 3px corners, navigation items use 4px corners, and the chat composer uses a 5px field corner. Circles identify status dots, question progress, and answer markers. The outgoing message bubble is the exception: its 14px, 14px, 2px corner pattern marks conversational ownership without turning the rest of the product into a rounded interface.

## Components

Quietly utilitarian components give each action a clear boundary and state without visual noise.

### Buttons

- **Shape:** Tight corners (3px) for contained primary actions; text actions remain unboxed and underlined.
- **Primary:** Desk Ink background with Paper text, usually 9px 14px padding. Full-width generation uses the same assignment.
- **Hover / Focus:** Primary actions lift their background to a dark gray on hover; keyboard focus uses the global 3px Focus Blue outline with a 3px offset.
- **Secondary / Ghost / Tertiary:** Secondary controls use a white field with an Ink border. Text actions use underlined Working Gray text and turn Ink on hover.

### Cards / Containers

- **Corner Style:** Square by default.
- **Background:** Paper cards sit on the main canvas; soft helper and review containers use Soft Surface.
- **Shadow Strategy:** No shadows. Hairline borders and tonal changes establish containment.
- **Border:** Light gray around document and history cards; dashed Field Edge for empty or loading workspace messages.
- **Internal Padding:** Most cards use 18px; review blocks use 20px; result cards use 22px.

### Inputs / Fields

- **Style:** Paper background, 1px Field Edge, compact padding, and either square or 5px composer corners.
- **Focus:** The global Focus Blue 3px outline remains visible with a 3px offset.
- **Error / Disabled:** Error feedback uses Correction Red. Disabled controls lower opacity to 0.55 and show a not-allowed cursor.

### Navigation

- **Style:** The desktop rail uses a 200px warm off-white column with 14px navigation items.
- **Default / Hover / Active:** Default links use Working Gray; hover shifts to a pale gray fill and Desk Ink; active links become Desk Ink with Paper text.
- **Mobile Treatment:** At 700px the rail becomes a sticky horizontal bar; at 420px it places the wordmark and nav on separate rows.

### Status & Progress

- **Style:** Status dots and question dots are circular; labels stay compact and muted.
- **State:** A filled dot indicates answer completion, a 2px Ink outline indicates the current question, and green or red appear only when the outcome is meaningful.

## Do's and Don'ts

### Do:

- **Do** use Desk Ink for the one clear primary action in a working area.
- **Do** use 1px dividers and contained backgrounds to structure information.
- **Do** preserve visible keyboard focus with the 3px Focus Blue outline.
- **Do** state loading, success, error, and selection in direct, compact language.
- **Do** use IBM Plex Mono for source, file, model, and keyboard metadata.

### Don't:

- **Don't** introduce decorative gradients, shadows, or oversized display treatment.
- **Don't** use color as ornament; reserve it for focus, completion, correction, and destructive actions.
- **Don't** obscure orientation on small screens: keep the product name and main navigation available.
- **Don't** add large corner radii to ordinary controls or cards.
