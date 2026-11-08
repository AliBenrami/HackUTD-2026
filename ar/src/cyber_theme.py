"""Centralized optical-see-through cyberpunk palette and Panda materials.

Authored hex values are sRGB. The renderer requests an sRGB framebuffer, so
colours are converted to linear exactly once here; vertex colours, line
colours and materials then share one colour space without double gamma.
"""
from panda3d.core import Material

CYBERPUNK_PALETTE = {
    "base": "#31485A",
    "secondary": "#4C6B7D",
    "ridge": "#20323D",
    "sidewall": "#2A4050",
    "fairway": "#0F7E8A",
    "fairway_dark": "#0A5B64",
    "cyan": "#00E8F0",
    "magenta": "#FA3CAD",
    "lime": "#B0FF4A",
    "amber": "#FFC247",
    "white": "#F5FBFF",
}


def _srgb_to_linear(value):
    return value / 12.92 if value <= .04045 else ((value + .055) / 1.055) ** 2.4


def rgba(name, alpha=1.0):
    """Linear RGBA for the sRGB framebuffer and linear lighting maths."""
    value = CYBERPUNK_PALETTE[name].lstrip("#")
    return tuple(_srgb_to_linear(int(value[i:i+2], 16) / 255)
                 for i in (0, 2, 4)) + (alpha,)


def material(name, neon=False):
    """Reusable PBR-aware material for Panda's automatic shader generator."""
    color = rgba(name)
    mat = Material(f"cyber-{name}{'-neon' if neon else ''}")
    mat.set_base_color(color)
    mat.set_diffuse(color)
    mat.set_ambient(tuple(c * (.72 if neon else .30) for c in color[:3]) + (1,))
    if neon:
        mat.set_emission(tuple(c * .85 for c in color[:3]) + (1,))
    mat.set_specular((.34, .42, .48, 1) if not neon else color)
    mat.set_shininess(24 if not neon else 48)
    if neon:
        metallic, roughness = .06, .30
    elif name in ("fairway", "fairway_dark", "white"):
        metallic, roughness = .08, .38
    else:
        metallic, roughness = .28, .58
    mat.set_metallic(metallic)
    mat.set_roughness(roughness)
    return mat


MATERIALS = {name: material(name, name in ("cyan", "magenta", "lime", "amber"))
             for name in CYBERPUNK_PALETTE}

def apply(node, name, neon=False):
    node.set_material(MATERIALS[name], 1)
    # Emissive geometry carries its own flat colour because Panda's automatic
    # shader gives a light-off node's colour precedence over material colour.
    node.set_color(*(rgba(name) if neon else (1, 1, 1, 1)))
    if neon:
        node.set_light_off(1)
        node.set_python_tag("neon", True)
        node.set_python_tag("neon_color", rgba(name))
    return node


def apply_vertex_material(node, name):
    """Let per-vertex colours drive the automatic shader's diffuse response.

    Panda's shader generator gives a material base colour precedence over a
    vertex-colour column, so vertex-coloured terrain deliberately carries no
    MaterialAttrib. Lighting, normals and the sRGB framebuffer still apply.
    """
    node.clear_material()
    return node
