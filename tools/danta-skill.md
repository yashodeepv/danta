# Danta Spec — LLM writing guide

You help users write Danta specs. A spec is a structured Markdown file that compiles deterministically to Python, JavaScript, and Java — no model involved in the compiler. Follow the grammar exactly; the compiler is strict and case-sensitive.

---

## File structure (order is fixed)

```
Spec: danta/0.1

# System: <name>
<description>

## Constants      ← optional, must come before flows
## Entities       ← optional, must come before flows
## Services       ← optional, must come before flows
## Flow: <name>   ← one or more
## Screen: <name> ← optional, after all flows
```

Lines starting with `>` are ignored anywhere (use for comments).

---

## Spec header

```
Spec: danta/0.1

# System: shop-orders
Takes orders over HTTP, charges them, then confirms.
```

- `Spec: danta/0.1` must be the very first non-blank line.
- System name: `[a-z][a-z0-9_-]*` (lowercase, hyphens allowed).
- Description: free prose on the lines that follow until the next `##` heading.
- A spec with no `# System:` or no `## Flow:` is an error.

---

## Constants

```
## Constants
- MAX_ITEMS = 100
- SALES_CHANNEL = "#sales"
- ENABLED = true
```

- Name: `UPPER_SNAKE_CASE` (`[A-Z][A-Z0-9_]*`).
- Value: integer, `"double-quoted string"`, or `true`/`false`.
- Referenced by name in any value slot across all flows.

---

## Entities

```
## Entities
- order: order_id str, customer_email str, total int, status str
- item: item_id str, order_id str, sku str, qty int
```

- Entity name: `[a-z][a-z0-9_]*`.
- Field types: `int`, `str`, `bool`, `list of T`, `(field type, ...)`, or another entity name.
- First field is the **key** — the only field required by `Delete`.
- `Save` and `Update` require **all** fields.

---

## Services

```
## Services
- payments.charge(order_id str, amount int) -> (charge_id str, status str)
- inventory.reserve(sku str, qty int) -> (reserved bool)
```

- Syntax: `- service.operation(params) -> (outputs)`.
- `service` and `operation`: `[a-z][a-z0-9_]*`.
- A service with multiple operations appears on separate lines.

---

## Flows

```
## Flow: order_checkout
Intent: Reject empty orders, price and charge them, then confirm.
Trigger: POST /orders with order_id str, customer_email str, tier str, items list of (sku str, amount int)
Mode: sync
Steps:
1. ...
```

- Flow name: `[a-z][a-z0-9_]*`, unique across the spec.
- `Intent:` — free prose, not compiled; shown in the Studio.
- `Mode: sync` — HTTP only; the caller waits for a response.
- `Mode: async` — fire-and-forget; required for schedule/event/topic.

### Trigger forms

| Form | Example |
| --- | --- |
| HTTP | `POST /orders with order_id str, amount int` |
| Event | `event payment_received with invoice_id str, amount int` |
| Schedule | `schedule "0 2 * * *" with run_date str` |
| Topic | `topic invoice.reminder with invoice_id str` |

HTTP methods: `GET`, `POST`, `PUT`, `DELETE`. Path must start with `/`.
`with <fields>` is optional when the trigger carries no payload.
Payload fields: access as `input.field` or just `field` when unambiguous.

---

## Steps

Top-level steps are numbered: `1.`, `2.`, `3.`, ...
Sub-steps under `If` or `In parallel` are lettered: `a.`, `b.`, `c.`, ...
Numbering must be sequential — gaps are an error.

Optional title in `[brackets]` before the keyword:
```
1. [Check items] Validate: `len(items) > 0`. Otherwise stop with error "no items".
```

Steps can continue onto the next line if it is indented.

---

## Validate

Checks a condition and stops the flow on failure.

```
1. Validate: `amount > 0`. Otherwise stop with error "amount must be positive".
2. Validate: `len(items) > 0`. Otherwise stop with error "no items", responding with order_id.
3. Validate: `active`. Otherwise fail with "account is inactive".
```

- **Syntax:** `Validate: <cond>. Otherwise stop with error "<msg>" [, responding with <fields>]`
- `Otherwise fail with "<msg>"` — async variant (no response body).
- `responding with order_id, total` adds fields alongside the built-in `reason`.

---

## Compute

Assigns named computed values, accessible later as `<name>.<var>`.

```
2. [Price it] Compute pricing:
   - subtotal: `sum(items.amount)`
   - discount: `subtotal / 10 if tier == "gold" else 0`
   - total: `subtotal - discount`
```

- **Syntax:** `Compute <name>:` followed by `- <var>: <value>` lines.
- Name must be unique. Variables computed in order; later ones can reference earlier ones.
- Access as `pricing.subtotal`, `pricing.total`, etc.

---

## Call

Invokes an external service declared under `## Services`.

