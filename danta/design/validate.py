"""validate.py — Cross-check a DesignSpec against the compiled backend context.

Checks that every flow, entity, and field name in the design spec actually
exists in the backend. Adds error strings to spec.errors in place.
"""

from danta.design.model import DesignSpec, FormComponent, ListComponent, StatsComponent


def validate(spec: DesignSpec, ctx: dict) -> DesignSpec:
    """Validate spec against backend context. Mutates spec.errors. Returns spec."""
    flows    = ctx.get('flows', {})
    entities = ctx.get('entities', {})
    screens  = {s['name'] for s in ctx.get('screens', [])}

    for screen in spec.screens:
        for comp in screen.components:
            if isinstance(comp, FormComponent):
                if comp.flow and comp.flow not in flows:
                    spec.errors.append(
                        f'Screen "{screen.name}" Form: flow "{comp.flow}" not found '
                        f'(available: {", ".join(sorted(flows))})'
                    )
                elif comp.flow:
                    valid_inputs = {f['name'] for f in flows[comp.flow]['inputs']}
                    for fh in comp.fields:
                        if fh.name not in valid_inputs:
                            spec.errors.append(
                                f'Screen "{screen.name}" Form "{comp.flow}": '
                                f'field "{fh.name}" not in flow inputs '
                                f'({", ".join(sorted(valid_inputs))})'
                            )

            elif isinstance(comp, ListComponent):
                if comp.entity and comp.entity not in entities:
                    spec.errors.append(
                        f'Screen "{screen.name}" List: entity "{comp.entity}" not found '
                        f'(available: {", ".join(sorted(entities))})'
                    )
                elif comp.entity:
                    valid_fields = {f['name'] for f in entities[comp.entity]}
                    for fh in comp.fields:
                        if fh.name not in valid_fields:
                            spec.errors.append(
                                f'Screen "{screen.name}" List "{comp.entity}": '
                                f'field "{fh.name}" not in entity '
                                f'({", ".join(sorted(valid_fields))})'
                            )

            elif isinstance(comp, StatsComponent):
                all_fields = {f['name'] for fields in entities.values() for f in fields}
                all_outputs = {k for f in flows.values() for k in f.get('outputs', [])}
                available = all_fields | all_outputs
                for fh in comp.items:
                    if fh.name and available and fh.name not in available:
                        spec.errors.append(
                            f'Screen "{screen.name}" Stats: '
                            f'field "{fh.name}" not found in any entity or flow output'
                        )

    return spec
