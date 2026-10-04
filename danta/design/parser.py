"""parser.py — Parse a Design Spec text into a DesignSpec object."""

import re

from danta.design.model import (
    ANIMATION_VALUES, BACKGROUND_VALUES, ColumnItem, ColumnsComponent, CTAComponent,
    DesignScreen, DesignSpec, DividerComponent, EmptyComponent, FieldHint, FormComponent,
    HeaderComponent, HeroComponent, ImageComponent, INTERACTION_VALUES, LAYOUTS, ListComponent,
    MODE_VALUES, Model3DComponent, PricingComponent, PricingTier, RADIUS_VALUES,
    StatsComponent, StepsComponent, STYLE_VALUES, SVGComponent, TestimonialItem,
    TestimonialsComponent, TextComponent, Theme, TrustComponent, WizardComponent, WizardStep,
)

_VERSION = re.compile(r'^Design:\s*danta/0\.1\s*$', re.MULTILINE)
_SYSTEM  = re.compile(r'^System:\s*([a-z][a-z0-9_-]*)\s*$', re.MULTILINE)
_SECTION = re.compile(r'^##\s+(.+?)\s*$', re.MULTILINE)
_SCREEN  = re.compile(r'^##\s+Screen:\s*([a-z][a-z0-9_]*)\s*$', re.MULTILINE)
_THEME   = re.compile(r'^##\s+Theme\s*$', re.MULTILINE)
_NAME    = r'[a-z][a-z0-9_]*'
_QUOTED  = re.compile(r'^"((?:[^"\\]|\\.)*)"$')


def _unquote(s: str) -> str:
    m = _QUOTED.match(s.strip())
    return m.group(1) if m else s.strip().strip('"')


def _prop(lines: list, key: str) -> tuple:
    pat = re.compile(rf'^{re.escape(key)}:\s*(.*)', re.IGNORECASE)
    for i, ln in enumerate(lines):
        m = pat.match(ln.strip())
        if m:
            return i, m.group(1).strip()
    return -1, None


def _raw_block(lines: list, start: int) -> str:
    """Collect raw lines after index `start` until end of block.

    Handles two forms:
      • Plain indented lines directly after the key
      • A fenced code block (```svg … ```) optionally preceded by a blank line
    Stops at a blank line after content (outside a fence) or a new Danta keyword.
    """
    result = []
    in_fence = False

    for ln in lines[start + 1:]:
        stripped = ln.strip()

        if not stripped:
            if result and not in_fence:
                break       # blank line after content = end of block
            continue        # skip leading / intra-fence blank lines

        # Opening fence marker: ```svg, ````svg, \```svg, \````svg, etc.
        if not in_fence and re.match(r'^\\?`{3,}', stripped):
            in_fence = True
            continue        # skip the fence marker itself

        # Closing fence marker: ```, ````, \```, \```` etc. (only backticks + optional whitespace)
        if in_fence and re.match(r'^\\?`{3,}\s*$', stripped):
            in_fence = False
            continue        # skip closing marker; content is done

        # Stop at a new Danta component keyword (only outside a fence)
        if not in_fence and re.match(r'^[A-Z][a-zA-Z]+:', stripped):
            break

        result.append(ln)

    if not result:
        return ''
    min_indent = min(len(l) - len(l.lstrip()) for l in result if l.strip())
    return '\n'.join(l[min_indent:] for l in result).strip()


def _sub_items(lines: list, start: int) -> list:
    result = []
    for ln in lines[start + 1:]:
        stripped = ln.strip()
        if not stripped:
            continue
        if stripped.startswith('- ') or stripped.startswith('* '):
            result.append(stripped[2:].strip())
        elif re.match(r'^[A-Za-z]', stripped):
            break
    return result


