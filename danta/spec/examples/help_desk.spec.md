Spec: danta/0.1

# System: help-desk
Customers raise support tickets from a web page; agents work through the
open tickets and close them. A complete app: two flows, and the two screens
that drive them.

## Constants
- SUPPORT_CHANNEL = "#support"

## Entities
- ticket: ticket_id str, customer_email str, subject str, priority str, status str

## Flow: open_ticket
Intent: Record a new support ticket, alert the support channel about urgent ones, and acknowledge it to the customer.
Trigger: POST /tickets with ticket_id str, customer_email str, subject str, priority str
Mode: sync
Steps:
1. [Has a subject?] Validate: `subject != ""`. Otherwise stop with error "a ticket needs a subject".
2. [Save the ticket] Save ticket: ticket_id, customer_email, subject, priority, status = "open".
3. [Urgent?] If `priority == "urgent"`:
   a. [Tell support] Slack SUPPORT_CHANNEL: "Urgent ticket {ticket_id}: {subject}".
4. [Acknowledge it] Email customer_email: "We have your ticket {ticket_id}: {subject}".
5. [Ticket open] Respond with ticket_id, status = "open".

## Flow: close_ticket
Intent: Mark a ticket closed and tell the customer.
Trigger: POST /tickets/close with ticket_id str, customer_email str, subject str, priority str
Mode: sync
Steps:
1. [Close it] Update ticket: ticket_id, customer_email, subject, priority, status = "closed".
2. [Tell the customer] Email customer_email: "Ticket {ticket_id} is closed: {subject}".
3. [Ticket closed] Respond with ticket_id, status = "closed".

## Screen: new_ticket
Title: Raise a ticket
Shows: form for open_ticket
Fields:
- ticket_id "Ticket number": generated
- customer_email "Your email": email
- subject "What went wrong?": long text
- priority "Priority": choice of "low", "normal", "urgent"
Submit: "Raise ticket"
After: show "Ticket {ticket_id} is {status}", then go to open_tickets

## Screen: open_tickets
Title: Open tickets
Shows: list of ticket
Columns:
- ticket_id "Ticket"
- customer_email "Customer"
- subject "Subject"
- priority "Priority"
Filter: status = "open"
Actions:
- "Close": close_ticket with ticket_id, customer_email, subject, priority
