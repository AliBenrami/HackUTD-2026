"""Optical FOV edge fading: smooth screen-space falloff to black.

A fullscreen-following card carrying a tiny GLSL shader multiplies the
scene toward black near the viewport edges (smoothstep on rectangular
edge distance). Black is optically transparent on the additive
combiner, so softening the cutoff reduces the "screen door" feeling
without changing any geometry, poses, or projection.

Design notes (all learned the hard way in this repo):
* The card lives in the WORLD (child of a follow-node under render),
  not under a camera and not in render2d: world geometry is the only
  placement that renders reliably in every configuration here.
* The follow node copies the head rig transform each frame, so the
  card always fills the view; the gradient itself is computed from
  clip-space NDC, i.e. it is viewport-relative by construction.
* In stereo both eyes see the same card through their own regions;
  each region evaluates its own NDC, so each eye gets an independent
  fade and the effect is never applied twice.
* The debug HUD lives in aspect2d (a separate display region drawn
  after the 3D scene), so it stays unfaded in mono.
"""

from __future__ import annotations

VERTEX = """
#version 130
uniform mat4 p3d_ModelViewProjectionMatrix;
in vec4 p3d_Vertex;
out vec4 v_clip;
void main() {
    v_clip = p3d_ModelViewProjectionMatrix * p3d_Vertex;
    gl_Position = v_clip;
}
"""

FRAGMENT = """
#version 130
uniform float u_width;    // fade band width, fraction of half-view (0..0.5)
uniform float u_strength; // 0 = off, 1 = full fade to black at the edge
in vec4 v_clip;
out vec4 fragColor;
void main() {
    vec2 ndc = v_clip.xy / v_clip.w;
    vec2 uv = ndc * 0.5 + 0.5;
    vec2 d = min(uv, 1.0 - uv);
    float edge = min(d.x, d.y);
    float t = smoothstep(0.0, u_width, edge);
    float a = (1.0 - t) * u_strength;
    fragColor = vec4(0.0, 0.0, 0.0, a);
}
"""

# Card 8 m ahead, 200 m across: overscans any reasonable frustum, so it
# always covers the viewport and the NDC math stays valid.
CARD_DISTANCE = 8.0
CARD_HALF_SIZE = 100.0


class EdgeFadeEffect:
    """Camera-following quad + NDC smoothstep fade (see module docstring).

    The shader declares Panda's standard inputs explicitly and targets GLSL
    1.30, avoiding the legacy implicit-builtin compile path on Mesa.
    """
    def __init__(self, render, width: float = 0.10,
                 strength: float = 1.0) -> None:
        from panda3d.core import (CardMaker, Shader, TransparencyAttrib)

        self._rig = render.attach_new_node("edge-fade-rig")
        maker = CardMaker("edge-fade-card")
        maker.set_frame(-1.0, 1.0, -1.0, 1.0)
        self.card = self._rig.attach_new_node(maker.generate())
        self.card.set_p(90.0)
        self.card.set_pos(0.0, CARD_DISTANCE, 0.0)
        self.card.set_scale(CARD_HALF_SIZE, CARD_HALF_SIZE, 1.0)
        self.card.set_two_sided(True)
        self.card.set_bin("background", 0)
        self.card.set_depth_write(False)
        self.card.set_depth_test(False)
        self.card.set_transparency(TransparencyAttrib.M_alpha)
        self.card.set_shader(Shader.make(
            Shader.SL_GLSL, vertex=VERTEX, fragment=FRAGMENT))
        self._width = 0.0
        self._strength = 0.0
        self.set_width(width)
        self.set_strength(strength)
        self._enabled = True

    # -- runtime controls -------------------------------------------------
    @property
    def enabled(self) -> bool:
        return self._enabled

    def set_enabled(self, on: bool) -> None:
        self._enabled = bool(on)
        if on:
            self.card.show()
        else:
            self.card.hide()

    def toggle(self) -> bool:
        self.set_enabled(not self._enabled)
        return self._enabled

    def set_width(self, width: float) -> float:
        self._width = max(0.0, min(0.5, float(width)))
        self.card.set_shader_input("u_width", self._width)
        return self._width

    def set_strength(self, strength: float) -> float:
        self._strength = max(0.0, min(1.0, float(strength)))
        self.card.set_shader_input("u_strength", self._strength)
        return self._strength

    @property
    def width(self) -> float:
        return self._width

    @property
    def strength(self) -> float:
        return self._strength

    # -- per-frame ----------------------------------------------------------
    def follow(self, cam_node, scene_root) -> None:
        """Snap the rig to a camera's world transform (call every frame)."""
        self._rig.set_pos(scene_root, cam_node.get_pos(scene_root))
        self._rig.set_quat(scene_root, cam_node.get_quat(scene_root))