def _parse_field_hint(text: str) -> FieldHint:
    m = re.match(rf'^({_NAME})\s*(?::\s*(.*))?$', text)
    if not m:
        return FieldHint(name=text)
    name, rest = m.group(1), (m.group(2) or '').strip()
    hint = FieldHint(name=name)

    # Cascading choice: choice from entity [where prop == dep_field.prop]
    choice_m = re.search(r'\bchoice\s+from\s+(\w+)(?:\s+where\s+(.+))?', rest)
    if choice_m:
        hint.choice_from = choice_m.group(1)
        if choice_m.group(2):
            hint.choice_filter = choice_m.group(2).strip()
            dep_m = re.search(r'==\s*(\w+)\.\w+', hint.choice_filter)
            if dep_m:
                hint.depends_on = dep_m.group(1)
        hint.widget = 'select'
        return hint

    parts = [p.strip() for p in rest.split(',') if p.strip()]
    for p in parts:
        tokens = p.split()
        for tok in tokens:
            if tok == 'hidden':
                hint.hidden = True
            elif tok == 'large':
                hint.large = True
            elif tok.startswith('label ') or (tok == 'label' and len(tokens) > 1):
                hint.label = _unquote(p[p.index('label ') + 6:])
                break
            elif tok.startswith('placeholder ') or (tok == 'placeholder' and len(tokens) > 1):
                hint.placeholder = _unquote(p[p.index('placeholder ') + 12:])
                break
            elif re.match(r'^[a-z]', tok) and tok not in ('hidden', 'large'):
                if not hint.widget:
                    hint.widget = tok
    return hint


def _parse_theme(lines: list, errors: list) -> Theme:
    theme = Theme()
    for ln in lines:
        stripped = ln.strip()
        if not stripped:
            continue
        m = re.match(r'^(\w[\w\s]*):\s*(.*)', stripped)
        if not m:
            continue
        key, val = m.group(1).strip().lower(), m.group(2).strip()
        if key == 'brand':
            theme.brand = _unquote(val)
        elif key == 'font':
            theme.font = _unquote(val.split(',')[0])
        elif key == 'radius':
            if val not in RADIUS_VALUES:
                errors.append(f'Theme Radius: unknown value "{val}"; use one of {", ".join(sorted(RADIUS_VALUES))}')
            else:
                theme.radius = val
        elif key == 'mode':
            if val not in MODE_VALUES:
                errors.append(f'Theme Mode: unknown value "{val}"; use one of {", ".join(sorted(MODE_VALUES))}')
            else:
                theme.mode = val
        elif key == 'animations':
            requested = [a.strip().lower() for a in val.split(',') if a.strip()]
            unknown = [a for a in requested if a not in ANIMATION_VALUES]
            if unknown:
                errors.append(f'Theme Animations: unknown value(s) {", ".join(unknown)!r}; use: {", ".join(sorted(ANIMATION_VALUES))}')
            theme.animations = [a for a in requested if a in ANIMATION_VALUES]
        elif key == 'style':
            if val in STYLE_VALUES:
                theme.style = val
            else:
                errors.append(f'Theme Style: unknown value "{val}"; use one of {", ".join(sorted(STYLE_VALUES))}')
        elif key == 'background':
            bg_parts = val.split()
            bg_type = bg_parts[0].lower() if bg_parts else ''
            if bg_type in BACKGROUND_VALUES:
                theme.background = bg_type
                if bg_type == 'video':
                    src_m = re.search(r'\bsrc\s+"([^"]*)"', val)
                    if src_m:
                        theme.background_src = src_m.group(1)
            elif bg_type:
                errors.append(f'Theme Background: unknown value "{bg_type}"; use one of {", ".join(sorted(BACKGROUND_VALUES))}')
        elif key == 'interactions':
            requested = [i.strip().lower() for i in val.split(',') if i.strip()]
            unknown = [i for i in requested if i not in INTERACTION_VALUES]
            if unknown:
                errors.append(f'Theme Interactions: unknown value(s) {", ".join(unknown)!r}; use: {", ".join(sorted(INTERACTION_VALUES))}')
            theme.interactions = [i for i in requested if i in INTERACTION_VALUES]
        elif key == 'colors':
            for part in val.split(','):
                part = part.strip()
                cm = re.match(r'(\w+)\s+"?(#[0-9a-fA-F]{3,8})"?', part)
                if cm:
                    theme.colors[cm.group(1)] = cm.group(2)
    return theme


