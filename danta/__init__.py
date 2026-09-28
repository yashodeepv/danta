"""Danta - exact business intent in, verified software out.

Ganapati broke off his tusk (danta) to write the Mahabharata as Vyasa spoke it,
on one condition: he would not write a line he did not understand. Danta keeps
the same pact. A spec it cannot understand exactly is rejected, line by line;
a spec it understands is written out whole, and every line is checked.

    danta/spec/     Danta Spec: the language (LANGUAGE.md), its compiler to IR2, screens
    danta/ir2/      IR2: typed flow graphs (trigger, call, compute, validate, branch,
                    parallel, persist, notify, query, publish, end)
    danta/core/     the expression core IR2 builds on: nodes, semantics, text form
    danta/check/    the verifier: structure, dataflow and type rules
    danta/sim/      the reference simulator; its runs are every project's tests
    danta/gen/      coverage synthesis (inputs that take every path), random flows
    danta/codegen/  Python, JavaScript and Java compilers, and whole projects:
                    FastAPI / Express / Spring Boot, React, Docker, Kubernetes
    danta/ui/       the screen model a spec's ## Screen: sections compile to
    danta/app/      Spec Studio: flowcharts, test runs, screens and projects in a browser
"""
