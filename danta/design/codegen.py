"""codegen.py — Generate a single-page HTML preview from a DesignSpec + backend context.

The output is a self-contained HTML file (no external dependencies) that renders
each screen as a realistic UI.  List screens fetch live data from /api/data/<entity>.
Forms submit to /api/<path> and refresh list screens on success.
"""

from danta.design.model import (
    ColumnsComponent, CTAComponent, DesignSpec, DividerComponent,
    EmptyComponent, FormComponent, HeaderComponent, HeroComponent,
    ImageComponent, ListComponent, Model3DComponent, PricingComponent,
    StatsComponent, StepsComponent, SVGComponent, TestimonialsComponent,
    TextComponent, Theme, TrustComponent, WizardComponent,
)

# ---------- helpers --------------------------------------------------------


def _esc(s: str) -> str:
    return s.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;')


def _title(name: str) -> str:
    return name.replace('_', ' ').title()


def _is_money_field(name: str) -> bool:
    return name.lower() in ('price', 'cost', 'amount', 'total', 'subtotal', 'revenue', 'value', 'fee', 'rate', 'salary', 'budget', 'balance')


def _money_attr(name: str) -> str:
    return ' data-fmt="money"' if _is_money_field(name) else ''


def _has_money_field(fields: list) -> bool:
    return any(_is_money_field(f['name']) for f in fields)


# Gradient palettes for product card image placeholders, cycled by index
_CARD_GRADIENTS = [
    ('135deg', '#6366f1', '#8b5cf6'),
    ('135deg', '#ec4899', '#f43f5e'),
    ('135deg', '#14b8a6', '#06b6d4'),
    ('135deg', '#f59e0b', '#ef4444'),
    ('135deg', '#22c55e', '#16a34a'),
    ('135deg', '#8b5cf6', '#ec4899'),
]


def _css_vars(theme: Theme) -> str:
    lines = []
    # Note: --primary is always emitted by the template directly; skip it here to avoid duplicate
    if 'accent' in theme.colors:
        lines.append(f"  --ds-accent: {theme.colors['accent']};")
    if 'background' in theme.colors or 'bg' in theme.colors:
        bg = theme.colors.get('background') or theme.colors.get('bg', '')
        lines.append(f"  --ds-bg: {bg};")
    if 'surface' in theme.colors:
        lines.append(f"  --ds-surface: {theme.colors['surface']};")
    if 'text' in theme.colors:
        lines.append(f"  --ds-text: {theme.colors['text']};")

    radius_map = {
        'none': '0px', 'small': '4px', 'medium': '8px',
        'large': '14px', 'rounded': '999px',
    }
    lines.append(f"  --ds-radius: {radius_map.get(theme.radius, '8px')};")

    if theme.font:
        lines.append(f"  --ds-font: '{theme.font}', system-ui, sans-serif;")

    return '\n'.join(lines)


def _font_link(theme: Theme) -> str:
    if not theme.font:
        return ''
    slug = theme.font.replace(' ', '+')
    return f'<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family={slug}:wght@400;500;600;700&display=swap">'


# ---------- component renderers -------------------------------------------


def _hero(comp: HeroComponent, theme: Theme) -> str:
    primary = theme.colors.get('primary', '#6366f1')
    accent = theme.colors.get('accent', '#8b5cf6')
    parts = []
    if comp.heading:
        parts.append(f'<h1 class="ds-hero-h">{_esc(comp.heading)}</h1>')
    if comp.sub:
        parts.append(f'<p class="ds-hero-sub">{_esc(comp.sub)}</p>')
    if comp.cta:
        parts.append(f'<div class="ds-hero-btns"><button class="ds-hero-cta" style="color:{primary}">{_esc(comp.cta)}</button></div>')
    return (
        f'<div class="ds-hero" style="background:linear-gradient(135deg,{primary} 0%,{accent} 100%)">'
        f'<div class="ds-hero-inner">{"".join(parts)}</div>'
        f'</div>'
    )


def _header(comp: HeaderComponent, theme: Theme) -> str:
    primary = theme.colors.get('primary', '#6366f1')
    actions = ''.join(
        f'<button class="ds-btn ds-btn-sm" style="border-color:{primary};color:{primary}">{_esc(a)}</button>'
        for a in comp.actions
    )
    return (
        f'<div class="ds-header">'
        f'<span class="ds-header-title">{_esc(comp.title)}</span>'
        f'<div class="ds-header-actions">{actions}</div>'
        f'</div>'
    )


def _stats(comp: StatsComponent, theme: Theme) -> str:
    primary = theme.colors.get('primary', '#6366f1')
    items = ''
    for fh in comp.items:
        label = fh.label or _title(fh.name)
        value = '—'
        if fh.widget in ('money', 'currency'):
            value = '$0.00'
        elif fh.widget in ('date',):
            value = 'Jan 1, 2025'
        elif fh.large:
            value = '0'
        items += (
            f'<div class="ds-stat" style="border-top-color:{primary}">'
            f'<span class="ds-stat-v" style="color:{primary}">{value}</span>'
            f'<span class="ds-stat-l">{_esc(label)}</span>'
            f'</div>'
        )
    return f'<div class="ds-stats">{items}</div>'


def _form(comp: FormComponent, ctx: dict, theme: Theme) -> str:
    primary = theme.colors.get('primary', '#6366f1')
    flow_info = ctx.get('flows', {}).get(comp.flow, {}) if comp.flow else {}
    flow_inputs = {}
    if flow_info:
        for f in flow_info.get('inputs', []):
            flow_inputs[f['name']] = f

    hint_map = {fh.name: fh for fh in comp.fields}
    fields_html = ''

    for fname, finfo in flow_inputs.items():
        fh = hint_map.get(fname)
        if fh and fh.hidden:
            continue
        label = (fh.label if fh else '') or _title(fname)
        ftype = finfo.get('type', 'str')
        placeholder = (fh.placeholder if fh else '') or ''
        widget = (fh.widget if fh else '') or ''
        large = fh.large if fh else False

        if fh and fh.choice_from:
            dep_attr = f' data-depends-on="{_esc(fh.depends_on)}"' if fh.depends_on else ''
            flt_attr = f' data-filter="{_esc(fh.choice_filter)}"' if fh.choice_filter else ''
            control = (
                f'<select class="ds-input ds-cascading-select" name="{_esc(fname)}"'
                f' data-choices-from="{_esc(fh.choice_from)}"{dep_attr}{flt_attr}>'
                f'<option value="">Loading {_esc(fh.choice_from)}…</option></select>'
            )
        elif widget == 'select' or widget == 'segmented':
            control = f'<select class="ds-input" name="{_esc(fname)}" style="border-color:#ccc"><option value="">{_esc(label)}…</option></select>'
        elif ftype == 'bool':
            control = f'<label class="ds-toggle"><input type="checkbox" name="{_esc(fname)}"> {_esc(label)}</label>'
        elif ftype in ('int', 'float') or widget in ('money', 'number'):
            control = f'<input class="ds-input{" ds-input-lg" if large else ""}" type="number" name="{_esc(fname)}" placeholder="{_esc(placeholder) or "0"}">'
        else:
            ph = _esc(placeholder) if placeholder else (_esc(label) + '…')
            control = f'<input class="ds-input{" ds-input-lg" if large else ""}" type="text" name="{_esc(fname)}" placeholder="{ph}">'

        fields_html += (
            f'<div class="ds-field">'
            f'<label class="ds-label">{_esc(label)}</label>'
            f'{control}'
            f'</div>'
        )

    submit = comp.submit or 'Submit'
    method = flow_info.get('method', 'POST') or 'POST'
    path = flow_info.get('path', '') or ''
    form_id = f'form-{_esc(comp.flow or "submit")}'
    if path:
        onsubmit = f'dsSubmit(event,\'{_esc(method)}\',\'{_esc(path)}\')'
    else:
        onsubmit = 'event.preventDefault()'
    return (
        f'<form class="ds-form" id="{form_id}" onsubmit="{onsubmit}">'
        f'{fields_html}'
        f'<button type="submit" class="ds-btn ds-btn-primary" style="background:{primary};margin-top:4px;width:100%;justify-content:center;padding:13px 20px;font-size:15px">{_esc(submit)}</button>'
        f'</form>'
        f'<p id="{form_id}-msg"></p>'
    )


def _list(comp: ListComponent, ctx: dict, theme: Theme) -> str:
    primary = theme.colors.get('primary', '#6366f1')
    accent = theme.colors.get('accent', '#8b5cf6')
    entity_fields = []
    if comp.entity and comp.entity in ctx.get('entities', {}):
        entity_fields = ctx['entities'][comp.entity]

    hint_map = {fh.name: fh for fh in comp.fields}
    shown = [f for f in entity_fields if not (hint_map.get(f['name']) and hint_map[f['name']].hidden)]
    if comp.fields and not entity_fields:
        shown = [{'name': fh.name, 'type': 'str'} for fh in comp.fields if not fh.hidden]

    entity = comp.entity or ''
    empty_text = f'No {_esc(_title(entity))} records yet.' if entity else 'No records yet.'

    if not shown:
        return f'<div class="ds-empty-note">No fields configured for this list.</div>'

    def _field_label(f):
        fh = hint_map.get(f['name'])
        return (fh.label if fh else '') or _title(f['name'])

    # Product card layout: used when a card-style list has a money field (price, cost…)
    cols_style = f' style="grid-template-columns:repeat({comp.cols},1fr)"' if getattr(comp, 'cols', 0) else ''

    if comp.style == 'cards' and _has_money_field(shown):
        # Separate fields into: name (title), price, and descriptive (meta)
        name_field = next((f for f in shown if f['name'] in ('name', 'title', 'product_name', 'item_name')), shown[0])
        price_field = next((f for f in shown if _is_money_field(f['name'])), None)
        meta_fields = [f for f in shown if f is not name_field and (price_field is None or f is not price_field)][:2]

        # Build gradient placeholders cycling through palette
        grad_count = len(_CARD_GRADIENTS)

        name_cell = f'<span class="ds-pcard-name" data-field="{_esc(name_field["name"])}"></span>'
        meta_cells = ''.join(
            f'<span class="ds-pcard-meta" data-field="{_esc(f["name"])}"></span>'
            for f in meta_fields
        )
        price_cell = (
            f'<span class="ds-pcard-price" data-field="{_esc(price_field["name"])}" data-fmt="money"></span>'
            if price_field else ''
        )
        cta_label = _esc(comp.fields[0].label if comp.fields and comp.fields[0].label else 'Add to Cart')
        tpl_card = (
            f'<div class="ds-pcard ds-card-tpl" hidden>'
            f'<div class="ds-pcard-img" style="background:linear-gradient(135deg,{primary} 0%,{accent} 100%)"></div>'
            f'<div class="ds-pcard-body">'
            f'{name_cell}{meta_cells}{price_cell}'
            f'<div class="ds-pcard-footer">'
            f'<button class="ds-btn ds-btn-primary ds-pcard-cta" style="background:{primary}">{cta_label}</button>'
            f'</div>'
            f'</div>'
            f'</div>'
        )
        return (
            f'<div class="ds-pcards" data-list="{_esc(entity)}" data-list-style="pcards"{cols_style}>'
            f'{tpl_card}'
            f'<div class="ds-list-loading ds-skel-wrap">'
            f'{"".join(f"""<div class="ds-skel-card"><div class="ds-skel ds-skel-img"></div><div class="ds-skel-body"><div class="ds-skel ds-skel-line ds-skel-w70"></div><div class="ds-skel ds-skel-line ds-skel-w40"></div><div class="ds-skel ds-skel-btn"></div></div></div>""" for _ in range(4))}'
            f'</div>'
            f'<div class="ds-list-empty" hidden>{empty_text}</div>'
            f'</div>'
        )

    elif comp.style == 'cards':
        cells_tpl = ''.join(
            f'<div class="ds-card-field">'
            f'<span class="ds-card-key">{_esc(_field_label(f))}</span>'
            f'<span class="ds-card-val" data-field="{_esc(f["name"])}"{_money_attr(f["name"])}></span>'
            f'</div>'
            for f in shown[:4]
        )
        tpl_card = f'<div class="ds-card ds-card-tpl" hidden>{cells_tpl}</div>'
        return (
            f'<div class="ds-cards" data-list="{_esc(entity)}" data-list-style="cards"{cols_style}>'
            f'{tpl_card}'
            f'<div class="ds-list-loading">Loading…</div>'
            f'<div class="ds-list-empty" hidden>{empty_text}</div>'
            f'</div>'
        )

    elif comp.style == 'rows':
        cells_tpl = ''.join(
            f'<span class="ds-row-cell">{_esc(_field_label(f))}: '
            f'<b data-field="{_esc(f["name"])}"{_money_attr(f["name"])}>—</b></span>'
            for f in shown[:3]
        )
        tpl_row = f'<div class="ds-row ds-row-tpl" hidden>{cells_tpl}<button class="ds-btn ds-btn-sm" style="color:{primary}">View</button></div>'
        return (
            f'<div class="ds-rows" data-list="{_esc(entity)}" data-list-style="rows">'
            f'{tpl_row}'
            f'<div class="ds-list-loading">Loading…</div>'
            f'<div class="ds-list-empty" hidden>{empty_text}</div>'
            f'</div>'
        )

    else:  # table (default)
        headers = ''.join(f'<th>{_esc(_field_label(f))}</th>' for f in shown[:6])
        tpl_cells = ''.join(
            f'<td data-field="{_esc(f["name"])}"{_money_attr(f["name"])}></td>'
            for f in shown[:6]
        )
        tpl_row = f'<tr class="ds-row-tpl" hidden>{tpl_cells}</tr>'
        return (
            f'<div class="ds-table-wrap" data-list="{_esc(entity)}" data-list-style="table">'
            f'<table class="ds-table">'
            f'<thead><tr>{headers}</tr></thead>'
            f'<tbody data-list-body="{_esc(entity)}">{tpl_row}</tbody>'
            f'</table>'
            f'<div class="ds-list-loading">Loading…</div>'
            f'<div class="ds-list-empty" hidden>{empty_text}</div>'
            f'</div>'
        )