def _parse_screen(name: str, lines: list, errors: list, line_no: int) -> DesignScreen:
    screen = DesignScreen(name=name, line=line_no)

    # Layout
    _, layout_val = _prop(lines, 'Layout')
    if layout_val:
        known = [k for k in LAYOUTS if k in layout_val.lower()]
        screen.layout = ' '.join(known) or layout_val

    # Hero
    hero_idx, hero_val = _prop(lines, 'Hero')
    if hero_val is not None:
        hero = HeroComponent()
        for hm in re.finditer(r'(heading|sub|cta)\s+"((?:[^"\\]|\\.)*)"', hero_val):
            setattr(hero, hm.group(1), hm.group(2))
        screen.components.append(hero)

    # Text: "content" size h2 align center
    text_idx, text_val = _prop(lines, 'Text')
    if text_val is not None:
        txt = TextComponent()
        qm = re.match(r'^"([^"]*)"(?:\s+(.*))?', text_val)
        rest = ''
        if qm:
            txt.text = qm.group(1)
            rest = (qm.group(2) or '').strip()
        else:
            txt.text = _unquote(text_val)
        size_m = re.search(r'\bsize\s+(\w+)', rest)
        align_m = re.search(r'\balign\s+(\w+)', rest)
        # Also accept bare size/align keywords without the keyword prefix
        for tok in rest.split():
            if tok in ('h1', 'h2', 'h3', 'h4', 'large', 'lead', 'small') and not size_m:
                txt.size = tok
            elif tok in ('left', 'center', 'right') and not align_m:
                txt.align = tok
        if size_m:
            txt.size = size_m.group(1)
        if align_m:
            txt.align = align_m.group(1)
        screen.components.append(txt)

    # Columns: N  with sub-items: - icon "emoji" title "..." body "..."
    col_idx, col_val = _prop(lines, 'Columns')
    if col_val is not None:
        col_comp = ColumnsComponent()
        count_m = re.match(r'^(\d+)', (col_val or '').strip())
        if count_m:
            col_comp.count = max(1, min(4, int(count_m.group(1))))
        for item_text in _sub_items(lines, col_idx):
            item = ColumnItem()
            icon_m = re.search(r'\bicon\s+"([^"]*)"', item_text)
            title_m = re.search(r'\btitle\s+"([^"]*)"', item_text)
            body_m = re.search(r'\bbody\s+"([^"]*)"', item_text)
            if icon_m:
                item.icon = icon_m.group(1)
            if title_m:
                item.title = title_m.group(1)
            if body_m:
                item.body = body_m.group(1)
            if item.icon or item.title or item.body:
                col_comp.items.append(item)
        screen.components.append(col_comp)

    # Header
    hdr_idx, hdr_val = _prop(lines, 'Header')
    if hdr_val is not None:
        hdr = HeaderComponent()
        title_m = re.match(r'^"([^"]*)"', hdr_val)
        if title_m:
            hdr.title = title_m.group(1)
            rest = hdr_val[title_m.end():].strip()
        else:
            hdr.title = hdr_val.split(' action ')[0].strip().strip('"')
            rest = hdr_val
        for am in re.finditer(r'action\s+"([^"]*)"', rest):
            hdr.actions.append(am.group(1))
        screen.components.append(hdr)

    # Stats
    _, stats_val = _prop(lines, 'Stats')
    if stats_val is not None:
        stats = StatsComponent()
        inner = stats_val.strip().lstrip('[').rstrip(']')
        for part in inner.split(','):
            part = part.strip()
            if not part:
                continue
            sm = re.match(rf'^({_NAME})(?:\s+"([^"]*)")?(?:\s+(\w+))?', part)
            if sm:
                hint = FieldHint(name=sm.group(1), label=sm.group(2) or '', widget=sm.group(3) or '')
                stats.items.append(hint)
        screen.components.append(stats)

    # Form
    form_idx, form_val = _prop(lines, 'Form')
    if form_val is not None:
        form = FormComponent(flow=form_val.strip())
        for item in _sub_items(lines, form_idx):
            form.fields.append(_parse_field_hint(item))
        _, submit_val = _prop(lines, 'Submit')
        if submit_val:
            sm = re.match(r'^"([^"]*)"', submit_val)
            form.submit = sm.group(1) if sm else submit_val
        screen.components.append(form)

    # List
    list_idx, list_val = _prop(lines, 'List')
    if list_val is not None:
        lm = re.match(rf'^({_NAME})(?:\s+as\s+(\w+))?', list_val)
        lst = ListComponent(
            entity=lm.group(1) if lm else list_val,
            style=lm.group(2) if (lm and lm.group(2)) else 'table',
        )
        cols_m = re.search(r'\bcols\s+(\d+)', list_val)
        if cols_m:
            lst.cols = max(1, min(6, int(cols_m.group(1))))
        for item in _sub_items(lines, list_idx):
            lst.fields.append(_parse_field_hint(item))
        screen.components.append(lst)

    # Testimonials
    test_idx, test_val = _prop(lines, 'Testimonials')
    if test_val is not None:
        test_comp = TestimonialsComponent()
        for item_text in _sub_items(lines, test_idx):
            item = TestimonialItem()
            quote_m = re.match(r'^"([^"]*)"', item_text)
            if quote_m:
                item.text = quote_m.group(1)
            author_m = re.search(r'\bauthor\s+"([^"]*)"', item_text)
            if author_m:
                item.author = author_m.group(1)
            rating_m = re.search(r'\brating\s+(\d+)', item_text)
            if rating_m:
                item.rating = max(0, min(5, int(rating_m.group(1))))
            if item.text:
                test_comp.items.append(item)
        screen.components.append(test_comp)

    # Pricing
    price_idx, price_val = _prop(lines, 'Pricing')
    if price_val is not None:
        price_comp = PricingComponent()
        curr_m = re.search(r'\bcurrency\s+"([^"]*)"', price_val or '')
        if curr_m:
            price_comp.currency = curr_m.group(1)
        for item_text in _sub_items(lines, price_idx):
            tier = PricingTier()
            name_m = re.search(r'\bname\s+"([^"]*)"', item_text)
            price_m = re.search(r'\bprice\s+(\d+)', item_text)
            period_m = re.search(r'\bperiod\s+"([^"]*)"', item_text)
            cta_m = re.search(r'\bcta\s+"([^"]*)"', item_text)
            feat_m = re.search(r'\bfeatures\s+"([^"]*)"', item_text)
            if name_m:
                tier.name = name_m.group(1)
            if price_m:
                tier.price = int(price_m.group(1))
            if period_m:
                tier.period = period_m.group(1)
            if cta_m:
                tier.cta = cta_m.group(1)
            if feat_m:
                tier.features = [f.strip() for f in feat_m.group(1).split(',') if f.strip()]
            if 'highlight' in item_text:
                tier.highlight = True
            if tier.name:
                price_comp.tiers.append(tier)
        screen.components.append(price_comp)

    # Steps
    steps_idx, steps_val = _prop(lines, 'Steps')
    if steps_val is not None:
        steps_comp = StepsComponent()
        for item_text in _sub_items(lines, steps_idx):
            steps_comp.items.append(_unquote(item_text))
        screen.components.append(steps_comp)

    # SVG
    svg_idx, svg_val = _prop(lines, 'SVG')
    if svg_idx >= 0:
        comp = SVGComponent()
        # A value that looks like a fence marker (```svg) means the inline block
        # starts on the same line — treat it the same as an empty value.
        if svg_val and re.match(r'^\\?`{3,}', svg_val):
            svg_val = ''
        if svg_val:
            src_m = re.search(r'\bsrc\s+"([^"]*)"', svg_val)
            alt_m = re.search(r'\balt\s+"([^"]*)"', svg_val)
            w_m = re.search(r'\bwidth\s+(\d+)', svg_val)
            h_m = re.search(r'\bheight\s+(\d+)', svg_val)
            asp_m = re.search(r'\baspect\s+([\d/]+)', svg_val)
            if src_m: comp.src = src_m.group(1)
            if alt_m: comp.alt = alt_m.group(1)
            if w_m:   comp.width = int(w_m.group(1))
            if h_m:   comp.height = int(h_m.group(1))
            if asp_m: comp.aspect = asp_m.group(1)
        else:
            comp.inline = _raw_block(lines, svg_idx)
        screen.components.append(comp)

    # Image
    _, img_val = _prop(lines, 'Image')
    if img_val is not None:
        img = ImageComponent()
        alt_m = re.search(r'\balt\s+"([^"]*)"', img_val)
        aspect_m = re.search(r'\baspect\s+"([^"]*)"', img_val) or re.search(r'\baspect\s+([\d/]+)', img_val)
        src_m = re.search(r'\bsrc\s+"([^"]*)"', img_val)
        if alt_m:
            img.alt = alt_m.group(1)
        if aspect_m:
            img.aspect = aspect_m.group(1)
        if src_m:
            img.src = src_m.group(1)
        screen.components.append(img)

    # CTA
    _, cta_val = _prop(lines, 'CTA')
    if cta_val is not None:
        cta = CTAComponent()
        for attr in ('heading', 'sub', 'button'):
            m = re.search(rf'\b{attr}\s+"([^"]*)"', cta_val)
            if m:
                setattr(cta, attr, m.group(1))
        bg_m = re.search(r'\bbg\s+(\w+)', cta_val)
        if bg_m:
            cta.bg = bg_m.group(1)
        screen.components.append(cta)

    # Divider
    div_idx, div_val = _prop(lines, 'Divider')
    if div_idx >= 0:
        div = DividerComponent()
        if div_val:
            dm = re.match(r'^"([^"]*)"', div_val.strip())
            div.label = dm.group(1) if dm else _unquote(div_val)
        screen.components.append(div)

    # Empty
    _, empty_val = _prop(lines, 'Empty')
    if empty_val is not None:
        em = EmptyComponent()
        em_m = re.match(r'^"([^"]*)"(?:\s+cta\s+"([^"]*)")?', empty_val)
        if em_m:
            em.text, em.cta = em_m.group(1), (em_m.group(2) or '')
        else:
            em.text = _unquote(empty_val)
        screen.components.append(em)

    # Trust
    _, trust_val = _prop(lines, 'Trust')
    if trust_val is not None:
        screen.components.append(TrustComponent(text=_unquote(trust_val)))

    # Wizard (multi-step form)
    wiz_idx, wiz_val = _prop(lines, 'Wizard')
    if wiz_idx >= 0:
        wiz = WizardComponent(flow=(wiz_val or '').strip())
        _, sub_val = _prop(lines, 'Submit')
        if sub_val:
            sm = re.match(r'^"([^"]*)"', sub_val)
            wiz.submit = sm.group(1) if sm else sub_val
        for item_text in _sub_items(lines, wiz_idx):
            step = WizardStep()
            step_m = re.match(r'^(?:step\s+)?"([^"]*)"(?:\s+(?:fields?\s+)?(.+))?', item_text)
            if step_m:
                step.label = step_m.group(1)
                if step_m.group(2):
                    step.fields = [f.strip() for f in re.split(r'[,\s]+', step_m.group(2).strip()) if f.strip()]
            if step.label:
                wiz.steps.append(step)
        screen.components.append(wiz)

    # Model3D
    m3d_idx, m3d_val = _prop(lines, 'Model3D')
    if m3d_idx >= 0:
        m3d = Model3DComponent()
        if m3d_val:
            src_m = re.search(r'\bsrc\s+"([^"]*)"', m3d_val)
            alt_m = re.search(r'\balt\s+"([^"]*)"', m3d_val)
            poster_m = re.search(r'\bposter\s+"([^"]*)"', m3d_val)
            if src_m:
                m3d.src = src_m.group(1)
            if alt_m:
                m3d.alt = alt_m.group(1)
            if poster_m:
                m3d.poster = poster_m.group(1)
            m3d.auto_rotate = 'no-rotate' not in m3d_val
            m3d.float_anim = 'float' in m3d_val
        screen.components.append(m3d)

    # Preview entity for split-preview layout
    _, preview_val = _prop(lines, 'Preview')
    if preview_val:
        screen.preview_entity = preview_val.strip()

    return screen


