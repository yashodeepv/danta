# Danta Design Spec — LLM writing guide

You help designers write Danta **design specs**. A design spec is the **customer-facing website** layer of a Danta project — the storefront, app, or portal that end users see. It describes how each screen looks, not what the business logic does.

> **Two separate concerns — keep them separate:**
>
> | Layer | Where it lives | What it controls |
> |---|---|---|
> | **Customer website** | Design spec (`Design: danta/0.1`) | Storefront, catalog, checkout, user-facing screens |
> | **Admin panel** | Backend spec (`## Screen:` sections) | Internal dashboards, data tables, management screens |
>
> Do NOT design admin screens in the design spec. The backend spec's `## Screen:` sections already generate the admin panel automatically. The design spec focuses entirely on making the **customer-facing side beautiful and release-ready**.

The compiled output is a self-contained, production-ready HTML frontend served by nginx. List screens **fetch live data** from `/api/data/<entity>` automatically. Forms **POST to the backend** and refresh lists on success. No extra wiring needed.

Follow the grammar exactly; the compiler is strict on keywords and structure.

---

## Available system elements

<!-- SYSTEM_CONTEXT_START -->
{{system_context}}
<!-- SYSTEM_CONTEXT_END -->

This section is injected at request time from the compiled backend spec. Every `Form:` flow name, `List:` entity name, and field name you use must appear in it. **Only use HTTP flows in forms** — schedule, event, and topic flows cannot be triggered from a web page.

---

## File structure

```
Design: danta/0.1             ← required first line

System: <name>                ← must match the backend spec's System: name exactly

## Theme                      ← optional, at most once
## Screen: <name>             ← one per customer-facing screen (name freely chosen)
```

> Screen names in the design spec are **yours to choose freely** — they do not need to match backend `## Screen:` names. Pick names that describe the customer journey: `home`, `catalog`, `product`, `checkout`, `orders`, `account`.

---

## Spec header

```
Design: danta/0.1

System: shop-orders
```

- `Design: danta/0.1` must be the very first non-blank line.
- `System:` must match the backend spec's `# System:` name exactly.

---

## Theme section

Optional. Controls the visual identity of the entire site.

```
## Theme
Brand: "Acme Shop"
Colors: primary "#6366f1", accent "#f59e0b"
Font: "Inter"
Radius: rounded
Mode: auto
```

| Property | Values | Default |
|---|---|---|
| `Brand:` | `"name"` — shown in nav and browser tab | (system name) |
| `Colors:` | `primary "#hex"`, `accent "#hex"`, `success "#hex"`, `danger "#hex"` | brand palette |
| `Font:` | `"Font Name"` — any Google Font | Inter |
| `Radius:` | `none` · `small` · `medium` · `large` · `rounded` | `medium` |
| `Mode:` | `light` · `dark` · `auto` | `auto` |
| `Animations:` | Comma-separated list of effects (see below) | _(none)_ |
| `Style:` | One of: `default` · `cyberpunk` · `glass` · `minimal` · `bold` | `default` |
| `Background:` | One of: `particles` · `mesh-gradient` · `dot-grid` · `circuit` · `video src "url"` | _(none)_ |
| `Interactions:` | Comma-separated micro-interactions (see below) | _(none)_ |

### Style presets

Apply a cohesive visual personality to the entire site with a single keyword.

```
## Theme
Style: cyberpunk
Colors: primary "#8b5cf6", accent "#22d3ee"
```

| Value | Effect |
|---|---|
| `default` | Clean, modern light UI (no overrides) |
| `cyberpunk` | Dark background, neon gradient headings, glow-on-hover cards, scan-line overlay |
| `glass` | Frosted-glass panels — all cards get `backdrop-filter: blur(20px)` and translucent borders |
| `minimal` | No shadows, thin 1px borders, flat rectangular shapes |
| `bold` | Oversized headings, thick left-border accent on cards, ALL-CAPS buttons |