def _empty(comp: EmptyComponent, theme: Theme, hidden: bool = False) -> str:
    primary = theme.colors.get('primary', '#6366f1')
    cta = ''
    if comp.cta:
        cta = f'<button class="ds-btn ds-btn-primary" style="background:{primary}">{_esc(comp.cta)}</button>'
    icon = '<div class="ds-empty-icon">📭</div>' if comp.text else ''
    hidden_attr = ' hidden' if hidden else ''
    return f'<div class="ds-empty"{hidden_attr}>{icon}<p>{_esc(comp.text)}</p>{cta}</div>'


def _trust(comp: TrustComponent) -> str:
    return f'<div class="ds-trust">{_esc(comp.text)}</div>'


def _text_comp(comp: TextComponent) -> str:
    align_cls = f' ds-text-{comp.align}' if comp.align in ('left', 'center', 'right') else ''
    text = _esc(comp.text)
    size = comp.size if comp.size in ('h1', 'h2', 'h3', 'h4', 'body', 'large', 'lead', 'small') else 'body'
    if size in ('h1', 'h2', 'h3', 'h4'):
        return f'<{size} class="ds-text-{size}{align_cls}">{text}</{size}>'
    return f'<p class="ds-text-{size}{align_cls}">{text}</p>'


def _columns(comp: ColumnsComponent, theme: Theme) -> str:
    primary = theme.colors.get('primary', '#6366f1')
    items_html = ''
    for item in comp.items:
        icon_html = f'<div class="ds-col-icon">{_esc(item.icon)}</div>' if item.icon else ''
        title_html = f'<h4 class="ds-col-title">{_esc(item.title)}</h4>' if item.title else ''
        body_html = f'<p class="ds-col-body">{_esc(item.body)}</p>' if item.body else ''
        items_html += f'<div class="ds-col-item">{icon_html}{title_html}{body_html}</div>'
    count = max(1, min(4, comp.count))
    return f'<div class="ds-columns ds-columns-{count}">{items_html}</div>'


def _cta(comp: CTAComponent, theme: Theme) -> str:
    primary = theme.colors.get('primary', '#6366f1')
    accent = theme.colors.get('accent', '#8b5cf6')
    bg_map = {'primary': primary, 'accent': accent, 'dark': '#0f172a', 'surface': '#f8fafc', 'white': '#ffffff'}
    bg = bg_map.get(comp.bg, primary)
    is_light = comp.bg in ('surface', 'white')
    fg = '#0f172a' if is_light else '#ffffff'
    btn_bg = primary if is_light else 'white'
    btn_fg = 'white' if is_light else bg
    heading_html = f'<h2 class="ds-cta-heading">{_esc(comp.heading)}</h2>' if comp.heading else ''
    sub_html = f'<p class="ds-cta-sub">{_esc(comp.sub)}</p>' if comp.sub else ''
    btn_html = (
        f'<button class="ds-btn ds-btn-cta" style="background:{btn_bg};color:{btn_fg};border-color:transparent">'
        f'{_esc(comp.button)}</button>'
    ) if comp.button else ''
    return (
        f'<div class="ds-cta" style="background:{bg};color:{fg}">'
        f'<div class="ds-cta-inner">{heading_html}{sub_html}{btn_html}</div>'
        f'</div>'
    )


def _divider(comp: DividerComponent) -> str:
    if comp.label:
        return f'<div class="ds-divider"><span class="ds-divider-label">{_esc(comp.label)}</span></div>'
    return '<div class="ds-divider"></div>'


def _testimonials(comp: TestimonialsComponent, theme: Theme) -> str:
    primary = theme.colors.get('primary', '#6366f1')
    items_html = ''
    for item in comp.items:
        stars = ('★' * item.rating + '☆' * (5 - item.rating)) if item.rating else ''
        stars_html = f'<div class="ds-testimonial-stars" style="color:{primary}">{stars}</div>' if stars else ''
        author_html = f'<div class="ds-testimonial-author">— {_esc(item.author)}</div>' if item.author else ''
        items_html += (
            f'<div class="ds-testimonial">'
            f'{stars_html}'
            f'<p class="ds-testimonial-text">&#8220;{_esc(item.text)}&#8221;</p>'
            f'{author_html}'
            f'</div>'
        )
    return f'<div class="ds-testimonials">{items_html}</div>'


def _pricing(comp: PricingComponent, theme: Theme) -> str:
    primary = theme.colors.get('primary', '#6366f1')
    tiers_html = ''
    for tier in comp.tiers:
        if tier.highlight:
            bg, fg, btn_bg, btn_fg = primary, '#ffffff', '#ffffff', primary
        else:
            bg, fg, btn_bg, btn_fg = '#ffffff', '#0f172a', primary, '#ffffff'
        check_svg = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"/></svg>'
        features_html = ''.join(
            f'<li class="ds-tier-feature">{check_svg}{_esc(f)}</li>'
            for f in tier.features
        )
        hl_cls = ' ds-tier-hl' if tier.highlight else ''
        tiers_html += (
            f'<div class="ds-tier{hl_cls}" style="background:{bg};color:{fg}">'
            f'<div class="ds-tier-name">{_esc(tier.name)}</div>'
            f'<div class="ds-tier-price">'
            f'<span class="ds-tier-currency">{_esc(comp.currency)}</span>'
            f'<span class="ds-tier-amount">{tier.price}</span>'
            f'<span class="ds-tier-period">{_esc(tier.period)}</span>'
            f'</div>'
            f'<ul class="ds-tier-features">{features_html}</ul>'
            f'<button class="ds-btn" style="background:{btn_bg};color:{btn_fg};border-color:transparent;justify-content:center;width:100%;padding:12px 20px">'
            f'{_esc(tier.cta or "Get started")}</button>'
            f'</div>'
        )
    return f'<div class="ds-pricing">{tiers_html}</div>'


def _steps(comp: StepsComponent, theme: Theme) -> str:
    primary = theme.colors.get('primary', '#6366f1')
    items_html = ''.join(
        f'<li class="ds-step">'
        f'<span class="ds-step-num" style="background:{primary}">{i + 1}</span>'
        f'<span class="ds-step-text">{_esc(item)}</span>'
        f'</li>'
        for i, item in enumerate(comp.items)
    )
    return f'<ol class="ds-steps">{items_html}</ol>'


def _svg_comp(comp: SVGComponent, theme: Theme) -> str:
    primary = theme.colors.get('primary', '#6366f1')
    accent = theme.colors.get('accent', '#8b5cf6')

    # Full-width aspect-ratio box (like Image component)
    if comp.aspect:
        aspect_map = {'16/9': '56.25%', '4/3': '75%', '1/1': '100%', '3/2': '66.67%', '21/9': '42.86%'}
        pt = aspect_map.get(comp.aspect, '56.25%')
        wrap = f'padding-top:{pt};position:relative;overflow:hidden;border-radius:14px;margin:16px 0'
        inner_style = 'position:absolute;inset:0;width:100%;height:100%;object-fit:contain'
        if comp.src:
            return f'<div style="{wrap}"><img src="{_esc(comp.src)}" alt="{_esc(comp.alt)}" style="{inner_style}"></div>'
        if comp.inline:
            svg = comp.inline.replace('<svg ', '<svg style="position:absolute;inset:0;width:100%;height:100%" ', 1)
            return f'<div style="{wrap}">{svg}</div>'

    # Inline SVG — output raw markup in a wrapper
    if comp.inline:
        dim_style = ''
        if comp.width or comp.height:
            parts = []
            if comp.width: parts.append(f'width:{comp.width}px')
            if comp.height: parts.append(f'height:{comp.height}px')
            dim_style = f' style="{";".join(parts)}"'
        return f'<div class="ds-svg-wrap"{dim_style}>{comp.inline}</div>'

    # External src — img tag
    if comp.src:
        style_parts = []
        if comp.width: style_parts.append(f'width:{comp.width}px')
        if comp.height: style_parts.append(f'height:{comp.height}px')
        style_attr = f' style="{";".join(style_parts)}"' if style_parts else ''
        return f'<img class="ds-svg-img" src="{_esc(comp.src)}" alt="{_esc(comp.alt)}"{style_attr}>'

    # Placeholder (no src, no inline)
    label = _esc(comp.alt) if comp.alt else '&#9674; SVG'
    w = f'{comp.width}px' if comp.width else '100%'
    h = f'{comp.height}px' if comp.height else '120px'
    return (
        f'<div class="ds-svg-placeholder" style="width:{w};height:{h};'
        f'background:linear-gradient(135deg,{primary} 0%,{accent} 100%)">'
        f'<span style="color:rgba(255,255,255,.7);font-size:13px;font-weight:500">{label}</span>'
        f'</div>'
    )


def _image(comp: ImageComponent, theme: Theme) -> str:
    primary = theme.colors.get('primary', '#6366f1')
    accent = theme.colors.get('accent', '#8b5cf6')
    aspect_map = {'16/9': '56.25%', '4/3': '75%', '1/1': '100%', '3/2': '66.67%', '21/9': '42.86%'}
    pt = aspect_map.get(comp.aspect, '56.25%')
    wrap_style = f'padding-top:{pt};position:relative;overflow:hidden;border-radius:14px;margin:16px 0'
    if comp.src:
        return (
            f'<div style="{wrap_style}">'
            f'<img src="{_esc(comp.src)}" alt="{_esc(comp.alt)}" '
            f'style="position:absolute;inset:0;width:100%;height:100%;object-fit:cover">'
            f'</div>'
        )
    label = _esc(comp.alt) if comp.alt else '&#128247; Image'
    return (
        f'<div style="{wrap_style};background:linear-gradient(135deg,{primary} 0%,{accent} 100%)">'
        f'<div style="position:absolute;inset:0;display:flex;align-items:center;justify-content:center;'
        f'color:rgba(255,255,255,.65);font-size:13px;font-weight:500">{label}</div>'
        f'</div>'
    )


# ---------- new ecommerce component renderers ------------------------------


def _hex_components(hex_color: str) -> str:
    """Return 'r,g,b' for a hex colour — used in rgba() strings."""
    h = hex_color.lstrip('#')
    if len(h) == 3:
        h = ''.join(c * 2 for c in h)
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f'{r},{g},{b}'