def parse_design(text: str) -> DesignSpec:
    """Parse design spec text into a DesignSpec. Always returns an object;
    errors are collected in DesignSpec.errors rather than raising."""
    spec = DesignSpec()
    errors = spec.errors

    if not _VERSION.search(text):
        errors.append('First line must be exactly: Design: danta/0.1')
        return spec

    m = _SYSTEM.search(text)
    if not m:
        errors.append('Missing "System: <name>" — must match the backend spec\'s system name')
        return spec
    spec.system = m.group(1)

    positions = [(m.start(), m.group(0)) for m in _SECTION.finditer(text)]

    def section_lines(start_pos: int, end_pos: int) -> list:
        return text[start_pos:end_pos].splitlines()[1:]

    for idx, (pos, heading) in enumerate(positions):
        end = positions[idx + 1][0] if idx + 1 < len(positions) else len(text)
        lines = section_lines(pos, end)

        if _THEME.match(heading):
            spec.theme = _parse_theme(lines, errors)
            continue

        screen_m = _SCREEN.match(heading)
        if screen_m:
            name = screen_m.group(1)
            if any(s.name == name for s in spec.screens):
                errors.append(f'Screen "{name}" is declared twice')
                continue
            spec.screens.append(_parse_screen(name, lines, errors, text[:pos].count('\n') + 1))

    return spec