### Background effects

Add a full-page ambient background effect.

```
## Theme
Background: particles
Background: mesh-gradient
Background: dot-grid
Background: circuit
Background: video src "/assets/bg.mp4"
```

| Value | Effect |
|---|---|
| `particles` | Animated canvas particle network (uses theme primary color) |
| `mesh-gradient` | Soft animated radial colour blobs behind the content |
| `dot-grid` | Subtle grid of dots (like graph paper) |
| `circuit` | Circuit-board SVG trace pattern |
| `video` | Full-bleed looping video (requires `src "url"`) |

### Micro-interactions

Fine-grained hover and click effects — combine multiple.

```
## Theme
Interactions: card-tilt, button-glow, ripple
```

| Value | Effect |
|---|---|
| `card-tilt` | Cards tilt in 3D perspective on mouse hover |
| `button-glow` | Primary buttons show a spotlight glow that follows the cursor |
| `ripple` | Material-style ink-ripple on every button click |
| `magnetic-links` | Nav links softly attract toward the cursor when nearby |
| `parallax-cards` | Cards in grids shift at different scroll rates |

### Animations

Add `Animations:` to the `## Theme` section to make the site feel alive. Mix and match as needed.

```
## Theme
Brand: "Parfumerie"
Colors: primary "#be185d", accent "#9333ea"
Animations: scroll-reveal, stagger, counter, parallax
```

| Value | Effect |
|---|---|
| `scroll-reveal` | Every component fades + slides up into view as the user scrolls down |
| `stagger` | Grid items (columns, cards, pricing tiers, stats) animate in one by one with offset delays |
| `counter` | Stat numbers count up from 0 when they scroll into view |
| `parallax` | Hero background image scrolls at a slower rate, creating depth |
| `typewriter` | Hero heading types itself out character by character on load |

**Recommended presets:**
- Marketing / landing: `scroll-reveal, stagger, parallax`
- SaaS dashboard: `scroll-reveal, stagger, counter`
- Full-featured storefront: `scroll-reveal, stagger, counter, parallax`

**Choosing good colors:** Pick a `primary` that defines the brand (buttons, links, active states) and an `accent` that contrasts with it (price callouts, highlights). For ecommerce, warm primaries (`#e11d48`, `#db2777`, `#ea580c`) work well for storefronts; cool primaries (`#6366f1`, `#0ea5e9`) suit SaaS products.

---

## Screen sections

Each `## Screen:` section is a page in the customer-facing website. Name them after the customer journey — `home`, `catalog`, `checkout`, `my_orders`, `account`.

```
## Screen: catalog
Layout: full
...components...
```

### Layout keywords

| Keyword | Effect | Best for |
|---|---|---|
| `centered` | Content centred in a max-width container | Forms, settings, checkout |
| `card` | Wrap the main content in a card/panel | Login, single-action screens |
| `full` | Full-width, no max-width constraint | **Product grids, catalogs** |
| `sidebar` | Left sidebar navigation | Multi-section apps |
| `two-col` | Two equal columns | Landing pages, split layouts |
| `dashboard` | Grid of stat cards + content | Account overview |
| `minimal` | No chrome, just the content | Confirmation screens |
| `hero` | Large hero section at the top | **Landing pages** |
| `split` | Left content, right decorative panel | Login, signup |

---

## Components

Components are the building blocks of a screen. List them in display order. Mix and match freely — there are no restrictions on order or combinations.

### Hero

Full-bleed gradient banner — always goes first on landing and marketing screens.

```
Hero: heading "Fresh fragrances, delivered.", sub "Shop 500+ perfumes from top houses.", cta "Shop now"
```

| Part | Description |
|---|---|
| `heading` | Large heading text (1–8 words, punchy) |
| `sub` | Subtitle or supporting copy |
| `cta` | Call-to-action button label (optional) |

---

### Header

Page-level title bar with optional action buttons. Use on catalog and account screens.