def _wizard(comp: WizardComponent, theme: Theme) -> str:
    """Multi-step form wizard component."""
    primary = theme.colors.get('primary', '#6366f1')
    n = len(comp.steps)
    if n == 0:
        return '<div class="ds-wizard"><p style="padding:24px;color:#94a3b8">No wizard steps defined.</p></div>'

    wid = f'wiz-{_esc(comp.flow or "w")}'
    pct = round(100 / n)

    step_indicators = ''.join(
        f'<div class="ds-wiz-step" data-step="{i}">'
        f'<span class="ds-wiz-snum">{i + 1}</span>'
        f'<span class="ds-wiz-slabel">{_esc(s.label)}</span>'
        f'</div>'
        for i, s in enumerate(comp.steps)
    )

    panes_html = ''
    for i, step in enumerate(comp.steps):
        fields_html = ''.join(
            f'<div class="ds-field">'
            f'<label class="ds-label" for="{_esc(wid)}-{_esc(f)}">'
            f'{_esc(f.replace("_", " ").title())}</label>'
            f'<input class="ds-input" type="text" id="{_esc(wid)}-{_esc(f)}" '
            f'name="{_esc(f)}" placeholder="{_esc(f.replace("_", " "))}…">'
            f'</div>'
            for f in step.fields
        ) if step.fields else (
            f'<p style="color:#94a3b8;font-size:14px;padding:12px 0">'
            f'No fields defined for this step.</p>'
        )
        panes_html += (
            f'<div class="ds-wiz-pane" data-pane="{i}">'
            f'<h3 class="ds-wiz-pane-title">{_esc(step.label)}</h3>'
            f'<div class="ds-form">{fields_html}</div>'
            f'</div>'
        )

    return (
        f'<div class="ds-wizard" id="{_esc(wid)}" data-flow="{_esc(comp.flow)}">'
        f'<div class="ds-wiz-header">'
        f'<div class="ds-wiz-progress">'
        f'<div class="ds-wiz-bar" style="background:{primary};width:{pct}%"></div>'
        f'</div>'
        f'<div class="ds-wiz-steps">{step_indicators}</div>'
        f'</div>'
        f'{panes_html}'
        f'<div class="ds-wiz-nav">'
        f'<button class="ds-btn ds-wiz-prev" disabled>← Back</button>'
        f'<div id="{_esc(wid)}-msg"></div>'
        f'<button class="ds-btn ds-btn-primary ds-wiz-next" '
        f'style="background:{primary};border-color:{primary}">Next →</button>'
        f'<button class="ds-btn ds-btn-primary ds-wiz-submit" '
        f'style="background:{primary};border-color:{primary};display:none">'
        f'{_esc(comp.submit)} →</button>'
        f'</div>'
        f'</div>'
    )


def _model3d(comp: Model3DComponent, theme: Theme) -> str:
    """3D model viewer — uses <model-viewer> if src given, else CSS 3D cube placeholder."""
    primary = theme.colors.get('primary', '#6366f1')
    accent = theme.colors.get('accent', '#8b5cf6')

    if comp.src:
        auto_attr = ' auto-rotate' if comp.auto_rotate else ''
        poster_attr = f' poster="{_esc(comp.poster)}"' if comp.poster else ''
        float_style = 'animation:ds-float 4s ease-in-out infinite;' if comp.float_anim else ''
        return (
            f'<div class="ds-model3d-wrap" style="{float_style}">'
            f'<model-viewer src="{_esc(comp.src)}" alt="{_esc(comp.alt)}"'
            f'{auto_attr}{poster_attr} camera-controls shadow-intensity="1" '
            f'style="width:100%;height:400px;background:transparent"></model-viewer>'
            f'</div>'
        )

    label = _esc(comp.alt) if comp.alt else '3D Model'
    float_style = 'animation:ds-float 4s ease-in-out infinite;' if comp.float_anim else ''
    pc = _hex_components(primary)
    ac = _hex_components(accent)
    return (
        f'<div class="ds-model3d-placeholder">'
        f'<div class="ds-model3d-cube" style="{float_style}">'
        f'<div class="ds-cube-face ds-cube-front" '
        f'style="background:rgba({pc},.12);border:1px solid rgba({pc},.3)"></div>'
        f'<div class="ds-cube-face ds-cube-back" '
        f'style="background:rgba({ac},.12);border:1px solid rgba({ac},.3)"></div>'
        f'<div class="ds-cube-face ds-cube-right" '
        f'style="background:rgba({pc},.09);border:1px solid rgba({pc},.2)"></div>'
        f'<div class="ds-cube-face ds-cube-left" '
        f'style="background:rgba({ac},.09);border:1px solid rgba({ac},.2)"></div>'
        f'<div class="ds-cube-face ds-cube-top" '
        f'style="background:rgba({pc},.18);border:1px solid rgba({pc},.4)"></div>'
        f'<div class="ds-cube-face ds-cube-bottom" '
        f'style="background:rgba({ac},.07);border:1px solid rgba({ac},.15)"></div>'
        f'</div>'
        f'<p class="ds-model3d-label">{label}</p>'
        f'</div>'
    )


def _split_preview_panel(entity: str, theme: Theme) -> str:
    primary = theme.colors.get('primary', '#6366f1')
    pc = _hex_components(primary)
    entity_label = _esc(_title(entity)) if entity else 'item'
    return (
        f'<div class="ds-split-empty" id="split-empty-state">'
        f'<svg width="40" height="40" fill="none" stroke="rgba({pc},.4)" '
        f'stroke-width="1.5" viewBox="0 0 24 24">'
        f'<rect x="3" y="3" width="18" height="18" rx="3"/>'
        f'<path d="M3 9h18M9 21V9"/>'
        f'</svg>'
        f'<span>Select a {entity_label} to preview</span>'
        f'</div>'
        f'<div class="ds-split-detail" id="split-detail" hidden></div>'
    )


# ---------- style presets -------------------------------------------------


def _style_css(theme: Theme) -> str:
    if not theme.style or theme.style == 'default':
        return ''
    primary = theme.colors.get('primary', '#6366f1')
    accent = theme.colors.get('accent', '#8b5cf6')
    pc = _hex_components(primary)
    ac = _hex_components(accent)

    if theme.style == 'cyberpunk':
        return f'''
/* style: cyberpunk */
body {{ background: #09090f; color: #e2e8f0; }}
.ds-nav {{ background: rgba(9,9,15,.92); border-bottom: 1px solid rgba({pc},.25); }}
.ds-nav-brand {{ background: linear-gradient(90deg,{primary},{accent}); -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text; }}
.ds-nav-btn {{ color: #94a3b8; }}
.ds-nav-btn.active {{ background: linear-gradient(90deg,{primary},{accent}); color: #fff; border: none; }}
.ds-hero-h {{ background: linear-gradient(90deg,{primary},{accent}); -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text; }}
.ds-col-item,.ds-card,.ds-pcard,.ds-stat,.ds-tier,.ds-testimonial {{
  background: rgba({pc},.06);
  border: 1px solid rgba({pc},.22);
  box-shadow: 0 0 24px rgba({pc},.08), inset 0 1px 0 rgba(255,255,255,.04);
  color: #e2e8f0;
}}
.ds-col-item:hover,.ds-card:hover,.ds-pcard:hover {{
  border-color: rgba({ac},.45);
  box-shadow: 0 0 32px rgba({ac},.18), 0 0 0 1px rgba({ac},.28);
}}
.ds-col-title,.ds-pcard-name,.ds-header-title,.ds-text-h1,.ds-text-h2,.ds-text-h3 {{ color: #f1f5f9; }}
.ds-col-body,.ds-pcard-meta,.ds-card-key,.ds-text-body,.ds-text-lead,.ds-text-large {{ color: #94a3b8; }}
.ds-input {{ background: rgba(255,255,255,.04); border-color: rgba({pc},.28); color: #f1f5f9; }}
.ds-input:focus {{ border-color: {accent}; box-shadow: 0 0 0 3px rgba({ac},.18); }}
.ds-input::placeholder {{ color: #475569; }}
.ds-btn {{ background: rgba(255,255,255,.05); border-color: rgba({pc},.25); color: #e2e8f0; }}
.ds-btn-primary {{ background: linear-gradient(90deg,{primary},{accent}); border: none; box-shadow: 0 0 20px rgba({pc},.3); color: #fff; }}
.ds-stat {{ border-top-color: {accent}; background: rgba({pc},.06); }}
.ds-stat-v {{ color: {accent}; }}
.ds-table-wrap {{ background: rgba({pc},.06); border: 1px solid rgba({pc},.2); }}
.ds-table thead {{ background: rgba({pc},.1); }}
.ds-table th {{ color: {accent}; }}
.ds-table td {{ color: #cbd5e1; border-top-color: rgba({pc},.12); }}
.ds-table tbody tr:hover {{ background: rgba({pc},.08); }}
.ds-trust {{ background: rgba(9,9,15,.85); border-top-color: rgba({pc},.18); color: #475569; }}
.ds-header {{ border-bottom-color: rgba({pc},.18); }}
.ds-wiz-header,.ds-wizard {{ background: rgba({pc},.06); border: 1px solid rgba({pc},.2); }}
body::after {{ content:''; position:fixed; inset:0; background:repeating-linear-gradient(0deg,rgba(0,0,0,.035) 0px,rgba(0,0,0,.035) 1px,transparent 1px,transparent 3px); pointer-events:none; z-index:9998; }}
'''

    if theme.style == 'glass':
        return f'''
/* style: glass */
.ds-col-item,.ds-card,.ds-pcard,.ds-stat,.ds-tier,.ds-testimonial,.ds-form,.ds-table-wrap,.ds-wizard {{
  background: rgba(255,255,255,.12);
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
  border: 1px solid rgba(255,255,255,.22);
  box-shadow: 0 8px 32px rgba(31,38,135,.1);
}}
.ds-nav {{ background: rgba(255,255,255,.18); backdrop-filter: blur(20px); -webkit-backdrop-filter: blur(20px); border-bottom: 1px solid rgba(255,255,255,.22); }}
.ds-trust {{ background: rgba(255,255,255,.1); backdrop-filter: blur(10px); }}
'''

    if theme.style == 'bold':
        return f'''
/* style: bold */
.ds-nav {{ border-bottom: 4px solid {primary}; }}
.ds-hero-h {{ font-size: clamp(54px, 9vw, 96px); letter-spacing: -.07em; }}
.ds-col-item,.ds-card,.ds-pcard {{
  border-left: 5px solid {primary};
  border-radius: 0 14px 14px 0;
}}
.ds-col-item:nth-child(2n),.ds-card:nth-child(2n) {{ border-left-color: {accent}; }}
.ds-btn-primary {{ border-radius: 0; text-transform: uppercase; letter-spacing: .1em; font-weight: 900; }}
.ds-cta-heading {{ font-size: clamp(38px, 7vw, 72px); }}
.ds-stat {{ border-top-width: 5px; }}
.ds-stat-v {{ font-size: 42px; }}
'''

    if theme.style == 'minimal':
        return f'''
/* style: minimal */
.ds-col-item,.ds-card,.ds-pcard,.ds-stat,.ds-tier,.ds-testimonial {{
  box-shadow: none;
  border: 1px solid #e2e8f0;
  border-radius: 4px;
}}
.ds-nav {{ box-shadow: none; border-bottom: 1px solid #e2e8f0; }}
.ds-btn,.ds-btn-primary,.ds-hero-cta {{ box-shadow: none; border-radius: 4px; }}
.ds-hero-h {{ font-weight: 700; letter-spacing: -.02em; }}
.ds-pcard {{ border-radius: 4px; }}
'''

    return ''


# ---------- background effects -------------------------------------------