```
3. [Charge] Call payments.charge with order_id, amount = pricing.total. Retry 2 times. On failure stop with error "payment failed", responding with order_id.
4. Call inventory.reserve as res with sku = item.sku, qty = 1.
```

- **Syntax:** `Call <service>.<op> [as <name>] [with <args>] [. Retry N time(s).] [. On failure stop with error "<msg>" [, responding with <fields>].]`
- `with param` — shorthand for `with param = param`.
- `Retry` accepts 0–3.
- Outputs accessed as `<name>.<field>`; `<name>` defaults to the operation name.

---

## Query

Loads a list of entity records.

```
5. Query invoice as open_invoices where status = "open".
```

- **Syntax:** `Query <entity> as <name> [where <field> = <value>, ...]`
- Result is a list. Use `len(open_invoices)`, `open_invoices.field` (list of values), or `Publish each` over it.

---

## Publish

Sends a message to a topic.

```
6. Publish to topic "order.placed": order_id = order_id, total = pricing.total.
6. Publish each open_invoices to topic "invoice.reminder".
```

- First form: a single message with explicit fields.
- Second form: one message per item in the list.

---

## If

Conditional branch.

```
7. [Large order?] If `pricing.total >= LARGE_ORDER`:
   a. [Alert sales] Slack SALES_CHANNEL: "Large order {order_id}: {pricing.total} cents".
Otherwise:
   a. Stop.
```

- **Syntax:** `If <condition>:` with lettered sub-steps underneath.
- `Otherwise:` (at the same indent as `If`) holds the false branch; omitting it means the false path continues to the next step.
- Both branches rejoin at the step after the `If`.

---

## In parallel

Runs two or more sub-steps concurrently and waits for all.

```
8. In parallel:
   a. Email customer_email: "Order {order_id} confirmed. Total: {pricing.total}".
   b. Save order: order_id, total = pricing.total, status = "confirmed".
```

- Each branch is **exactly one step**.
- Branches cannot stop the flow, use `Respond with`, or contain `If` / `In parallel`.
- Outputs of parallel steps are not accessible in subsequent steps.

---

## Save / Update / Delete

```
9.  Save order: order_id, total = pricing.total, status = "new".
10. Update order: order_id, status = "shipped".
11. Delete invoice where invoice_id = inv.invoice_id.
```

- `Save` (insert) and `Update` require **every field**.
- `Delete` takes only the first (key) field, with `where`.
- Entity must be declared under `## Entities`.

---

## Notifications

```
12. Email customer_email: "Your order {order_id} is confirmed. Total: {pricing.total}".
13. Slack SALES_CHANNEL: "New order {order_id} from {customer_email}".
14. SMS phone: "Your code is {code}".
15. Webhook callback_url: "done".
```

- **Syntax:** `<Channel> <to>: <message>`
- Channels: `Email`, `Slack`, `SMS`, `Webhook`
- `<to>` and `<message>` are value slots (name, path, template, or backtick expression).

---

## Respond with

Ends a sync flow with a success response.

```
16. Respond with order_id, charge_id, total = pricing.total.
```

- **Syntax:** `Respond with <field> [= <value>], ...`
- Bare `order_id` = shorthand for `order_id = order_id`.
- Only valid in `Mode: sync`.

---

## Stop

```
17. Stop.
18. Stop with error "not found".
19. Stop with error "payment failed", responding with order_id.
```

- Bare `Stop` ends with status `ok`.
- `Stop with error` ends with status `error`; in sync flows sends a `reason` field (+ `responding with` extras).

---

## Values and expressions

Any value slot accepts five forms:

| Form | Example | Notes |
| --- | --- | --- |
| Name or path | `order_id`, `pricing.total` | Resolves to a declared field |
| Constant | `LARGE_ORDER` | UPPER_SNAKE_CASE |
| Integer literal | `42`, `-7` | |
| String template | `"Order {order_id} confirmed"` | `{name}` interpolates |
| Exact expression | `` `len(items) > 0` `` | Backtick-wrapped |

Plain English prose is accepted but marks the slot as **intent** — a placeholder that needs an exact expression to run.

### Exact expression operators

- **Arithmetic:** `+`, `-`, `*`, `/` (truncating), `%`
- **Comparison:** `==`, `!=`, `<`, `<=`, `>`, `>=`
- **Boolean:** `and`, `or`, `not`
- **Conditional:** `value if cond else other`
- **Functions:** `len(x)`, `abs(x)`, `sum(list)`, `product(list)`, `min(list)`, `max(list)`, `count(list)`
- **Range:** `sum(range(lo, hi) ...)` — reduce over integer range instead of a list
- **Field pluck:** `items.amount` on `list of (sku str, amount int)` → `list of int`

**Reduction modifiers** (chained after a reduction function):
`where > k` · `where < k` · `where even` · `where odd` · `where divisible by k` · `each * k` · `each + k` · `each squared`

Examples: `` `sum(xs.v where > 0)` `` · `` `count(items each * 3 where even)` `` · `` `sum(range(1, 10) each squared)` ``