```
Header: "My Orders" action "Reorder"
Header: "Browse Catalog" action "Filter", action "Sort"
```

---

### Form

Renders the named flow's trigger fields as a form. **Flow must have an HTTP trigger.**

```
Form: add_perfume
  - name: placeholder "e.g. Bleu de Chanel"
  - brand: placeholder "House name"
  - price: money large
  - description: placeholder "Fragrance notes…"
Submit: "Add to catalog"
```

**Field hints** (after the field name):

| Hint | Effect |
|---|---|
| `hidden` | Pre-filled automatically, not shown |
| `placeholder "text"` | Input placeholder text |
| `label "text"` | Override the field label |
| `segmented "A \| B \| C"` | Segmented control / pill toggle |
| `badge` | Coloured status badge |
| `large` | Hero-size display number |
| `money` | Currency widget hint |
| `date` | Date picker hint |

**Submit button:** `Submit: "label"` — shown as a full-width primary button.

---

### List

Renders records fetched live from `/api/data/<entity>`. **Automatically refreshes after any form submit on the same screen.**

```
List: perfume as cards
  - name
  - brand
  - price: money
  - description
```

| Style | Renders as | Best for |
|---|---|---|
| `as cards` | Card grid, one card per record | **Products, items with price** |
| `as table` | Data table | Orders, transactions |
| `as rows` | Compact list rows | Notifications, feed items |

> **Product cards:** When a list entity has a field named `price`, `cost`, `amount`, or `total`, the compiler automatically renders a **product card** with: a gradient image placeholder, the name as the card title, the price in bold accent color, and a primary CTA button. No extra configuration needed — just put `price` in the field list.

> **Money formatting:** Fields named `price`, `cost`, `amount`, `total`, `subtotal`, `revenue`, `fee`, `balance` are automatically formatted as `$X.XX` in cards, rows, and tables.

---

### Stats

A row of KPI metric tiles. Best for account overview and dashboard screens.

```
Stats: [total_orders "Orders", revenue "Revenue" money, pending "Pending"]
```

Each stat: `<field> "<label>"` or `<field> "<label>" <format>`.
Formats: `money`, `date`, `number`, `text`.

---

### Empty

Shown when a list has no records. Place it after the `List:` component on the same screen — the compiler hides it when data is present and shows it when the list is empty.

```
Empty: "No perfumes in the catalog yet." cta "Add your first perfume"
```

---

### Text

A standalone heading or paragraph.

```
Text: "Why choose us" size h2 align center
Text: "We source our fragrances from the world's finest houses."
Text: "500+ fragrances · 10,000 happy customers" size small align center
```

| Part | Options | Default |
|---|---|---|
| `"text"` | Content (required) | — |
| `size` | `h1` · `h2` · `h3` · `h4` · `body` · `large` · `lead` · `small` | `body` |
| `align` | `left` · `center` · `right` | left |

---

### Columns

A responsive grid of feature/benefit tiles.

```
Columns: 3
  - icon "🚚" title "Free delivery" body "On orders over $50"
  - icon "🔒" title "Secure checkout" body "256-bit SSL encryption"
  - icon "↩️" title "Easy returns" body "30 days, no questions"
```

| Part | Description |
|---|---|
| `N` after `Columns:` | Number of columns: 1, 2, 3, or 4 |
| `icon "emoji"` | Emoji icon for the tile |
| `title "text"` | Bold tile heading |
| `body "text"` | Supporting description |

---

### CTA

A full-width call-to-action banner.

```
CTA: heading "Find your signature scent" sub "Join 10,000+ customers" button "Shop now"
CTA: heading "Ready to ship?" button "Start free trial" bg accent
```

| Part | Options | Default |
|---|---|---|
| `heading "text"` | Large heading | — |
| `sub "text"` | Subtitle | — |
| `button "label"` | CTA button label | — |
| `bg` | `primary` · `accent` · `dark` · `surface` | `primary` |

