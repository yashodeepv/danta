# Danta

**Exact business intent in, verified software out.**

Ganapati broke off his tusk (*danta*, दन्त) to write the Mahabharata as Vyasa
dictated it, on one condition: he would not write a line he did not
understand. Danta keeps the same pact. A spec it cannot understand exactly is
rejected, with line numbers. A spec it understands is written out whole, in
three languages, and every line is checked before you get it.

## What it does

1. **An analyst writes a spec.** A person or an LLM writes Danta Spec: a
   short, exact document of business flows (triggers, calls, rules, records,
   notifications, topics, batch jobs) and the screens people use.
   `danta prompt` prints the prompt that teaches an LLM the language.
2. **Danta checks it.** The compiler turns the spec into IR2, a typed flow
   graph, and rejects anything ambiguous with the rule broken and the line.
3. **Business people review flowcharts, not code.** Spec Studio draws every
   flow and previews every screen.
4. **Every path is simulated.** Danta invents inputs until each branch of
   each flow has run. Those runs become the tests.
5. **Whole projects are generated and verified.** Each project runs its own
   tests before you get it, in three flavours:
   - Python: FastAPI
   - JavaScript: Express
   - Java: Spring Boot

   Every project comes with a React app, Swagger UI, MongoDB, RabbitMQ, email,
   Docker Compose, and Kubernetes manifests with a deployment guide for GKE,
   EKS, AKS and Cloud Run.

## Quick start

```bash
pip install -e .
danta check    danta/spec/examples/help_desk.spec.md
danta simulate danta/spec/examples/help_desk.spec.md
danta build    danta/spec/examples/help_desk.spec.md --out dist --verify
cd dist/python/help-desk && docker compose up --build    # web app on :3000, API docs on :8000/docs
danta studio                                             # Spec Studio on http://127.0.0.1:8765
```

Python 3.11+. Building projects needs nothing else. Verifying them needs Node,
Maven and a JDK. Formatting them uses ruff, prettier and google-java-format
when they are installed. Running the stacks needs Docker.

## The language

[`danta/spec/LANGUAGE.md`](danta/spec/LANGUAGE.md) is the reference.
[`danta/spec/examples/`](danta/spec/examples/) has complete systems: order
checkout, leave requests, an invoice batch job, and a help desk with screens.

## Tests

```bash
python -m unittest discover -s danta/tests -t .
FLOW_STACK_TESTS=1 python -m unittest danta.tests.test_stack   # full Docker stacks, slow
```

## Origins

Danta grew inside [baby-programmer](https://github.com/yashodeepv/baby-programmer-small-language-model),
a small model that learns to program the way a person does. Its expression
core (`danta/core/`) began there as the IR of that model.

Prose values in a spec, logic stated as intent rather than as an exact
expression, are left for a logic model to program. baby-programmer is meant
to be that model. It plugs in through the compiler's `intent` hook:

```python
compile_spec(text, intent=lambda prose: exact_expression_or_None)
```
