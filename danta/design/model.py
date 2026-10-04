"""model.py — Data classes for the Design Spec IR."""

from dataclasses import dataclass, field
from typing import Any, List, Optional


# ---------- theme -------------------------------------------------------

RADIUS_VALUES   = {'none', 'small', 'medium', 'large', 'rounded'}
MODE_VALUES     = {'light', 'dark', 'auto'}
LAYOUTS         = {
    'centered', 'card', 'full', 'sidebar', 'two-col',
    'hero', 'minimal', 'dashboard', 'split', 'split-preview',
}
ANIMATION_VALUES    = {'scroll-reveal', 'stagger', 'counter', 'parallax', 'typewriter'}
STYLE_VALUES        = {'default', 'cyberpunk', 'glass', 'minimal', 'bold'}
BACKGROUND_VALUES   = {'particles', 'mesh-gradient', 'dot-grid', 'circuit', 'video'}
INTERACTION_VALUES  = {'card-tilt', 'button-glow', 'magnetic-links', 'ripple', 'parallax-cards'}


@dataclass
class Theme:
    brand: str = ''
    colors: dict = field(default_factory=dict)
    font: str = ''
    radius: str = 'medium'
    mode: str = 'auto'
    animations: list = field(default_factory=list)   # subset of ANIMATION_VALUES
    style: str = 'default'                            # subset of STYLE_VALUES
    background: str = ''                              # one of BACKGROUND_VALUES
    background_src: str = ''                          # for video background
    interactions: list = field(default_factory=list)  # subset of INTERACTION_VALUES


# ---------- field / column display hints --------------------------------

@dataclass
class FieldHint:
    name: str
    widget: str = ''
    label: str = ''
    placeholder: str = ''
    large: bool = False
    hidden: bool = False
    choice_from: str = ''    # entity name for dynamic <select>
    choice_filter: str = ''  # filter expression e.g. "socket == cpu_sku.socket_type"
    depends_on: str = ''     # field name this select depends on for cascading


# ---------- components --------------------------------------------------

@dataclass
class HeroComponent:
    kind: str = 'hero'
    heading: str = ''
    sub: str = ''
    cta: str = ''


@dataclass
class TextComponent:
    kind: str = 'text'
    text: str = ''
    size: str = 'body'    # h1 | h2 | h3 | h4 | body | large | lead | small
    align: str = ''       # left | center | right


@dataclass
class ColumnItem:
    icon: str = ''
    title: str = ''
    body: str = ''


@dataclass
class ColumnsComponent:
    kind: str = 'columns'
    count: int = 3
    items: List[ColumnItem] = field(default_factory=list)


@dataclass
class CTAComponent:
    kind: str = 'cta'
    heading: str = ''
    sub: str = ''
    button: str = ''
    bg: str = 'primary'   # primary | accent | dark | surface


@dataclass
class DividerComponent:
    kind: str = 'divider'
    label: str = ''


@dataclass
class TestimonialItem:
    text: str = ''
    author: str = ''
    rating: int = 5


@dataclass
class TestimonialsComponent:
    kind: str = 'testimonials'
    items: List[TestimonialItem] = field(default_factory=list)


@dataclass
class PricingTier:
    name: str = ''
    price: int = 0
    period: str = '/mo'
    features: List[str] = field(default_factory=list)
    highlight: bool = False
    cta: str = ''


@dataclass
class PricingComponent:
    kind: str = 'pricing'
    tiers: List[PricingTier] = field(default_factory=list)
    currency: str = '$'


@dataclass
class StepsComponent:
    kind: str = 'steps'
    items: List[str] = field(default_factory=list)


@dataclass
class ImageComponent:
    kind: str = 'image'
    alt: str = ''
    aspect: str = '16/9'   # 16/9 | 4/3 | 1/1 | 3/2 | 21/9
    src: str = ''


@dataclass
class SVGComponent:
    kind: str = 'svg'
    src: str = ''      # URL / path / data URI (renders as <img>)
    alt: str = ''      # alt text or label
    width: int = 0     # px; 0 = auto
    height: int = 0    # px; 0 = auto
    aspect: str = ''   # e.g. 16/9 — makes it full-width with aspect ratio box
    inline: str = ''   # raw SVG markup pasted inline


@dataclass
class FormComponent:
    kind: str = 'form'
    flow: str = ''
    fields: List[FieldHint] = field(default_factory=list)
    submit: str = ''


@dataclass
class ListComponent:
    kind: str = 'list'
    entity: str = ''
    style: str = 'table'      # cards | table | rows
    fields: List[FieldHint] = field(default_factory=list)
    cols: int = 0             # 0 = auto, otherwise forces column count


@dataclass
class StatsComponent:
    kind: str = 'stats'
    items: List[FieldHint] = field(default_factory=list)


@dataclass
class HeaderComponent:
    kind: str = 'header'
    title: str = ''
    actions: List[str] = field(default_factory=list)


@dataclass
class TrustComponent:
    kind: str = 'trust'
    text: str = ''


@dataclass
class EmptyComponent:
    kind: str = 'empty'
    text: str = ''
    cta: str = ''


# ---------- new ecommerce components ------------------------------------

@dataclass
class WizardStep:
    label: str = ''
    fields: List[str] = field(default_factory=list)


@dataclass
class WizardComponent:
    kind: str = 'wizard'
    flow: str = ''
    steps: List[WizardStep] = field(default_factory=list)
    submit: str = 'Submit'


@dataclass
class Model3DComponent:
    kind: str = 'model3d'
    src: str = ''          # path/URL to .glb/.gltf file
    alt: str = ''
    auto_rotate: bool = True
    float_anim: bool = False
    poster: str = ''       # preview image shown before model loads


Component = Any


# ---------- screen / spec -----------------------------------------------

@dataclass
class DesignScreen:
    name: str
    layout: str = ''
    components: List[Component] = field(default_factory=list)
    preview_entity: str = ''   # for split-preview layouts
    line: int = 0


@dataclass
class DesignSpec:
    system: str = ''
    theme: Theme = field(default_factory=Theme)
    screens: List[DesignScreen] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    @property
    def ok(self):
        return not self.errors