def _bg_css(theme: Theme) -> str:
    if not theme.background:
        return ''
    primary = theme.colors.get('primary', '#6366f1')
    accent = theme.colors.get('accent', '#8b5cf6')
    pc = _hex_components(primary)
    ac = _hex_components(accent)

    if theme.background == 'particles':
        return '#ds-ptc { position: fixed; inset: 0; z-index: -1; pointer-events: none; }\n'

    if theme.background == 'mesh-gradient':
        return f'''
body::before {{
  content: '';
  position: fixed;
  inset: 0;
  background:
    radial-gradient(ellipse 80% 80% at 20% 20%, rgba({pc},.11) 0%, transparent 60%),
    radial-gradient(ellipse 80% 80% at 80% 80%, rgba({ac},.09) 0%, transparent 60%),
    radial-gradient(ellipse 60% 60% at 60% 30%, rgba({pc},.06) 0%, transparent 55%);
  animation: ds-mesh 20s ease-in-out infinite alternate;
  z-index: -1;
  pointer-events: none;
}}
@keyframes ds-mesh {{
  0%   {{ opacity: 1; transform: translate(0,0); }}
  33%  {{ transform: translate(3%,5%); }}
  66%  {{ transform: translate(-4%,-3%); }}
  100% {{ transform: translate(2%,-2%); }}
}}
'''

    if theme.background == 'dot-grid':
        return f'''
body::before {{
  content: '';
  position: fixed;
  inset: 0;
  background-image: radial-gradient(circle at 1px 1px, rgba({pc},.1) 1px, transparent 0);
  background-size: 24px 24px;
  z-index: -1;
  pointer-events: none;
}}
'''

    if theme.background == 'circuit':
        hex_p = primary.lstrip('#')
        encoded = hex_p
        return f'''
body::before {{
  content: '';
  position: fixed;
  inset: 0;
  opacity: 0.07;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='120' height='120'%3E%3Cpath d='M10 10h20v20H50V10h20v20h20V50h-20V30H70v20H50v20H30V50H10V30H30V10z' fill='none' stroke='%23{encoded}' stroke-width='1'/%3E%3Ccircle cx='10' cy='10' r='3' fill='%23{encoded}'/%3E%3Ccircle cx='110' cy='110' r='3' fill='%23{encoded}'/%3E%3Ccircle cx='60' cy='60' r='2' fill='%23{encoded}'/%3E%3C/svg%3E");
  background-size: 120px 120px;
  z-index: -1;
  pointer-events: none;
}}
'''

    if theme.background == 'video':
        return '''
#ds-bg-video {
  position: fixed; inset: 0; width: 100%; height: 100%;
  object-fit: cover; z-index: -1; opacity: .4;
}
'''

    return ''


def _bg_js(theme: Theme) -> str:
    if theme.background != 'particles':
        return ''
    primary = theme.colors.get('primary', '#6366f1')
    pc = _hex_components(primary)
    return f'''(function(){{
  var c=document.createElement('canvas');
  c.id='ds-ptc';document.body.insertBefore(c,document.body.firstChild);
  var x=c.getContext('2d'),W,H,P=[],N=55,D=140;
  function resize(){{W=c.width=innerWidth;H=c.height=innerHeight;}}
  function init(){{
    P=[];for(var i=0;i<N;i++)P.push({{x:Math.random()*W,y:Math.random()*H,vx:(Math.random()-.5)*.45,vy:(Math.random()-.5)*.45,r:Math.random()*1.5+1}});
  }}
  function frame(){{
    x.clearRect(0,0,W,H);
    for(var i=0;i<N;i++)for(var j=i+1;j<N;j++){{
      var dx=P[i].x-P[j].x,dy=P[i].y-P[j].y,d=Math.sqrt(dx*dx+dy*dy);
      if(d<D){{x.beginPath();x.strokeStyle='rgba({pc},'+(1-d/D)*.12+')';x.lineWidth=1;x.moveTo(P[i].x,P[i].y);x.lineTo(P[j].x,P[j].y);x.stroke();}}
    }}
    P.forEach(function(p){{
      x.beginPath();x.arc(p.x,p.y,p.r,0,Math.PI*2);x.fillStyle='rgba({pc},.22)';x.fill();
      p.x+=p.vx;p.y+=p.vy;if(p.x<0||p.x>W)p.vx*=-1;if(p.y<0||p.y>H)p.vy*=-1;
    }});
    requestAnimationFrame(frame);
  }}
  resize();init();frame();window.addEventListener('resize',function(){{resize();init();}});
}})();'''


# ---------- micro-interaction helpers --------------------------------------


def _interactions_css(theme: Theme) -> str:
    if not theme.interactions:
        return ''
    primary = theme.colors.get('primary', '#6366f1')
    pc = _hex_components(primary)
    parts = []

    if 'card-tilt' in theme.interactions:
        parts.append('''
/* micro: card-tilt */
.ds-col-item,.ds-card,.ds-pcard {
  transform-style: preserve-3d;
  will-change: transform;
  transition: transform .2s ease, box-shadow .2s ease !important;
}
''')

    if 'button-glow' in theme.interactions:
        parts.append('''
/* micro: button-glow */
.ds-btn-primary,.ds-hero-cta,.ds-btn-cta { position: relative; overflow: hidden; }
.ds-btn-primary::after,.ds-hero-cta::after,.ds-btn-cta::after {
  content: '';
  position: absolute; inset: 0;
  background: radial-gradient(circle 80px at var(--mx,50%) var(--my,50%), rgba(255,255,255,.28), transparent);
  opacity: 0; transition: opacity .3s; pointer-events: none;
}
.ds-btn-primary:hover::after,.ds-hero-cta:hover::after,.ds-btn-cta:hover::after { opacity: 1; }
''')

    if 'ripple' in theme.interactions:
        parts.append('''
/* micro: ripple */
.ds-ripple { position: relative; overflow: hidden; }
.ds-ripple-wave {
  position: absolute; border-radius: 50%;
  background: rgba(255,255,255,.32);
  transform: scale(0); animation: ds-ripple-anim .5s linear;
  pointer-events: none;
}
@keyframes ds-ripple-anim { to { transform: scale(4); opacity: 0; } }
''')

    if 'magnetic-links' in theme.interactions:
        parts.append('''
/* micro: magnetic-links */
.ds-nav-btn {
  transition: transform .2s cubic-bezier(.25,.46,.45,.94), background .12s, color .12s !important;
}
''')

    if 'parallax-cards' in theme.interactions:
        parts.append('''
/* micro: parallax-cards */
.ds-col-item { will-change: transform; }
''')

    return ''.join(parts)


def _interactions_js(theme: Theme) -> str:
    if not theme.interactions:
        return ''
    parts = []

    if 'card-tilt' in theme.interactions:
        parts.append(r'''
(function(){
  var TILT=12;
  function addTilt(el){
    el.addEventListener('mousemove',function(e){
      var r=el.getBoundingClientRect();
      var tx=(e.clientX-r.left)/r.width-.5;
      var ty=(e.clientY-r.top)/r.height-.5;
      el.style.transform='perspective(600px) rotateY('+(tx*TILT)+'deg) rotateX('+(-ty*TILT)+'deg) translateZ(8px)';
      el.style.boxShadow='0 '+(10+ty*10)+'px '+(30+Math.abs(tx)*20)+'px rgba(0,0,0,.16)';
    });
    el.addEventListener('mouseleave',function(){el.style.transform='';el.style.boxShadow='';});
  }
  function initTilt(){document.querySelectorAll('.ds-col-item,.ds-card,.ds-pcard').forEach(addTilt);}
  document.addEventListener('DOMContentLoaded',initTilt);
  var _o=window.showScreen;window.showScreen=function(n){_o(n);setTimeout(initTilt,50);};
})();
''')

    if 'button-glow' in theme.interactions:
        parts.append(r'''
(function(){
  function trackGlow(el){
    el.addEventListener('mousemove',function(e){
      var r=el.getBoundingClientRect();
      el.style.setProperty('--mx',((e.clientX-r.left)/r.width*100)+'%');
      el.style.setProperty('--my',((e.clientY-r.top)/r.height*100)+'%');
    });
  }
  function initGlow(){document.querySelectorAll('.ds-btn-primary,.ds-hero-cta,.ds-btn-cta').forEach(trackGlow);}
  document.addEventListener('DOMContentLoaded',initGlow);
  var _o=window.showScreen;window.showScreen=function(n){_o(n);setTimeout(initGlow,50);};
})();
''')

    if 'ripple' in theme.interactions:
        parts.append(r'''
(function(){
  function addRipple(el){
    el.classList.add('ds-ripple');
    el.addEventListener('click',function(e){
      var r=el.getBoundingClientRect();
      var d=Math.max(r.width,r.height);
      var w=document.createElement('span');
      w.className='ds-ripple-wave';
      w.style.cssText='width:'+d+'px;height:'+d+'px;left:'+(e.clientX-r.left-d/2)+'px;top:'+(e.clientY-r.top-d/2)+'px;';
      el.appendChild(w);setTimeout(function(){w.remove();},600);
    });
  }
  function initRipple(){document.querySelectorAll('.ds-btn-primary,.ds-hero-cta,.ds-btn-cta,.ds-btn').forEach(addRipple);}
  document.addEventListener('DOMContentLoaded',initRipple);
  var _o=window.showScreen;window.showScreen=function(n){_o(n);setTimeout(initRipple,50);};
})();
''')

    if 'magnetic-links' in theme.interactions:
        parts.append(r'''
(function(){
  var S=0.3;
  document.addEventListener('DOMContentLoaded',function(){
    document.querySelectorAll('.ds-nav-btn').forEach(function(btn){
      btn.addEventListener('mousemove',function(e){
        var r=btn.getBoundingClientRect();
        var dx=(e.clientX-r.left-r.width/2)*S;
        var dy=(e.clientY-r.top-r.height/2)*S;
        btn.style.transform='translate('+dx+'px,'+dy+'px)';
      });
      btn.addEventListener('mouseleave',function(){btn.style.transform='';});
    });
  });
})();
''')

    if 'parallax-cards' in theme.interactions:
        parts.append(r'''
(function(){
  window.addEventListener('scroll',function(){
    var sy=window.scrollY;
    document.querySelectorAll('.ds-screen.visible .ds-col-item').forEach(function(el,i){
      el.style.transform='translateY('+(sy*(i%2===0?0.03:-0.03))+'px)';
    });
  },{passive:true});
})();
''')

    return ''.join(parts)


# ---------- animation helpers ---------------------------------------------


def _anim_css(anims: list) -> str:
    if not anims:
        return ''
    parts = []
    if 'scroll-reveal' in anims or 'stagger' in anims:
        parts.append('''
/* scroll-reveal */
.anim-ready {
  opacity: 0;
  transform: translateY(22px);
  transition: opacity .6s cubic-bezier(.22,.68,0,1.1), transform .6s cubic-bezier(.22,.68,0,1.1);
}
.anim-in { opacity: 1 !important; transform: none !important; }

/* hero uses a CSS-only entrance so it never starts hidden */
@keyframes ds-hero-enter {
  from { opacity: 0; transform: scale(.985); }
  to   { opacity: 1; transform: none; }
}
.ds-screen.visible .ds-hero {
  animation: ds-hero-enter .75s cubic-bezier(.22,.68,0,1.1) both;
}
''')
    if 'typewriter' in anims:
        parts.append('''
/* typewriter */
.tw-ch { display: inline; transition: opacity 0s; }
.ds-hero-h::after {
  content: '|';
  animation: tw-blink .75s step-end infinite;
  margin-left: 1px;
  opacity: 1;
}
.ds-hero-h.tw-done::after { display: none; }
@keyframes tw-blink { 0%,100% { opacity: 1; } 50% { opacity: 0; } }
''')
    return ''.join(parts)