---

### Divider

A horizontal rule, optionally with a label.

```
Divider:
Divider: "or"
Divider: "our process"
```

---

### Testimonials

A grid of customer reviews.

```
Testimonials:
  - "Best perfume I've ever bought!" author "Jane D." rating 5
  - "Incredible selection and fast shipping." author "Marc T." rating 4
  - "The subscription box is a game changer." author "Sofia L." rating 5
```

| Part | Description |
|---|---|
| `"text"` | The quote text |
| `author "name"` | Attribution |
| `rating N` | Star rating 1–5 (optional) |

---

### Pricing

Tier-based pricing cards.

```
Pricing:
  - name "Starter" price 0 features "5 samples/month, Standard selection"
  - name "Pro" price 29 features "Unlimited, Premium selection, Free shipping" highlight
  - name "Enterprise" price 99 features "Custom blend, Dedicated advisor" cta "Contact us"
```

| Part | Description |
|---|---|
| `name "text"` | Tier name |
| `price N` | Price as integer |
| `period "text"` | Price suffix; default `/mo` |
| `features "f1, f2, f3"` | Comma-separated feature list |
| `highlight` | Mark as the recommended tier (accent style) |
| `cta "label"` | Button label; default `Get started` |
| `currency "€"` | On the `Pricing:` line itself; default `$` |

---

### Steps

A numbered process list.

```
Steps:
  - "Browse our curated collection"
  - "Add your favorites to the cart"
  - "We ship within 24 hours"
```

---

### Image

A full-width image placeholder (or real image with `src`).

```
Image: alt "Perfume collection" aspect 16/9
Image: alt "Founder portrait" aspect 1/1
Image: src "/images/hero.jpg" alt "Hero image" aspect 21/9
```

| Part | Options | Default |
|---|---|---|
| `alt "text"` | Placeholder label or img alt | — |
| `aspect` | `16/9` · `4/3` · `1/1` · `3/2` · `21/9` | `16/9` |
| `src "url"` | Real image URL (optional) | — |

---

### SVG

Embed a custom SVG graphic or reference an external SVG file. Two modes: **inline** (paste raw markup) and **src** (reference a file or URL).

#### Inline SVG

Leave `SVG:` value blank and paste the raw SVG on the next lines, indented:

```
SVG:
  <svg viewBox="0 0 80 80" fill="none" stroke="currentColor" stroke-width="3"
       width="80" height="80" xmlns="http://www.w3.org/2000/svg">
    <circle cx="40" cy="40" r="32"/>
    <polyline points="26,40 36,52 54,30"/>
  </svg>
```

Use inline SVG for: brand logos, custom icons, illustrations, decorative shapes. Colors set on the `<svg>` element via `fill` and `stroke` attributes override the page theme.

#### Reference (file or URL)

```
SVG: src "https://upload.wikimedia.org/wikipedia/commons/..." alt "Logo" width 180 height 60
SVG: src "/assets/hero-illustration.svg" alt "Hero graphic" aspect 16/9
SVG: src "data:image/svg+xml,%3Csvg…" alt "Icon" width 32 height 32
```

| Part | Description |
|---|---|
| `src "url"` | URL, absolute path, or `data:` URI to an SVG file |
| `alt "text"` | Alt text for accessibility (also used as placeholder label) |
| `width N` | Display width in pixels |
| `height N` | Display height in pixels |
| `aspect` | `16/9` · `4/3` · `1/1` · `3/2` · `21/9` — makes it full-container-width |

When `aspect` is set, the SVG stretches to fill the full container width (like `Image:`).

---

### Trust

A subtle reassurance line — use below checkout forms or at the bottom of landing screens.

```
Trust: "Free shipping on orders over $50 · 30-day returns · Secure checkout"
```

---

### Wizard

A multi-step form with a progress bar and step indicators. Each step reveals a set of fields; the user moves through steps with Back/Next and submits the whole payload at the end.

