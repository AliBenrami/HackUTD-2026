# GolfAR for Quest

A Unity port of the tabletop course prototype. Physical club play defaults to passthrough on supported headsets, and the menu can switch to the virtual workshop. It uses Unity 6.6 (6000.6.8f1), OpenXR 1.19.0, and Meta XR Core SDK 207.0.1. Meta's camera rig provides head tracking, Touch controller poses, and hand input. Meta also handles passthrough compositing and spatial anchor persistence.

## Open and build

1. Add this directory as a project in Unity Hub. Install the pinned editor with **Android Build Support**, **Android SDK & NDK Tools**, and **OpenJDK**.
2. Open `Assets/GolfAR/GolfTable.unity` and press Play for a desktop preview. Right drag looks around, Tab opens the menu, and R returns you to the ball. Hold the left mouse button on the ball, aim, and release to putt in the preview. WASD moves the preview camera in the tabletop editor.
3. Switch to Android in **File > Build Profiles** and choose **GolfAR > Build Quest APK**. The project includes its OpenXR loader, Quest 2 target, Vulkan, ARM64 and IL2CPP settings.
4. Connect a Quest in developer mode, accept its USB debugging prompt, and run from this directory:

   ```sh
   adb install -r Builds/GolfAR-Quest.apk
   adb shell am start -n com.golfar.quest/com.unity3d.player.UnityPlayerActivity
   ```

The build method also runs in batch mode with `-projectPath <absolute-ar-unity-path> -buildTarget Android -executeMethod GolfAR.Editor.QuestProject.BuildQuest -batchmode -quit`.

For a local soundtrack, place your MP3 at `Assets/Resources/GolfBackground.mp3`. The game loops it at 12% volume. The MP3 is excluded from Git.

## Headset controls

- **Play** starts beside the ball on a level opening stretch that blends into the generated terrain. The default green measures about 7.6 × 4.8 m and uses a 43 mm ball. In VR, the game moves you beside the ball after each putt and keeps horizontal movement within 10 cm of that stance. Your view follows your head. **A** places you beside a stationary ball.
- **Putt** with the right Touch controller. Hold the grip button, lower the virtual head beside the ball, and point the cyan face in the direction you want to putt. Take a short backswing and bring the face through the ball. Face angle steers the shot. A faster, centered strike sends the ball farther, and a toe or heel strike loses power.
- Each putt counts one stroke. A slow putt into the target completes the hole. If the ball rolls off the course, it returns to where you last putted from and the stroke still counts. **Reset hole** returns the ball to the tee and clears the count. Space does the same in the desktop Play tab.
- **B → Drop ball** lets you choose a clear spot within 1.5 m of the current lie. Point at the spot and trigger when the marker appears. The drop adds one stroke and sets up the next putt. Press **B** to cancel.
- **B** opens or closes the menu in first-person play. Aim and trigger to select. The menu shows a hover dot, and opening it pauses the putter. The editing tabs open the tabletop view, where you can select or grab with a Touch controller or tracked-hand pinch.
- **Course** selects difficulty, generates or enters a seed, restores the previous course, saves or loads a layout, and adjusts ball diameter. **Fixed demo** uses the reference Medium layout at seed 4242 with six decor placements.
- **Stage** switches between grabbing the stage and individual props. It also has undo, reset, 1 cm nudges, 5° yaw steps, and course scale from 0.10 to 1.00. The default scale is 0.25. The ball stays at its selected physical diameter when you resize the course.
- **Display** shows the calibration outline, prop gallery, route diagnostic, neon trim and graphics presets. Performance uses a 65×65 terrain, 2× MSAA and a 4× anisotropy limit. Balanced starts at 97×97 with 4× MSAA and an 8× limit. Quality uses 129×129 with the same antialiasing and filtering as Balanced. The Quest logs the XR render target’s sample count and frame timings as `[golf-graphics]`.
- **Obstacles** adds a box footprint at the point you select on the table plane. You can edit its type, position, footprint and height, or switch between outlines and solid proxies. Obstacle placement and sizing use table-local metres and survive course regeneration.

## Connect the club gyro

1. Build and flash the current screen firmware from the repository root with `pio run -d embedded -e cyd -t upload`. This adds the BLE notification descriptor the Quest subscribes to. Confirm the screen shows live readings when the gyro moves.
2. The physical club is the default. On first use, press **B → Connect club** and allow **Nearby devices**. With permission granted, the game searches automatically the next time it opens in club mode.
3. Close the menu with **B**, press **A** to place the ball, and hold the club head still at the bracket behind it. The bracket shows **READY** in lime when the club is set and **ARMED** in blue once the backswing is long enough. Swing back through the bracket and look for **HIT COUNTED**. Passthrough shows a gyro-driven putter head as a guide. VR shows the head and shaft. You can set down Touch while putting.
4. At the tee, the aim line starts along the fairway. From later lies it starts toward the cup. Hold the right Touch index trigger and point at your target, then release to lock the blue preview. Nudge the **right stick** left or right for 5° aim steps, or use **X** and **Y**. **A** repositions you at the current lie and keeps your chosen aim.
5. If the gyro reads the swing backward, click the **right stick** or select **B → Flip swing** after moving the club once. To teach the direction from scratch, hold the club at address, click the **left stick**, draw the club straight back, and return slowly. The app remembers the correction.