def _anim_js(anims: list) -> str:
    if not anims:
        return ''
    parts = []

    if 'scroll-reveal' in anims:
        parts.append(r'''
(function(){
  // Note: .ds-hero is intentionally excluded — it is always visible on load
  // and gets its own CSS entrance animation (.ds-hero-enter).
  var SEL = [
    '.ds-header','.ds-stats','.ds-form','.ds-columns',
    '.ds-cta','.ds-divider','.ds-testimonials','.ds-pricing','.ds-steps',
    '.ds-table-wrap','.ds-cards','.ds-pcards','.ds-rows','.ds-trust',
    '.ds-text-h1','.ds-text-h2','.ds-text-h3','.ds-text-lead','.ds-text-large',
    '.ds-text-body','.ds-empty','.ds-svg-wrap','.ds-svg-placeholder','.ds-svg-img'
  ].join(',');
  function observe(root) {
    root.querySelectorAll(SEL).forEach(function(el) {
      if (el.classList.contains('anim-ready')) return;
      el.classList.add('anim-ready');
      _revObs.observe(el);
    });
  }
  window._revObs = new IntersectionObserver(function(entries) {
    entries.forEach(function(e) {
      if (e.isIntersecting) {
        e.target.classList.add('anim-in');
        _revObs.unobserve(e.target);
      }
    });
  }, { threshold: 0.07, rootMargin: '0px 0px -36px 0px' });
  var _orig = window.showScreen;
  window.showScreen = function(name) {
    _orig(name);
    var s = document.getElementById('s-' + name);
    if (s) observe(s);
  };
  document.addEventListener('DOMContentLoaded', function() {
    document.querySelectorAll('.ds-screen').forEach(observe);
  });
})();
''')

    if 'stagger' in anims:
        parts.append(r'''
(function(){
  var GRIDS = '.ds-columns,.ds-cards,.ds-pcards,.ds-rows,.ds-stats,.ds-testimonials,.ds-pricing';
  document.addEventListener('DOMContentLoaded', function() {
    document.querySelectorAll(GRIDS).forEach(function(grid) {
      Array.from(grid.children).forEach(function(child, i) {
        if (!child.classList.contains('ds-card-tpl') &&
            !child.classList.contains('ds-row-tpl') &&
            !child.classList.contains('ds-skel-wrap') &&
            !child.classList.contains('ds-list-loading') &&
            !child.classList.contains('ds-list-empty')) {
          child.style.transitionDelay = (i * 70) + 'ms';
        }
      });
    });
  });
})();
''')

    if 'counter' in anims:
        parts.append(r'''
(function(){
  function countUp(el) {
    var raw = el.textContent.replace(/[^0-9.]/g, '');
    var target = parseFloat(raw);
    if (isNaN(target) || target === 0) return;
    var isMoney = el.dataset.fmt === 'money';
    var start = performance.now();
    var dur = 1100;
    function tick(now) {
      var p = Math.min(1, (now - start) / dur);
      var ease = 1 - Math.pow(1 - p, 3);
      var val = target * ease;
      el.textContent = isMoney
        ? '$' + val.toFixed(2).replace(/\B(?=(\d{3})+(?!\d))/g, ',')
        : Math.round(val).toLocaleString();
      if (p < 1) requestAnimationFrame(tick);
    }
    requestAnimationFrame(tick);
  }
  var obs = new IntersectionObserver(function(entries) {
    entries.forEach(function(e) {
      if (e.isIntersecting) {
        e.target.querySelectorAll('.ds-stat-v').forEach(countUp);
        obs.unobserve(e.target);
      }
    });
  }, { threshold: 0.5 });
  document.addEventListener('DOMContentLoaded', function() {
    document.querySelectorAll('.ds-stats').forEach(function(el) { obs.observe(el); });
  });
})();
''')

    if 'parallax' in anims:
        parts.append(r'''
(function(){
  var ticking = false;
  function onScroll() {
    if (!ticking) {
      requestAnimationFrame(function() {
        var hero = document.querySelector('.ds-screen.visible .ds-hero');
        if (hero) {
          var offset = (window.scrollY * 0.32).toFixed(1);
          hero.style.backgroundPositionY = offset + 'px';
        }
        ticking = false;
      });
      ticking = true;
    }
  }
  window.addEventListener('scroll', onScroll, { passive: true });
})();
''')

    if 'typewriter' in anims:
        parts.append(r'''
(function(){
  function _esc(s) {
    return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
  }
  document.addEventListener('DOMContentLoaded', function() {
    document.querySelectorAll('.ds-hero-h').forEach(function(el) {
      var full = el.textContent.trim();
      // Wrap each character in a span starting invisible.
      // Text stays in the DOM so layout never shifts.
      el.innerHTML = full.split('').map(function(ch) {
        var encoded = ch === ' ' ? '&nbsp;' : _esc(ch);
        return '<span class="tw-ch" style="opacity:0">' + encoded + '</span>';
      }).join('');
      var spans = el.querySelectorAll('.tw-ch');
      var delay = 120; // slight delay so the hero entrance plays first
      spans.forEach(function(span) {
        setTimeout(function() { span.style.opacity = '1'; }, delay);
        delay += 42 + Math.random() * 22;
      });
      setTimeout(function() { el.classList.add('tw-done'); }, delay + 600);
    });
  });
})();
''')

    return ''.join(parts)


# ---------- screen layout -------------------------------------------------


_LAYOUT_CLASS = {
    'centered': 'ds-layout-centered',
    'card': 'ds-layout-card',
    'full': 'ds-layout-full',
    'sidebar': 'ds-layout-sidebar',
    'two-col': 'ds-layout-two-col',
    'hero': 'ds-layout-hero',
    'minimal': 'ds-layout-minimal',
    'dashboard': 'ds-layout-dashboard',
    'split': 'ds-layout-split',
    'split-preview': 'ds-layout-split-preview',
}


def _render_components(components: list, ctx: dict, theme: Theme) -> str:
    """Render a list of components to HTML."""
    has_list = any(isinstance(c, ListComponent) for c in components)
    parts = []
    for comp in components:
        if isinstance(comp, HeroComponent):
            parts.append(_hero(comp, theme))
        elif isinstance(comp, TextComponent):
            parts.append(_text_comp(comp))
        elif isinstance(comp, ColumnsComponent):
            parts.append(_columns(comp, theme))
        elif isinstance(comp, CTAComponent):
            parts.append(_cta(comp, theme))
        elif isinstance(comp, DividerComponent):
            parts.append(_divider(comp))
        elif isinstance(comp, TestimonialsComponent):
            parts.append(_testimonials(comp, theme))
        elif isinstance(comp, PricingComponent):
            parts.append(_pricing(comp, theme))
        elif isinstance(comp, StepsComponent):
            parts.append(_steps(comp, theme))
        elif isinstance(comp, SVGComponent):
            parts.append(_svg_comp(comp, theme))
        elif isinstance(comp, ImageComponent):
            parts.append(_image(comp, theme))
        elif isinstance(comp, HeaderComponent):
            parts.append(_header(comp, theme))
        elif isinstance(comp, StatsComponent):
            parts.append(_stats(comp, theme))
        elif isinstance(comp, FormComponent):
            parts.append(_form(comp, ctx, theme))
        elif isinstance(comp, ListComponent):
            parts.append(_list(comp, ctx, theme))
        elif isinstance(comp, EmptyComponent):
            parts.append(_empty(comp, theme, hidden=has_list))
        elif isinstance(comp, TrustComponent):
            parts.append(_trust(comp))
        elif isinstance(comp, WizardComponent):
            parts.append(_wizard(comp, theme))
        elif isinstance(comp, Model3DComponent):
            parts.append(_model3d(comp, theme))
    return ''.join(parts)


def _screen_html(screen, spec: DesignSpec, ctx: dict) -> str:
    layout_cls = _LAYOUT_CLASS.get(screen.layout, 'ds-layout-centered')
    theme = spec.theme

    # Split-preview: two-column layout with live detail panel on the right
    if screen.layout == 'split-preview':
        entity = screen.preview_entity or next(
            (c.entity for c in screen.components if isinstance(c, ListComponent)), ''
        )
        controls_html = _render_components(screen.components, ctx, theme)
        return (
            f'<section class="ds-screen ds-layout-split-preview" id="s-{_esc(screen.name)}">'
            f'<div class="ds-split-controls">{controls_html}</div>'
            f'<div class="ds-split-preview">'
            f'<div class="ds-split-preview-header">'
            f'<span class="ds-split-preview-title">Preview</span>'
            f'</div>'
            f'<div class="ds-split-preview-body">'
            f'{_split_preview_panel(entity, theme)}'
            f'</div>'
            f'</div>'
            f'</section>'
        )

    return (
        f'<section class="ds-screen {layout_cls}" id="s-{_esc(screen.name)}">'
        f'{_render_components(screen.components, ctx, theme)}'
        f'</section>'
    )


# ---------- full page -------------------------------------------------------