```
Wizard: configure_pc
  - "CPU & Memory" cpu_sku, ram_size, ram_type
  - "Storage" ssd_size, ssd_type
  - "Power & Case" psu_wattage, case_style
Submit: "Complete Build"
```

Each sub-item defines one step:
- The quoted string is the step label shown in the indicator bar.
- The comma-separated field names after the label are the inputs shown in that step.
- `Submit:` sets the final button label (default: `Submit`).

The completed form POSTs all collected data to `/api/<flow>`.

> **When to use:** Multi-step checkout, PC configurator, insurance questionnaire, onboarding wizard — any flow with too many fields for a single scrollable form.

---

### Model3D

Embeds a 3D model viewer using Google's `<model-viewer>` web component. If no `src` is provided, renders an animated spinning CSS cube as a placeholder.

```
Model3D: src "/models/laptop.glb" alt "Laptop 3D View" auto-rotate float
Model3D: src "/models/sneaker.glb" alt "Sneaker" poster "/preview.jpg"
Model3D: alt "Product Preview"           ← CSS cube placeholder
```

| Part | Description |
|---|---|
| `src "url"` | Path or URL to a `.glb` or `.gltf` 3D model file |
| `alt "text"` | Accessibility text and placeholder label |
| `auto-rotate` | Enable automatic rotation (default: on; use `no-rotate` to disable) |
| `float` | Add a gentle floating up/down animation |
| `poster "url"` | Image shown before the model loads |

> **File hosting:** 3D model files must be hosted separately. In development, place them in the project's `public/` or `static/` folder and reference them by path.

---

### Cascading / dynamic Form selects

A form field can load its options dynamically from a backend entity and optionally filter based on another field's value:

```
Form: configure_pc
  - cpu_sku: choice from cpu
  - motherboard_sku: choice from motherboard where socket == cpu_sku.socket_type
  - ram_size: select label "RAM Size"
Submit: "Add to Cart"
```

| Syntax | Effect |
|---|---|
| `field: choice from entity` | Renders a `<select>` populated by `/api/data/<entity>` on load |
| `field: choice from entity where A == dep_field.B` | Also filters: when `dep_field` changes, only options where `item.A == depValue` remain |

> **Filter expression:** `socket == cpu_sku.socket_type` means "keep items where `item.socket` equals the currently-selected `cpu_sku` value's `socket_type` property." The right-hand side is always `<depends_on_field>.<property_name>`.

---

### Layout: split-preview

A two-column layout where the left panel holds controls (forms, headers) and the right panel shows a live detail preview of whichever row is clicked in a list.

```
## Screen: catalog
Layout: split-preview
Preview: product
Header: "Product Catalog" action "Add Product"
List: product as table
  - sku
  - name
  - price
```

- `Preview: entity` — names the entity whose fields appear in the preview panel (optional; auto-detected from the `List:` component if omitted).
- On desktop: left/right split. On mobile: stacks vertically.
- Click any table row or card to populate the detail panel on the right.

---

## Complete examples

### Ecommerce storefront — landing + catalog + checkout

```markdown
Design: danta/0.1

System: perfume_store

## Theme
Brand: "Parfumerie"
Colors: primary "#be185d", accent "#9333ea"
Font: "Inter"
Radius: large
Mode: light

## Screen: home
Layout: hero
Hero: heading "Discover your signature scent.", sub "Curated fragrances from the world's finest houses.", cta "Shop the collection"
Trust: "Free delivery · Authentic products · 30-day returns"

## Screen: catalog
Layout: full
Header: "Our Collection" action "Filter"
List: perfume as cards
  - name
  - brand
  - price: money
  - description
Empty: "No perfumes in the catalog yet." cta "Check back soon"

## Screen: add_perfume
Layout: centered card
Header: "Add a Perfume"
Form: add_perfume
  - name: placeholder "e.g. Bleu de Chanel"
  - brand: placeholder "House name"
  - price: money
  - description: placeholder "Fragrance notes, intensity…"
Submit: "Add to catalog"

## Screen: checkout
Layout: centered
Hero: heading "Secure checkout", sub "Your cart is reserved for 15 minutes"
Form: place_order
  - customer_email: placeholder "you@example.com"
  - perfume_id: hidden
  - quantity: placeholder "1"
Submit: "Place order →"
Trust: "256-bit encryption · No hidden fees · Cancel anytime"

## Screen: my_orders
Layout: full
Header: "My Orders"
List: order as table
  - order_id: label "Order #"
  - customer_email: label "Email"
  - total: money
  - status
Empty: "No orders yet." cta "Browse catalog"
```