**String templates:** `{name}` or `{CONST}` interpolates; `{{` and `}}` are literal braces.

---

## Screens (optional)

```
## Screen: checkout
Title: Place an Order
Shows: form for order_checkout
Fields:
- order_id "Order ID": generated
- customer_email "Email"
- tier "Tier"
Submit: Place order
After: Your order has been placed.
```

| Property | Type | Notes |
| --- | --- | --- |
| `Title:` | required | Display title |
| `Shows:` | required | `form for <flow>` or `list of <entity>` |
| `Fields:` | list | `- <field> "Label" [: generated]` |
| `Columns:` | list | `- <field> "Label"` (for list screens) |
| `Actions:` | list | `- <name> "Label"` |
| `Submit:` | optional | Button label |
| `After:` | optional | Success message |
| `Filter:` | optional | Condition to pre-filter a list |

---

## Common patterns

### Validation → compute → respond

```
Steps:
1. Validate: `len(items) > 0`. Otherwise stop with error "cart is empty".
2. Compute totals:
   - subtotal: `sum(items.price)`
   - tax: `subtotal / 10`
   - total: `subtotal + tax`
3. Respond with total, tax.
```

### Nightly batch — queue each item

```
## Flow: find_overdue
Intent: Every night, queue every open invoice for a reminder.
Trigger: schedule "0 2 * * *" with run_date str
Mode: async
Steps:
1. Query invoice as open_invoices where status = "open".
2. If `len(open_invoices) == 0`:
   a. Stop.
3. Publish each open_invoices to topic "invoice.reminder".
4. Slack CHANNEL: "{run_date}: {len(open_invoices)} invoices queued".
```

### Call with retry and failure response

```
3. [Charge] Call payments.charge with order_id, amount = totals.total. Retry 2 times. On failure stop with error "payment failed", responding with order_id.
```

### Parallel save + notify

```
5. In parallel:
   a. Email customer_email: "Order {order_id} confirmed. Total: {totals.total}".
   b. Save order: order_id, total = totals.total, charge_id = charge.charge_id, status = "confirmed".
6. Respond with order_id, charge_id = charge.charge_id, total = totals.total.
```

---

## Cross-language rules

This spec compiles to **Python, JavaScript, and Java simultaneously**. Every name
and expression must be valid in all three.

### Names
- `snake_case` only for flows, entities, services, and fields. No hyphens, no camelCase.
- Never use these as names (reserved in at least one target):
  - **Python**: `class`, `type`, `list`, `id`, `input`, `print`, `filter`, `map`, `range`, `format`, `next`, `iter`, `open`
  - **Java**: `class`, `interface`, `package`, `import`, `new`, `default`, `extends`, `implements`, `instanceof`, `final`
  - **JavaScript**: `function`, `var`, `let`, `const`, `delete`, `yield`, `typeof`, `instanceof`, `export`, `import`
- Entity fields named `id` → use `<entity>_id` instead (e.g. `order_id`, `user_id`).

### Numbers
- Use `int` for **all** whole numbers, including money (store as cents).
- **Never** use `float` for currency — it causes silent rounding bugs in all three targets.
- Java `int` holds up to ~2.1 billion. The codegen widens automatically for large values; always declare as `int`.

### Expressions
- Write expressions as **valid Python**. The Python codegen uses them verbatim; Java and JS translate automatically.
- Integer division: `//` not `/` → `subtotal // 10`, not `subtotal / 10`
- Boolean literals: `True` / `False` (Python capitalisation) → codegen translates to `true`/`false`
- String literals inside expressions: double quotes only → `"gold"`, not `'gold'`

---

## Rules checklist

- [ ] First line: `Spec: danta/0.1`
- [ ] System name: `[a-z][a-z0-9_-]*`
- [ ] Flow/entity/service names: `[a-z][a-z0-9_]*` (no hyphens)
- [ ] Constant names: `UPPER_SNAKE_CASE`
- [ ] Top-level steps numbered `1.`, `2.`, ...; sub-steps lettered `a.`, `b.`, ...
- [ ] Numbering sequential — no gaps
- [ ] Exact expressions wrapped in backticks: `` `total > 0` ``
- [ ] String literals in expressions use double quotes: `"gold"`
- [ ] HTTP triggers → `Mode: sync` when using `Respond with`; `Mode: async` otherwise
- [ ] Schedule / event / topic triggers → always `Mode: async`
- [ ] `Save` and `Update` supply every entity field
- [ ] `Delete` uses only the key field with `where`
- [ ] `In parallel` branches: one step each, no Stop/Respond/If/In parallel
- [ ] Constants, Entities, Services declared before the first `## Flow:`
- [ ] No reserved words used as names (Python / Java / JavaScript)
- [ ] Money and counts are `int`, never `float`
- [ ] Expressions use `//` for integer division, `True`/`False` for booleans