_BASE_CSS = '''
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
html { scroll-behavior: smooth; }
body { font-family: var(--ds-font, 'Inter', system-ui, sans-serif);
  background: var(--ds-bg, #f1f5f9); color: var(--ds-text, #0f172a); line-height: 1.5; }

/* nav */
.ds-nav { display: flex; align-items: center; gap: 4px;
  padding: 0 28px; height: 66px; background: rgba(255,255,255,.95);
  backdrop-filter: blur(14px); -webkit-backdrop-filter: blur(14px);
  border-bottom: 1px solid rgba(0,0,0,.07); position: sticky; top: 0; z-index: 100; }
.ds-nav-brand { font-weight: 900; font-size: 19px; color: var(--primary, #6366f1);
  letter-spacing: -.04em; flex-shrink: 0; }
.ds-nav-links { display: flex; align-items: center; gap: 2px; flex: 1; margin: 0 12px; }
.ds-nav-btn { padding: 7px 15px; border: 1.5px solid transparent;
  border-radius: 8px; background: none; cursor: pointer; font-size: 13px;
  font-weight: 500; color: #475569; transition: background .12s, color .12s; white-space: nowrap; }
.ds-nav-btn:hover { background: #f1f5f9; color: #0f172a; }
.ds-nav-btn.active { background: var(--primary, #6366f1); color: white; }
.ds-nav-end { display: flex; align-items: center; gap: 4px; margin-left: auto; }
.ds-nav-icon { display: flex; align-items: center; justify-content: center;
  width: 38px; height: 38px; border: none; border-radius: 10px; background: none;
  cursor: pointer; color: #64748b; transition: background .12s, color .12s; }
.ds-nav-icon:hover { background: #f1f5f9; color: #0f172a; }

/* screens */
.ds-screen:not(.visible) { display: none !important; }
.ds-screen { min-height: calc(100vh - 62px); }
.ds-screen.visible { display: block; }
.ds-layout-centered { max-width: 680px; margin: 0 auto; padding: 52px 24px; }
.ds-layout-card { align-items: flex-start; justify-content: center; padding: 64px 24px; }
.ds-layout-card > * { width: 100%; max-width: 460px; background: white;
  border-radius: 20px; padding: 40px; box-shadow: 0 4px 24px rgba(0,0,0,.08), 0 0 0 1px rgba(0,0,0,.04); }
.ds-screen.visible.ds-layout-card { display: flex; }
.ds-layout-full { padding: 40px 32px; }
.ds-layout-dashboard { padding: 40px 32px; gap: 24px; }
.ds-screen.visible.ds-layout-dashboard { display: grid; }
.ds-layout-two-col { padding: 40px 32px; grid-template-columns: 1fr 1fr; gap: 32px; }
.ds-screen.visible.ds-layout-two-col { display: grid; }
.ds-layout-sidebar { grid-template-columns: 260px 1fr; }
.ds-screen.visible.ds-layout-sidebar { display: grid; }
.ds-layout-hero { padding: 0; }
.ds-layout-minimal { max-width: 560px; margin: 0 auto; padding: 48px 24px; }
.ds-layout-split { grid-template-columns: 1fr 1fr; min-height: calc(100vh - 62px); }
.ds-screen.visible.ds-layout-split { display: grid; }

/* hero — break out of narrow containers so it always goes full-bleed */
.ds-hero { text-align: center; padding: 110px 32px 90px; position: relative; overflow: hidden; }
.ds-layout-centered .ds-hero,
.ds-layout-minimal .ds-hero { margin: -52px -24px 0; width: calc(100% + 48px); }
.ds-hero::before { content: ''; position: absolute; inset: 0;
  background-image: radial-gradient(circle at 1px 1px, rgba(255,255,255,.18) 1px, transparent 0);
  background-size: 28px 28px; pointer-events: none; }
.ds-hero-inner { position: relative; z-index: 1; max-width: 700px; margin: 0 auto; }
.ds-hero-h { font-size: clamp(38px, 6vw, 68px); font-weight: 900; color: white;
  line-height: 1.05; letter-spacing: -.04em; margin-bottom: 22px; }
.ds-hero-sub { font-size: clamp(16px, 2.5vw, 20px); color: rgba(255,255,255,.82);
  margin-bottom: 40px; max-width: 540px; margin-left: auto; margin-right: auto; line-height: 1.6; }
.ds-hero-btns { display: flex; flex-wrap: wrap; gap: 12px; justify-content: center; }
.ds-hero-cta { display: inline-flex; align-items: center; gap: 8px;
  padding: 15px 32px; background: white; border-radius: 12px; border: none;
  cursor: pointer; font-size: 16px; font-weight: 700;
  box-shadow: 0 4px 20px rgba(0,0,0,.18); transition: transform .15s, box-shadow .15s; }
.ds-hero-cta:hover { transform: translateY(-2px); box-shadow: 0 8px 32px rgba(0,0,0,.22); }

/* section header bar */
.ds-header { display: flex; align-items: center; justify-content: space-between;
  padding-bottom: 20px; margin-bottom: 28px; border-bottom: 1px solid #e2e8f0; }
.ds-header-title { font-size: 22px; font-weight: 800; color: #0f172a; letter-spacing: -.02em; }
.ds-header-actions { display: flex; gap: 8px; }

/* stats */
.ds-stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 16px; margin-bottom: 32px; }
.ds-stat { background: white; border-radius: 14px; padding: 22px 24px; border-top: 3px solid var(--primary, #6366f1);
  box-shadow: 0 1px 4px rgba(0,0,0,.06), 0 0 0 1px rgba(0,0,0,.04); }
.ds-stat-v { font-size: 34px; font-weight: 900; display: block; letter-spacing: -.04em; line-height: 1.1; }
.ds-stat-l { font-size: 11px; color: #64748b; margin-top: 8px; display: block;
  font-weight: 700; letter-spacing: .06em; text-transform: uppercase; }

/* form */
.ds-form { display: grid; gap: 20px; }
.ds-field { display: grid; gap: 6px; }
.ds-label { font-size: 13px; font-weight: 600; color: #374151; }
.ds-input { width: 100%; padding: 11px 14px; border: 1.5px solid #e2e8f0;
  border-radius: var(--ds-radius, 10px); font-size: 14px; background: white;
  color: #0f172a; outline: none; transition: border-color .15s, box-shadow .15s;
  font-family: inherit; }
.ds-input::placeholder { color: #94a3b8; }
.ds-input:focus { border-color: var(--primary, #6366f1); box-shadow: 0 0 0 3px rgba(99,102,241,.15); }
.ds-input-lg { font-size: 24px; padding: 16px 18px; font-weight: 700; letter-spacing: -.02em; }
.ds-toggle { display: flex; align-items: center; gap: 10px; font-size: 14px; color: #374151; cursor: pointer; font-weight: 500; }

/* buttons */
.ds-btn { display: inline-flex; align-items: center; gap: 6px; padding: 10px 20px;
  border: 1.5px solid #e2e8f0; border-radius: var(--ds-radius, 10px); cursor: pointer;
  font-size: 14px; font-weight: 600; background: white; color: #374151;
  transition: background .12s, border-color .12s, transform .1s; font-family: inherit; }
.ds-btn:hover { background: #f8fafc; border-color: #cbd5e1; }
.ds-btn-primary { color: white; border-color: transparent; box-shadow: 0 2px 8px rgba(0,0,0,.18); }
.ds-btn-primary:hover { opacity: .92; transform: translateY(-1px); box-shadow: 0 4px 16px rgba(0,0,0,.22); }
.ds-btn-sm { padding: 5px 12px; font-size: 12px; border-radius: 7px; }

/* table */
.ds-table-wrap { background: white; border-radius: 14px; overflow: hidden;
  box-shadow: 0 1px 4px rgba(0,0,0,.06), 0 0 0 1px rgba(0,0,0,.04); }
.ds-table { width: 100%; border-collapse: collapse; font-size: 14px; }
.ds-table thead { background: #f8fafc; }
.ds-table th { text-align: left; font-size: 11px; color: #64748b; font-weight: 700;
  padding: 13px 16px; letter-spacing: .06em; text-transform: uppercase;
  border-bottom: 1px solid #e2e8f0; }
.ds-table td { padding: 14px 16px; border-top: 1px solid #f1f5f9; color: #334155; }
.ds-table tbody tr:hover { background: #f8fafc; }
.ds-table-wrap + .ds-table-wrap { margin-top: 16px; }

/* generic cards */
.ds-cards { display: grid; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); gap: 16px; }
.ds-card { background: white; border-radius: 14px; padding: 22px;
  box-shadow: 0 1px 4px rgba(0,0,0,.06), 0 0 0 1px rgba(0,0,0,.04);
  transition: box-shadow .15s, transform .15s; }
.ds-card:hover { box-shadow: 0 8px 28px rgba(0,0,0,.1); transform: translateY(-2px); }
.ds-card-field { display: flex; justify-content: space-between; align-items: center;
  padding: 8px 0; border-bottom: 1px solid #f1f5f9; font-size: 13px; }
.ds-card-field:last-child { border-bottom: none; padding-bottom: 0; }
.ds-card-key { color: #64748b; font-weight: 500; }
.ds-card-val { font-weight: 600; color: #0f172a; }

/* product cards (entity with price field) */
.ds-pcards { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 22px; }
.ds-pcard { background: white; border-radius: 18px; overflow: hidden;
  box-shadow: 0 1px 4px rgba(0,0,0,.06), 0 0 0 1px rgba(0,0,0,.04);
  transition: box-shadow .22s, transform .22s; display: flex; flex-direction: column; }
.ds-pcard:hover { box-shadow: 0 16px 48px rgba(0,0,0,.13); transform: translateY(-4px); }
.ds-pcard-img { height: 180px; display: flex; align-items: center; justify-content: center;
  font-size: 48px; flex-shrink: 0; position: relative; overflow: hidden; }
.ds-pcard-img::after { content: ''; position: absolute; inset: 0;
  background-image: radial-gradient(circle at 1px 1px, rgba(255,255,255,.12) 1px, transparent 0);
  background-size: 18px 18px; }
.ds-pcard-body { padding: 18px 20px 20px; display: flex; flex-direction: column; flex: 1; }
.ds-pcard-name { font-size: 15px; font-weight: 700; color: #0f172a; margin-bottom: 4px;
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
.ds-pcard-meta { font-size: 12px; color: #64748b; margin-bottom: 10px; display: block; }
.ds-pcard-price { font-size: 24px; font-weight: 900; color: var(--primary, #6366f1);
  letter-spacing: -.03em; margin-bottom: 16px; display: block; margin-top: auto; }
.ds-pcard-footer { display: flex; gap: 8px; }
.ds-pcard-cta { flex: 1; justify-content: center; padding: 11px 16px; border-radius: 12px; }

/* skeleton loading */
@keyframes ds-shimmer { 0% { background-position: -400px 0; } 100% { background-position: 400px 0; } }
.ds-skel { border-radius: 8px; background: linear-gradient(90deg, #f1f5f9 25%, #e2e8f0 50%, #f1f5f9 75%);
  background-size: 800px 100%; animation: ds-shimmer 1.4s infinite; }
.ds-skel-wrap { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 22px; padding: 0; background: none; }
.ds-skel-card { background: white; border-radius: 18px; overflow: hidden; box-shadow: 0 1px 4px rgba(0,0,0,.06); }
.ds-skel-img { height: 180px; border-radius: 0; }
.ds-skel-body { padding: 18px 20px 20px; }
.ds-skel-line { height: 14px; margin-bottom: 10px; }
.ds-skel-w70 { width: 70%; }
.ds-skel-w40 { width: 40%; }
.ds-skel-btn { height: 40px; margin-top: 16px; border-radius: 12px; }

/* rows */
.ds-rows { display: grid; gap: 10px; }
.ds-row { display: flex; flex-wrap: wrap; align-items: center; gap: 12px; background: white;
  border-radius: 12px; padding: 15px 20px; font-size: 14px;
  box-shadow: 0 1px 3px rgba(0,0,0,.05), 0 0 0 1px rgba(0,0,0,.04);
  transition: box-shadow .15s; }
.ds-row:hover { box-shadow: 0 4px 14px rgba(0,0,0,.08); }
.ds-row-cell { color: #475569; font-size: 13px; }
.ds-row-cell b { color: #0f172a; }

/* list loading / empty states */
.ds-list-loading { padding: 40px 24px; text-align: center; color: #94a3b8; font-size: 14px; }
.ds-list-empty { padding: 40px 24px; text-align: center; color: #94a3b8; font-size: 14px; }

/* standalone empty state */
.ds-empty { display: flex; flex-direction: column; align-items: center; justify-content: center;
  padding: 72px 24px; text-align: center; }
.ds-empty p { font-size: 16px; color: #64748b; margin: 0 0 24px; max-width: 340px; }
.ds-empty-icon { font-size: 48px; margin-bottom: 16px; }

/* trust / social proof */
.ds-trust { display: flex; flex-wrap: wrap; align-items: center; justify-content: center;
  gap: 24px; padding: 36px 32px; color: #94a3b8; font-size: 12px;
  font-weight: 700; letter-spacing: .06em; text-transform: uppercase;
  border-top: 1px solid #e2e8f0; background: white; }

/* submit feedback */
.ds-msg { padding: 11px 14px; border-radius: 9px; font-size: 13px; font-weight: 500; margin-top: 14px; }
.ds-msg-ok { background: #f0fdf4; color: #15803d; border: 1px solid #bbf7d0; }
.ds-msg-err { background: #fef2f2; color: #dc2626; border: 1px solid #fecaca; }
.ds-msg-load { background: #f8fafc; color: #64748b; border: 1px solid #e2e8f0; }

/* misc */
.ds-empty-note { color: #94a3b8; font-style: italic; padding: 20px 0; font-size: 13px; }

/* text component */
.ds-text-h1 { font-size: clamp(32px, 5vw, 60px); font-weight: 900; line-height: 1.1; letter-spacing: -.04em; color: #0f172a; margin-bottom: 20px; }
.ds-text-h2 { font-size: clamp(22px, 4vw, 40px); font-weight: 800; line-height: 1.15; letter-spacing: -.03em; color: #0f172a; margin-bottom: 16px; }
.ds-text-h3 { font-size: clamp(18px, 3vw, 28px); font-weight: 700; line-height: 1.2; color: #0f172a; margin-bottom: 14px; }
.ds-text-h4 { font-size: 20px; font-weight: 700; color: #0f172a; margin-bottom: 12px; }
.ds-text-body { font-size: 15px; color: #64748b; line-height: 1.7; margin-bottom: 16px; max-width: 65ch; }
.ds-text-large { font-size: 20px; color: #475569; line-height: 1.6; margin-bottom: 18px; max-width: 65ch; }
.ds-text-lead { font-size: 18px; color: #475569; line-height: 1.7; margin-bottom: 18px; max-width: 65ch; }
.ds-text-small { font-size: 13px; color: #94a3b8; line-height: 1.6; margin-bottom: 10px; }
.ds-text-center { text-align: center; margin-left: auto; margin-right: auto; }
.ds-text-right { text-align: right; margin-left: auto; }
.ds-text-left { text-align: left; }

/* columns / feature grid */
.ds-columns { display: grid; gap: 24px; margin: 40px 0; }
.ds-columns-2 { grid-template-columns: repeat(2, 1fr); }
.ds-columns-3 { grid-template-columns: repeat(3, 1fr); }
.ds-columns-4 { grid-template-columns: repeat(4, 1fr); }
@media (max-width: 768px) {
  .ds-columns-2, .ds-columns-3, .ds-columns-4 { grid-template-columns: 1fr; }
}
.ds-col-item { display: flex; flex-direction: column; gap: 10px; padding: 28px;
  background: white; border-radius: 16px;
  box-shadow: 0 1px 4px rgba(0,0,0,.06), 0 0 0 1px rgba(0,0,0,.04); }
.ds-col-icon { font-size: 28px; width: 56px; height: 56px; display: flex;
  align-items: center; justify-content: center; background: #f1f5f9; border-radius: 12px; }
.ds-col-title { font-size: 16px; font-weight: 700; color: #0f172a; }
.ds-col-body { font-size: 14px; color: #64748b; line-height: 1.65; }

/* CTA banner */
.ds-cta { padding: 80px 32px; text-align: center; }
.ds-cta-inner { max-width: 580px; margin: 0 auto; display: flex; flex-direction: column; align-items: center; gap: 14px; }
.ds-cta-heading { font-size: clamp(28px, 5vw, 46px); font-weight: 900; letter-spacing: -.04em; color: inherit; }
.ds-cta-sub { font-size: 18px; opacity: .8; color: inherit; }
.ds-btn-cta { padding: 16px 36px; font-size: 16px; border-radius: 12px; font-weight: 700; margin-top: 8px; }

/* divider */
.ds-divider { display: flex; align-items: center; gap: 16px; margin: 40px 0; }
.ds-divider::before, .ds-divider::after { content: ''; flex: 1; height: 1px; background: #e2e8f0; }
.ds-divider:empty::after { display: none; }
.ds-divider-label { font-size: 12px; color: #94a3b8; font-weight: 600;
  letter-spacing: .06em; text-transform: uppercase; white-space: nowrap; }

/* testimonials */
.ds-testimonials { display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 20px; margin: 32px 0; }
.ds-testimonial { background: white; border-radius: 16px; padding: 28px;
  box-shadow: 0 1px 4px rgba(0,0,0,.06), 0 0 0 1px rgba(0,0,0,.04);
  display: flex; flex-direction: column; gap: 10px; }
.ds-testimonial-stars { font-size: 16px; letter-spacing: 2px; }
.ds-testimonial-text { font-size: 15px; line-height: 1.65; color: #374151; font-style: italic; flex: 1; }
.ds-testimonial-author { font-size: 13px; font-weight: 600; color: #94a3b8; }

/* pricing */
.ds-pricing { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
  gap: 24px; margin: 32px 0; align-items: start; }
.ds-tier { border-radius: 20px; padding: 36px 32px;
  box-shadow: 0 1px 4px rgba(0,0,0,.06), 0 0 0 1px rgba(0,0,0,.06);
  display: flex; flex-direction: column; gap: 8px; }
.ds-tier-hl { box-shadow: 0 20px 60px rgba(0,0,0,.18); transform: scale(1.04); }
.ds-tier-name { font-size: 12px; font-weight: 800; letter-spacing: .1em; text-transform: uppercase; opacity: .6; }
.ds-tier-price { display: flex; align-items: flex-end; gap: 2px; margin: 8px 0 20px; line-height: 1; }
.ds-tier-currency { font-size: 20px; font-weight: 700; padding-bottom: 4px; }
.ds-tier-amount { font-size: 52px; font-weight: 900; letter-spacing: -.04em; }
.ds-tier-period { font-size: 13px; opacity: .5; padding-bottom: 6px; margin-left: 2px; }
.ds-tier-features { list-style: none; display: flex; flex-direction: column; gap: 12px; margin: 4px 0 24px; }
.ds-tier-feature { display: flex; align-items: center; gap: 10px; font-size: 14px; }
.ds-tier-feature svg { flex-shrink: 0; }

/* steps */
.ds-steps { list-style: none; display: flex; flex-direction: column; gap: 20px; margin: 32px 0; }
.ds-step { display: flex; align-items: flex-start; gap: 16px; }
.ds-step-num { display: flex; align-items: center; justify-content: center;
  width: 36px; height: 36px; min-width: 36px; border-radius: 50%;
  color: white; font-size: 14px; font-weight: 800; }
.ds-step-text { font-size: 15px; color: #374151; line-height: 1.6; padding-top: 6px; }

/* svg */
.ds-svg-wrap { display: flex; justify-content: center; align-items: center; margin: 16px 0; }
.ds-svg-wrap svg { max-width: 100%; height: auto; display: block; }
.ds-svg-img { max-width: 100%; height: auto; display: block; }
.ds-svg-placeholder { display: flex; align-items: center; justify-content: center;
  border-radius: 14px; margin: 16px 0; }
'''