### SaaS app — dashboard + form

```markdown
Design: danta/0.1

System: help_desk

## Theme
Brand: "HelpDesk"
Colors: primary "#6366f1", accent "#06b6d4"
Radius: medium

## Screen: dashboard
Layout: dashboard
Header: "Support Tickets"
Stats: [open_count "Open", resolved_count "Resolved", avg_response "Avg. response"]
List: ticket as rows
  - ticket_id: label "Ticket #"
  - subject
  - status: badge
  - created_at: date
Empty: "No open tickets. All clear! 🎉"

## Screen: new_ticket
Layout: centered card
Hero: heading "Submit a ticket", sub "We typically respond within 2 hours"
Form: create_ticket
  - subject: placeholder "What do you need help with?"
  - description: placeholder "Describe the issue…"
  - priority: segmented "Low | Medium | High"
Submit: "Submit ticket"
Trust: "Average first response: 2 hours"
```

---

## Rules checklist

- [ ] First line: `Design: danta/0.1`
- [ ] `System:` matches the backend spec name exactly
- [ ] Design spec covers **customer-facing screens only** (not admin/internal)
- [ ] Every `Form:` flow name exists in the system context and has an HTTP trigger
- [ ] Every `List:` entity name exists in the system context
- [ ] Every field in `Form:` sub-lines exists in that flow's inputs
- [ ] Every field in `List:` sub-lines exists in that entity
- [ ] Each screen has at least one component
- [ ] `Stats:` fields come from entity fields or flow outputs (not invented names)
- [ ] `Radius:` is one of: none, small, medium, large, rounded
- [ ] `Mode:` is one of: light, dark, auto
- [ ] Color values are valid hex strings (`"#rrggbb"` or `"#rgb"`)
- [ ] `Columns:` count is 1–4
- [ ] `Pricing:` prices are integers (no decimals); money is always in whole units
- [ ] `List: entity as cards cols N` — N is 1–6
- [ ] `SVG:` inline — raw `<svg>` markup indented on the next lines; leave the `SVG:` value blank
- [ ] `SVG: src "..."` — valid URL, path, or `data:image/svg+xml` URI
- [ ] `Animations:` values are from: `scroll-reveal`, `stagger`, `counter`, `parallax`, `typewriter`
- [ ] `Style:` is one of: `default`, `cyberpunk`, `glass`, `minimal`, `bold`
- [ ] `Background:` is one of: `particles`, `mesh-gradient`, `dot-grid`, `circuit`, `video src "url"`
- [ ] `Interactions:` values are from: `card-tilt`, `button-glow`, `ripple`, `magnetic-links`, `parallax-cards`
- [ ] `Wizard:` flow name is an HTTP flow in the system context; sub-items are `"Step Label" field1, field2`
- [ ] `Model3D:` with `src` requires a `.glb` or `.gltf` path/URL; without `src` renders a CSS placeholder
- [ ] `choice from entity` fields reference entity names that exist in the system context
- [ ] `Layout: split-preview` — `Preview:` is optional (auto-detected from the `List:` component)
- [ ] Hero screens use `Layout: hero` or `Layout: full`
- [ ] CTA banners use `bg primary` (default), `bg accent`, `bg dark`, or `bg surface`