The Quest subscribes directly to the screen board’s `HackUTD` BLE service using the existing v1 frame format. It estimates gyro bias while the club is still and detects the backswing axis. The sensor uses a 65 cm lever-arm estimate to infer head speed. A stream gap requires a fresh address. The Quest retries up to three times after a link loss or a stalled live stream. Disconnect another telemetry client if it is already using the club.

### Track the physical club with Touch

Secure the right Touch controller to the shaft and keep its tracking ring exposed. Select **B → Track club** and close the menu. In passthrough, line up the actual putter head with the bracket behind the ball, square the face to the bracket, and press **X** on the left controller. Swing the club through the virtual ball once the marker shows **ARMED**. This mode uses the calibrated Touch position and rotation for contact. Press **X** again if the mount moves. The left controller’s **Y** opens the menu.

## Passthrough play and placement

In passthrough, the green becomes translucent over the room. Press **A** to bring the ball to the floor in front of you, or hold the **left grip** and point at a reachable floor spot. Release when the green dot is where you want the ball. After a putt, the course slides the next lie to the same floor spot and keeps its orientation. Press **B** to switch between **Enter VR** and **Passthrough**. The game remembers your choice.

For tabletop editing, choose **Stage > Place table** while passthrough is active. Hold the tracked controller or hand at the center and height of the physical tabletop and trigger or pinch. Use **Grab: stage** or **Fine tune** to adjust the overlay. **Save anchor** stores the table location locally on the headset. In a later session, enter passthrough and choose **Restore anchor** in the same room. The calibration outline is 60 × 40 cm.

Quest 2 provides grayscale passthrough. Marker tracking and automatic camera-based obstacle detection require camera frames that the Quest 2 passthrough API does not expose. Use manual placement and obstacle footprints on this device. [Meta passthrough tutorial](https://developers.meta.com/vr/documentation/unity/unity-passthrough-tutorial/) · [Meta camera API requirements](https://developers.meta.com/vr/documentation/unity/unity-pca-overview/)

## Layouts and parity

- Layout files live in Unity's `Application.persistentDataPath`. On Quest that is normally `/sdcard/Android/data/com.golfar.quest/files`. To bring over a 60 × 40 cm Python cyber-golf v5 layout, put it there as `course_layout.json` and choose **Load layout**. With the same seed, difficulty, and generation settings, new Quest and Python layouts use the same route and feature placements. Previously saved Unity v5 files still load with their original coordinates.
- The terrain renderer and static mesh collider share their triangles. The fairway ribbon, beveled island, plasma pools, target and obstacle trim are generated. Neon accents can be toggled without changing the course or its collider.
- The Unity port uses its own obstacle save format. Viture optics, marker calibration files, baseline scanning, and desktop bloom are specific to the original prototype.

### Import the reference city props

Download `LowPolyCyberpunkPack_v1.0.zip` and run the importer from the repository root. [Creator’s asset page](https://reodesuxz.itch.io/low-poly-cyberpunk-pack)

```sh
python3 ar-unity/Tools/import_cyberpunk_models.py ~/hackutd26_assets/LowPolyCyberpunkPack_v1.0.zip
```

Unity imports the 23 GLBs using glTFast. The importer maps filenames to the original manifest IDs. The course instantiates only the props it needs and sizes each to its placement. The gallery shows the full pack when installed. A clean checkout can build and generate courses with procedural fallback props. The raw GLBs are machine-local and ignored by Git. [Pack license](../ar/assets/CYBERPUNK_ASSET_LICENSE.md)

### Verify procedural parity

From the repository root, export reference layouts and run the Unity comparison:

```sh
python3 ar-unity/Tools/export_course_reference.py /tmp/golfar-course-reference.json
"$UNITY_EDITOR" -batchmode -nographics -quit -projectPath "$PWD/ar-unity" \
  -executeMethod GolfAR.Editor.CourseParity.Verify \
  -courseReference /tmp/golfar-course-reference.json -logFile -
```

Set `UNITY_EDITOR` to the Unity executable first. The comparison checks seeds 0–99 per difficulty, the fixed demo, and six settings groups in total beyond the sweep. It checks matching layout decisions, v5 loading, and sampled terrain geometry. Position and height tolerance is 0.000015 course-local metres. Slope and unit normal tolerance is 0.001. The Python export runs on the development machine. The Quest generates courses offline. See the [port checklist](TODO.md) for the remaining headset and art checks.