_EXTRA_CSS = '''
/* wizard */
.ds-wizard { background: white; border-radius: 20px;
  box-shadow: 0 1px 4px rgba(0,0,0,.06), 0 0 0 1px rgba(0,0,0,.04); overflow: hidden; }
.ds-wiz-header { padding: 28px 28px 0; }
.ds-wiz-progress { height: 4px; background: #e2e8f0; border-radius: 2px; margin-bottom: 24px; }
.ds-wiz-bar { height: 100%; border-radius: 2px; transition: width .4s cubic-bezier(.22,.68,0,1.1); }
.ds-wiz-steps { display: flex; gap: 0; background: #f8fafc; border-radius: 10px;
  padding: 4px; margin-bottom: 28px; }
.ds-wiz-step { flex: 1; display: flex; flex-direction: column; align-items: center;
  gap: 5px; padding: 10px 6px; border-radius: 8px; transition: background .15s; }
.ds-wiz-step--active { background: white; box-shadow: 0 1px 4px rgba(0,0,0,.08); }
.ds-wiz-snum { width: 24px; height: 24px; border-radius: 50%; background: #e2e8f0;
  display: flex; align-items: center; justify-content: center;
  font-size: 12px; font-weight: 800; color: #64748b; transition: background .15s, color .15s; }
.ds-wiz-step--active .ds-wiz-snum { background: var(--primary, #6366f1); color: white; }
.ds-wiz-step--done .ds-wiz-snum { background: #bbf7d0; color: #15803d; }
.ds-wiz-slabel { font-size: 11px; font-weight: 600; color: #94a3b8; text-align: center; line-height: 1.3; }
.ds-wiz-step--active .ds-wiz-slabel { color: #0f172a; }
.ds-wiz-pane { padding: 0 28px 24px; display: none; }
.ds-wiz-pane-title { font-size: 17px; font-weight: 700; color: #0f172a; margin-bottom: 18px; }
.ds-wiz-nav { display: flex; align-items: center; justify-content: space-between; gap: 12px;
  padding: 18px 28px 24px; border-top: 1px solid #f1f5f9; }

/* model3d */
.ds-model3d-wrap { margin: 16px 0; border-radius: 14px; overflow: hidden;
  box-shadow: 0 1px 4px rgba(0,0,0,.06); }
.ds-model3d-placeholder { display: flex; flex-direction: column; align-items: center;
  justify-content: center; padding: 48px 32px; background: #f8fafc;
  border-radius: 14px; border: 1px solid #e2e8f0; gap: 20px; margin: 16px 0; }
.ds-model3d-cube { width: 100px; height: 100px; position: relative;
  transform-style: preserve-3d; animation: ds-cube-spin 9s linear infinite; }
.ds-cube-face { position: absolute; width: 100px; height: 100px; border-radius: 4px; }
.ds-cube-front  { transform: translateZ(50px); }
.ds-cube-back   { transform: rotateY(180deg) translateZ(50px); }
.ds-cube-right  { transform: rotateY(90deg) translateZ(50px); }
.ds-cube-left   { transform: rotateY(-90deg) translateZ(50px); }
.ds-cube-top    { transform: rotateX(90deg) translateZ(50px); }
.ds-cube-bottom { transform: rotateX(-90deg) translateZ(50px); }
@keyframes ds-cube-spin {
  from { transform: rotateX(14deg) rotateY(0); }
  to   { transform: rotateX(14deg) rotateY(360deg); }
}
@keyframes ds-float { 0%,100% { transform: translateY(0); } 50% { transform: translateY(-14px); } }
.ds-model3d-label { font-size: 13px; color: #64748b; font-weight: 500; }

/* split-preview layout */
.ds-layout-split-preview { grid-template-columns: 1fr 1fr; min-height: calc(100vh - 62px); }
.ds-screen.visible.ds-layout-split-preview { display: grid; }
.ds-split-controls { padding: 40px 32px; overflow-y: auto; border-right: 1px solid #e2e8f0; }
.ds-split-preview { background: #f8fafc; display: flex; flex-direction: column;
  position: sticky; top: 62px; height: calc(100vh - 62px); }
.ds-split-preview-header { padding: 20px 24px 16px; border-bottom: 1px solid #e2e8f0; }
.ds-split-preview-title { font-size: 11px; font-weight: 800; letter-spacing: .1em;
  text-transform: uppercase; color: #94a3b8; }
.ds-split-preview-body { flex: 1; overflow-y: auto; padding: 24px; }
.ds-split-empty { display: flex; flex-direction: column; align-items: center;
  justify-content: center; height: 100%; color: #94a3b8; font-size: 14px; gap: 12px; }
.ds-split-detail { display: none; }
.ds-detail-list { display: grid; gap: 0; }
.ds-detail-row { display: grid; grid-template-columns: 130px 1fr; gap: 8px;
  padding: 12px 0; border-bottom: 1px solid #f1f5f9; align-items: baseline; }
.ds-detail-row:last-child { border-bottom: none; }
.ds-detail-row dt { font-size: 12px; font-weight: 600; color: #94a3b8;
  text-transform: capitalize; letter-spacing: .03em; }
.ds-detail-row dd { font-size: 14px; color: #0f172a; font-weight: 500; }
@media (max-width: 900px) {
  .ds-layout-split-preview { grid-template-columns: 1fr; }
  .ds-split-preview { position: static; height: auto; border-top: 1px solid #e2e8f0; }
}
'''

