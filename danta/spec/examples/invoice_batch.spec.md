Spec: danta/0.1

# System: invoice-chaser
Chases overdue invoices in two stages. A nightly batch finds the open invoices and
puts each one on a queue; a worker takes them one at a time, reminds the customer,
escalates the very late ones and marks them reminded. This is the batch pattern:
schedule, query, publish each, and a topic-triggered flow per item.

## Constants
- LATE_DAYS = 30
- COLLECTIONS = "#collections"

## Entities
- invoice: invoice_id str, customer_email str, amount int, days_late int, status str

## Flow: find_overdue
Intent: Every night, queue every open invoice for a reminder and report how many.
Trigger: schedule "0 2 * * *" with run_date str
Mode: async
Steps:
1. [Find open invoices] Query invoice as open_invoices where status = "open".
2. [Anything to chase?] If `len(open_invoices) == 0`:
   a. [Nothing open] Stop.
3. [Count them] Compute batch:
   - queued: `len(open_invoices)`
4. [Queue each invoice] Publish each open_invoices to topic "invoice.reminder".
5. [Report the batch] Slack COLLECTIONS: "{run_date}: {queued} invoices queued for reminders".

## Flow: send_reminder
Intent: Remind one customer about one overdue invoice, escalating the very late ones.
Trigger: topic invoice.reminder with invoice_id str, customer_email str, amount int, days_late int, status str
Mode: async
Steps:
1. [Still open?] Validate: `status == "open"`. Otherwise stop with error "invoice is no longer open".
2. [Email the customer] Email customer_email: "Invoice {invoice_id} for {amount} cents is {days_late} days overdue".
3. [Very late?] If `days_late > LATE_DAYS`:
   a. [Tell collections] Slack COLLECTIONS: "Invoice {invoice_id} is {days_late} days late".
4. [Mark reminded] Update invoice: invoice_id, customer_email, amount, days_late, status = "reminded".
5. [Announce it] Publish to topic "invoice.reminded": invoice_id, days_late.
6. [Done] Stop.
