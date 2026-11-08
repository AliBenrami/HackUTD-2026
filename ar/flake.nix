{
  description = "PoC AR overlay for VITURE Luma Ultra XR glasses (Python + Panda3D)";

  inputs = {
    # Pinned to the nixpkgs rev verified by the reference checkout
    # (avoids a branch-HEAD lookup at lock time).
    nixpkgs.url = "github:NixOS/nixpkgs/1d060086d60cb76a40cf37109f979d88a5bd6396";
  };

  outputs = { self, nixpkgs }:
    let
      systems = [ "x86_64-linux" "aarch64-linux" ];

      forEachSystem = f:
        nixpkgs.lib.genAttrs systems (system: f (import nixpkgs { inherit system; }));
    in
    {
      devShells = forEachSystem (pkgs:
        let
          # Runtime closure needed by the proprietary SDK blobs
          # (libglasses -> libudev, libcarina_vio -> libusb, bundled OpenCV)
          # plus whatever Panda3D's manylinux wheel loads from the system
          # (libGL, X11, Wayland client libs, C++ stdlib).
          runtimeLibs = with pkgs; [
            systemd # libudev.so.1
            libusb1
            openssl # libcrypto (SDK adjacency; harmless if unused)
            zlib # Pillow JPEG/PNG decode
            libGL
            wayland
            stdenv.cc.cc
            libx11
            libxext
            libxrandr
            libxinerama
            libxcursor
            libxi
            libxcb
            libxkbcommon
            glib
          ];
        in
        {
          default = pkgs.mkShell {
            packages = with pkgs; [
              python312
              uv
            ];

            shellHook = ''
              # Deterministic interpreter: uv uses the Nix-provided
              # Python 3.12 (matches .python-version), never downloads.
              export UV_PYTHON="''${UV_PYTHON:-python3.12}"

              # Default SDK location: the reference checkout's unpacked
              # vendor blobs (proprietary, not vendored here). Override with:
              #   export VITURE_SDK_LIB=/path/to/sdk/<arch>/dir
              if [ -z "''${VITURE_SDK_LIB:-}" ]; then
                if [ -d "$PWD/sdk/viture_x86_64/x86_64" ]; then
                  export VITURE_SDK_LIB="$PWD/sdk/viture_x86_64/x86_64"
                elif [ -d "$PWD/sdk/viture_arm64/aarch64" ]; then
                  export VITURE_SDK_LIB="$PWD/sdk/viture_arm64/aarch64"
                elif [ -d /home/jude/Repos/Viture_AR_Playground/sdk/viture_x86_64/x86_64 ]; then
                  export VITURE_SDK_LIB=/home/jude/Repos/Viture_AR_Playground/sdk/viture_x86_64/x86_64
                fi
              fi

              export LD_LIBRARY_PATH="''${VITURE_SDK_LIB:+$VITURE_SDK_LIB:}${pkgs.lib.makeLibraryPath runtimeLibs}''${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"

              if [ -z "''${VITURE_SDK_LIB:-}" ] || [ ! -f "''${VITURE_SDK_LIB}/libglasses.so" ]; then
                echo "NOTE: libglasses.so not found. Set VITURE_SDK_LIB to the unpacked" >&2
                echo "VITURE SDK arch dir (see README.md), then 'uv sync'." >&2
              else
                echo "VITURE SDK: $VITURE_SDK_LIB"
              fi
              echo "Run:  uv sync && uv run python src/ar_poc.py --help"
            '';
          };
        });
    };
}