_NAV_JS = '''
function _fmtVal(v, fmt) {
  if (v == null || v === '') return '—';
  if (fmt === 'money') {
    var n = parseFloat(v);
    if (isNaN(n)) return v;
    return '$' + n.toFixed(2).replace(/\B(?=(\d{3})+(?!\d))/g, ',');
  }
  return v;
}
function _fillFields(el, rec) {
  el.querySelectorAll('[data-field]').forEach(function(cell) {
    cell.textContent = _fmtVal(rec[cell.dataset.field], cell.dataset.fmt);
  });
}
function loadLists(screenEl) {
  screenEl.querySelectorAll('[data-list]').forEach(function(container) {
    var entity = container.dataset.list;
    if (!entity) return;
    var listStyle = container.dataset.listStyle || 'table';
    var loading = container.querySelector('.ds-list-loading');
    var emptyEl = container.querySelector('.ds-list-empty');
    if (loading) loading.hidden = false;
    if (emptyEl) emptyEl.hidden = true;
    fetch('/api/data/' + encodeURIComponent(entity))
      .then(function(r) { return r.json(); })
      .then(function(payload) {
        if (loading) loading.hidden = true;
        var items = Array.isArray(payload) ? payload : (payload.items || payload.data || []);
        if (listStyle === 'table') {
          var tbody = container.querySelector('[data-list-body]');
          var tpl = tbody && tbody.querySelector('.ds-row-tpl');
          if (!tbody || !tpl) return;
          tbody.querySelectorAll('tr:not(.ds-row-tpl)').forEach(function(r) { r.remove(); });
          if (items.length === 0) { if (emptyEl) emptyEl.hidden = false; return; }
          var frag = document.createDocumentFragment();
          items.forEach(function(rec) {
            var row = tpl.cloneNode(true);
            row.classList.remove('ds-row-tpl'); row.hidden = false;
            _fillFields(row, rec);
            frag.appendChild(row);
          });
          tbody.appendChild(frag);
        } else {
          var tplSel = listStyle === 'pcards' ? '.ds-card-tpl' : (listStyle === 'cards' ? '.ds-card-tpl' : '.ds-row-tpl');
          var itemSel = listStyle === 'pcards' ? '.ds-pcard:not(.ds-card-tpl)' : (listStyle === 'cards' ? '.ds-card:not(.ds-card-tpl)' : '.ds-row:not(.ds-row-tpl)');
          var tpl = container.querySelector(tplSel);
          if (!tpl) return;
          container.querySelectorAll(itemSel).forEach(function(el) { el.remove(); });
          if (items.length === 0) { if (emptyEl) emptyEl.hidden = false; return; }
          var frag = document.createDocumentFragment();
          items.forEach(function(rec) {
            var card = tpl.cloneNode(true);
            card.classList.remove('ds-card-tpl', 'ds-row-tpl'); card.hidden = false;
            _fillFields(card, rec);
            frag.appendChild(card);
          });
          container.insertBefore(frag, tpl);
        }
      })
      .catch(function() {
        if (loading) loading.hidden = true;
        if (emptyEl) { emptyEl.hidden = false; emptyEl.textContent = 'Failed to load data.'; }
      });
  });
}

function loadChoices(screenEl) {
  screenEl.querySelectorAll('[data-choices-from]').forEach(function(sel) {
    var entity = sel.dataset.choicesFrom;
    fetch('/api/data/' + encodeURIComponent(entity))
      .then(function(r) { return r.json(); })
      .then(function(payload) {
        var items = Array.isArray(payload) ? payload : (payload.items || payload.data || []);
        sel._allItems = items;
        sel.innerHTML = '<option value="">Select ' + entity + '…</option>';
        items.forEach(function(item) {
          var opt = document.createElement('option');
          opt.value = item.id || item.sku || item.name || JSON.stringify(item);
          opt.textContent = item.name || item.title || item.sku || item.id || JSON.stringify(item);
          sel.appendChild(opt);
        });
        var dep = sel.dataset.dependsOn;
        if (dep && sel.dataset.filter) {
          var depField = screenEl.querySelector('[name="' + dep + '"]');
          if (depField) {
            depField.addEventListener('change', function() {
              _filterChoices(sel, depField.value);
            });
          }
        }
      })
      .catch(function() {
        sel.innerHTML = '<option value="">Options unavailable</option>';
      });
  });
}

function _filterChoices(sel, depValue) {
  var filterStr = sel.dataset.filter || '';
  var m = filterStr.match(/(\w+)\s*==\s*\w+\.(\w+)/);
  var items = sel._allItems || [];
  sel.innerHTML = '<option value="">Select…</option>';
  items.forEach(function(item) {
    var match = !m || String(item[m[1]]) === String(depValue);
    if (match) {
      var opt = document.createElement('option');
      opt.value = item.id || item.sku || item.name || JSON.stringify(item);
      opt.textContent = item.name || item.title || item.sku || item.id || JSON.stringify(item);
      sel.appendChild(opt);
    }
  });
}

(function() {
  function initWizard(wiz) {
    var panes = wiz.querySelectorAll('.ds-wiz-pane');
    var steps = wiz.querySelectorAll('.ds-wiz-step');
    var prevBtn = wiz.querySelector('.ds-wiz-prev');
    var nextBtn = wiz.querySelector('.ds-wiz-next');
    var submitBtn = wiz.querySelector('.ds-wiz-submit');
    var bar = wiz.querySelector('.ds-wiz-bar');
    var total = panes.length;
    var cur = 0;
    function update() {
      panes.forEach(function(p, i) { p.style.display = i === cur ? 'block' : 'none'; });
      steps.forEach(function(s, i) {
        s.classList.toggle('ds-wiz-step--active', i === cur);
        s.classList.toggle('ds-wiz-step--done', i < cur);
      });
      if (bar) bar.style.width = ((cur + 1) / total * 100) + '%';
      if (prevBtn) prevBtn.disabled = cur === 0;
      if (nextBtn) nextBtn.style.display = cur < total - 1 ? '' : 'none';
      if (submitBtn) submitBtn.style.display = cur === total - 1 ? '' : 'none';
    }
    if (nextBtn) nextBtn.addEventListener('click', function() { if (cur < total - 1) { cur++; update(); } });
    if (prevBtn) prevBtn.addEventListener('click', function() { if (cur > 0) { cur--; update(); } });
    if (submitBtn) submitBtn.addEventListener('click', function() {
      var data = {};
      wiz.querySelectorAll('input,select,textarea').forEach(function(el) {
        if (el.name) data[el.name] = el.type === 'checkbox' ? el.checked : (el.type === 'number' ? (el.value === '' ? null : +el.value) : el.value);
      });
      var flow = wiz.dataset.flow;
      var msgEl = document.getElementById(wiz.id + '-msg');
      if (msgEl) { msgEl.className = 'ds-msg ds-msg-load'; msgEl.textContent = 'Submitting…'; }
      fetch('/api/' + flow, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(data)})
        .then(function(r) { return r.text().then(function(t) { try { return {ok:r.ok,data:JSON.parse(t)}; } catch(_) { return {ok:r.ok,data:t}; } }); })
        .then(function(res) {
          if (msgEl) {
            msgEl.className = 'ds-msg ' + (res.ok ? 'ds-msg-ok' : 'ds-msg-err');
            msgEl.textContent = res.ok ? '✓ Submitted!' : 'Error: ' + JSON.stringify(res.data);
          }
          if (res.ok) { wiz.querySelectorAll('input,select,textarea').forEach(function(el) { el.value = ''; }); cur = 0; update(); }
        })
        .catch(function(e) { if (msgEl) { msgEl.className = 'ds-msg ds-msg-err'; msgEl.textContent = 'Error: ' + e.message; } });
    });
    update();
  }
  document.addEventListener('DOMContentLoaded', function() {
    document.querySelectorAll('.ds-wizard').forEach(initWizard);
  });
})();

// Split-preview: clicking a row/card shows details in the right panel
document.addEventListener('click', function(e) {
  var row = e.target.closest('.ds-row:not(.ds-row-tpl),.ds-card:not(.ds-card-tpl),.ds-pcard:not(.ds-card-tpl)');
  if (!row) return;
  var screen = row.closest('.ds-layout-split-preview');
  if (!screen) return;
  var detail = screen.querySelector('.ds-split-detail');
  var empty = screen.querySelector('.ds-split-empty');
  if (!detail) return;
  var fields = {};
  row.querySelectorAll('[data-field]').forEach(function(el) { fields[el.dataset.field] = el.textContent; });
  var html = '<dl class="ds-detail-list">';
  Object.keys(fields).forEach(function(k) {
    html += '<div class="ds-detail-row"><dt>' + k.replace(/_/g, ' ') + '</dt><dd>' + fields[k] + '</dd></div>';
  });
  html += '</dl>';
  detail.innerHTML = html;
  detail.style.display = 'block';
  if (empty) empty.style.display = 'none';
});

function showScreen(name) {
  document.querySelectorAll('.ds-screen').forEach(function(s) { s.classList.remove('visible'); });
  document.querySelectorAll('.ds-nav-btn').forEach(function(b) { b.classList.remove('active'); });
  var s = document.getElementById('s-' + name);
  if (s) { s.classList.add('visible'); loadLists(s); loadChoices(s); }
  document.querySelectorAll('[data-screen="' + name + '"]').forEach(function(b) { b.classList.add('active'); });
}

function dsSubmit(e, method, path) {
  e.preventDefault();
  var form = e.target;
  var data = {};
  form.querySelectorAll('input,select,textarea').forEach(function(el) {
    if (!el.name) return;
    data[el.name] = el.type === 'checkbox' ? el.checked : (el.type === 'number' ? (el.value === '' ? null : +el.value) : el.value);
  });
  var msgEl = document.getElementById(form.id + '-msg');
  if (msgEl) { msgEl.className = 'ds-msg ds-msg-load'; msgEl.textContent = 'Submitting…'; }
  var apiPath = path.startsWith('/api') ? path : '/api' + path;
  fetch(apiPath, { method: method, headers: {'Content-Type': 'application/json'}, body: JSON.stringify(data) })
    .then(function(r) { return r.text().then(function(t) { try { return {ok: r.ok, status: r.status, data: JSON.parse(t)}; } catch(_) { return {ok: r.ok, status: r.status, data: t}; } }); })
    .then(function(res) {
      if (msgEl) {
        msgEl.className = 'ds-msg ' + (res.ok ? 'ds-msg-ok' : 'ds-msg-err');
        msgEl.textContent = res.ok ? '✓ Done' : 'Error ' + res.status + ': ' + JSON.stringify(res.data);
      }
      if (res.ok) {
        form.reset();
        // Refresh all visible list screens after a successful write
        document.querySelectorAll('.ds-screen.visible').forEach(function(s) { loadLists(s); });
      }
    })
    .catch(function(err) {
      if (msgEl) { msgEl.className = 'ds-msg ds-msg-err'; msgEl.textContent = 'Cannot reach ' + apiPath + ' — ' + err.message; }
    });
}

document.addEventListener('DOMContentLoaded', function() {
  var first = document.querySelector('.ds-screen');
  if (first) { first.classList.add('visible'); loadLists(first); loadChoices(first); }
  var firstBtn = first && document.querySelector('[data-screen="' + first.id.slice(2) + '"]');
  if (firstBtn) firstBtn.classList.add('active');
  document.querySelectorAll('.ds-nav-btn').forEach(function(b) {
    b.addEventListener('click', function() { showScreen(this.dataset.screen); });
  });
});
'''


def generate(spec: DesignSpec, ctx: dict) -> str:
    """Generate a self-contained HTML from a DesignSpec + backend context dict.
    List screens fetch live data from /api/data/<entity>.
    Forms POST to /api/<path> and refresh list screens on success."""
    theme = spec.theme
    brand = theme.brand or ctx.get('system', spec.system or 'App')

    css_vars = _css_vars(theme)
    font_link = _font_link(theme)
    if not theme.font:
        font_link = '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap">'

    mode_attr = ''
    if theme.mode == 'dark':
        mode_attr = ' data-mode="dark"'

    nav_buttons = ''.join(
        f'<button class="ds-nav-btn" data-screen="{_esc(s.name)}">{_esc(_title(s.name))}</button>'
        for s in spec.screens
    )

    screens_html = '\n'.join(_screen_html(s, spec, ctx) for s in spec.screens)

    primary = theme.colors.get('primary', '#6366f1')
    accent = theme.colors.get('accent', '#8b5cf6')
    anim_css = _anim_css(theme.animations)
    anim_js  = _anim_js(theme.animations)
    style_css = _style_css(theme)
    bg_css = _bg_css(theme)
    bg_js = _bg_js(theme)
    ia_css = _interactions_css(theme)
    ia_js  = _interactions_js(theme)

    has_model3d = any(
        isinstance(c, Model3DComponent) and c.src
        for s in spec.screens for c in s.components
    )
    model3d_script = (
        '<script type="module" src="https://unpkg.com/@google/model-viewer@4.0.0'
        '/dist/model-viewer.min.js"></script>'
        if has_model3d else ''
    )

    bg_video_html = ''
    if theme.background == 'video' and theme.background_src:
        bg_video_html = (
            f'<video id="ds-bg-video" autoplay muted loop playsinline>'
            f'<source src="{_esc(theme.background_src)}"></video>'
        )

    return f'''<!doctype html>
<html lang="en"{mode_attr}>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_esc(brand)}</title>
{font_link}
{model3d_script}
<style>
:root {{
  --primary: {primary};
  --accent: {accent};
{css_vars}
}}
{_BASE_CSS}
{_EXTRA_CSS}
{anim_css}
{style_css}
{bg_css}
{ia_css}
</style>
</head>
<body>
{bg_video_html}
<nav class="ds-nav">
  <span class="ds-nav-brand">{_esc(brand)}</span>
  <div class="ds-nav-links">{nav_buttons}</div>
  <div class="ds-nav-end">
    <button class="ds-nav-icon" aria-label="Search" title="Search">
      <svg width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/></svg>
    </button>
    <button class="ds-nav-icon ds-nav-cart" aria-label="Cart" title="Cart">
      <svg width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M6 2 3 6v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V6l-3-4z"/><line x1="3" y1="6" x2="21" y2="6"/><path d="M16 10a4 4 0 0 1-8 0"/></svg>
    </button>
  </div>
</nav>
{screens_html}
<script>{_NAV_JS}</script>
{('<script>' + anim_js + '</script>') if anim_js else ''}
{('<script>' + bg_js + '</script>') if bg_js else ''}
{('<script>' + ia_js + '</script>') if ia_js else ''}
</body>
</html>'''
