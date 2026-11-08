"""World-locked video panel: live MJPEG frames on a quad in the room.

Instead of a camera-following background card (which Panda3D will not
render as a child of the camera node), the camera feed is shown the
same way every other AR element is: as geometry *in the world*,
parented under gl_space like the cube -- the virtual
screen of reference sample 03, fed by the glasses' own camera.

The panel is opaque and depth-writes, so 3D objects occlude it (and it
occludes them) correctly. JPEG decode is via Pillow; upload is one
`set_ram_image` per frame.
"""

from __future__ import annotations

import io

from PIL import Image

# Panel width in metres; height follows the camera aspect (16:9).
PANEL_WIDTH_METRES = 1.6
# Panel centre in GL world coordinates (x right, y up, z backward).
PANEL_POS = (0.0, 0.10, -2.00)


class VideoPanel:
    def __init__(self, gl_space) -> None:
        from panda3d.core import CardMaker, Texture

        self._Texture = Texture
        self.texture = Texture("video-panel")
        self._tex_w = 0
        self._tex_h = 0
        self.frames_shown = 0

        half_w = PANEL_WIDTH_METRES / 2.0
        # Fixed 16:9 frame: the camera is fixed-config 1920x1080.
        maker = CardMaker("video-panel-card")
        maker.set_frame(-half_w, half_w, -half_w * 9.0 / 16.0,
                        half_w * 9.0 / 16.0)
        self.card = gl_space.attach_new_node(maker.generate())
        # CardMaker cards lie in the XZ plane (ground-quad convention);
        # pitch -90 about X stands the panel up to face the wearer (+Z).
        self.card.set_p(90.0)
        self.card.set_two_sided(True)
        # A screen emits light: ignore scene lighting, show video as-is.
        self.card.set_light_off()
        self.card.set_pos(*PANEL_POS)
        self.card.set_texture(self.texture)
        self.card.hide()  # shown on the first real frame

    @property
    def has_image(self) -> bool:
        return self._tex_w > 0

    def show_frame(self, jpeg: bytes, width: int, height: int) -> bool:
        """Decode + upload one MJPEG frame. False when undecodable."""
        try:
            img = Image.open(io.BytesIO(jpeg)).convert("RGB")
        except Exception:
            return False
        if img.size != (width, height):
            width, height = img.size  # trust the decoder
        if not width or not height:
            return False
        if width != self._tex_w or height != self._tex_h:
            self.texture.setup_2d_texture(
                width, height,
                self._Texture.T_unsigned_byte, self._Texture.F_rgb)
            self._tex_w, self._tex_h = width, height
        # Empirically, F_rgb uploads render R/B-swapped on this stack
        # (red test stripes showed blue); pre-swap to BGR here.
        r, g, b = img.split()
        raw = Image.merge("RGB", (b, g, r)).tobytes()
        if len(raw) != width * height * 3:
            return False
        self.texture.set_ram_image(raw)
        self.card.show()
        self.frames_shown += 1
        return True
