using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using Newtonsoft.Json;
using UnityEngine;
using UnityEngine.InputSystem;
using UnityEngine.XR;

namespace GolfAR
{
    public sealed class GolfTable : MonoBehaviour
    {
        [SerializeField] private OVRCameraRig rig;
        [SerializeField] private OVRPassthroughLayer passthrough;
        [SerializeField] private OVRHand leftHand, rightHand;
        [SerializeField] private Camera previewCamera;
        [SerializeField] private Shader terrainShader, flatShader;
        private Camera eye;
        private TableAnchor table;
        private Transform stage, room, stand, outline, cursor;
        private CourseView palette, course;
        private Putting putting, pendingArrival;
        private readonly ClubLink clubLink = new();
        private enum ClubMode { Touch, Gyro, Mounted }
        private ClubMode clubMode = ClubMode.Gyro;
        private bool useSensorClub => clubMode == ClubMode.Gyro;
        private const string ClubModePreference = "GolfAR.UsePhysicalClub";
        private const string PassthroughPreference = "GolfAR.UsePassthrough";
        private readonly List<XRDisplaySubsystem> displays = new();
        private Coroutine graphicsReport;
        private GreenPlay greenPlay;
        private Transform green;
        private TableMenu menu;
        private PhysicalObstacles physical;
        private LineRenderer laser;
        private CourseLayout layout, previous;
        private readonly Stack<(Transform Target, Vector3 Position, Quaternion Rotation)> undo = new();
        private Transform grabbed, aimSource;
        private float grabDistance, grabYaw;
        private Vector3 grabOffset;
        private Vector3? floorSpot;
        private Quaternion grabRotation;
        private bool held, wasMouse, expanded = true, menuOpen, mixedReality, neon = true, diagnostics, boundsVisible;
        private bool placeTable, addObstacle, grabStage, xr, droppingBall;
        private int seed = CourseLayout.FixedSeed, grid = CourseLayout.ReferenceGrid, galleryIndex, selectedObject;
        private float scale = CourseLayout.DefaultScale, ball = CourseLayout.DefaultBall;
        private float previousScale = CourseLayout.DefaultScale;
        private string difficulty = "medium", page = "Play", seedText = "", message = "";
        private const string PuttHelp = "Aim at ball · hold to charge · release to putt";
        private string PlayHelp => greenPlay.Active && xr && clubMode == ClubMode.Mounted ? "X calibrate club · A place ball · Y menu" :
            greenPlay.Active && xr && useSensorClub ? "Hold trigger to aim · A place ball · B menu" :
            greenPlay.Passthrough ? "A place ball · hold grip to putt · B menu" :
            greenPlay.Active && xr ? "Hold grip · square the putter face · swing · B menu" :
            greenPlay.Active ? "Hold left mouse to putt · right drag look · Tab menu" : PuttHelp;
        private View view;
        private enum View { Course, Calibration, Gallery }
        private string CoursePath => Path.Combine(Application.persistentDataPath, "course_layout.json");
        private string ObstaclePath => Path.Combine(Application.persistentDataPath, "obstacle_layout.json");

        private void Awake()
        {
#if UNITY_ANDROID && !UNITY_EDITOR
            xr = true;
#endif
            rig.gameObject.SetActive(xr);
            previewCamera.gameObject.SetActive(!xr);
            eye = xr ? rig.centerEyeAnchor.GetComponent<Camera>() : previewCamera;
            eye.allowMSAA = true;
            palette = gameObject.AddComponent<CourseView>();
            palette.FlatShader = flatShader;
            green = CourseView.Group("First-person green", transform);
            green.localPosition = Vector3.up * .32f;
            green.localScale = Vector3.one * GreenPlay.CourseMagnification;
            greenPlay = new GreenPlay(transform, xr ? rig.transform : previewCamera.transform, eye, palette, xr);
            table = new GameObject("Table placement").AddComponent<TableAnchor>();
            table.transform.SetParent(transform, false);
            stage = CourseView.Group("Course stage adjustment", table.transform);
            physical = new PhysicalObstacles(table.transform, palette);
            menu = new TableMenu(transform, palette);
            menu.Visible = false;
            BuildRoom();
            BuildPointer();
            StartBackgroundMusic();
            Cursor.lockState = CursorLockMode.None;
        }

        private void StartBackgroundMusic()
        {
            var clip = Resources.Load<AudioClip>("GolfBackground");
            if (!clip)
                return;
            var music = gameObject.AddComponent<AudioSource>();
            music.playOnAwake = false;
            music.clip = clip;
            music.loop = true;
            music.spatialBlend = 0;
            music.volume = .12f;
            music.Play();
        }

        private IEnumerator Start()
        {
            if (xr)
            {
                float timeout = Time.realtimeSinceStartup + 3;
                while (eye.transform.position.y < .2f && Time.realtimeSinceStartup < timeout)
                    yield return null;
            }
            Recenter();
            if (xr)
            {
                clubMode = (ClubMode)Mathf.Clamp(PlayerPrefs.GetInt(ClubModePreference, 1), 0, 2);
                mixedReality = PlayerPrefs.GetInt(PassthroughPreference, clubMode == ClubMode.Touch ? 0 : 1) != 0 &&
                    OVRManager.IsInsightPassthroughSupported();
                if (useSensorClub)
                    clubLink.ConnectIfAuthorized();
            }
            Randomize();
            if (layout == null)
                Generate("easy", CourseLayout.FixedSeed);
            Status(PlayHelp);
        }

        private void Update()
        {
            if (layout == null)
                return;
            if (clubLink.Poll())
                Status(clubLink.Status);
            if (mixedReality && OVRManager.HasInsightPassthroughInitFailed())
            {
                mixedReality = false;
                placeTable = addObstacle = false;
                SyncPlayMode();
                Status("Passthrough could not start. Returned to VR.");
            }
            if (!xr)
                DesktopControls();
            else
            {
                greenPlay.KeepAtLie();
                if (OVRInput.GetDown(OVRInput.Button.Two, OVRInput.Controller.RTouch) ||
                    clubMode == ClubMode.Mounted && OVRInput.GetDown(OVRInput.Button.Two, OVRInput.Controller.LTouch))
                    ToggleMenu();
            }

            if (greenPlay.Active && !menuOpen && !droppingBall)
            {
                HidePointer();
                if (pendingArrival == putting && (!xr || OVRManager.hasInputFocus))
                {
                    pendingArrival = null;
                    greenPlay.Spawn(course, putting.BallCenter);
                }
                if (xr)
                {
                    if (!putting.Rolling && !putting.Holed && greenPlay.Passthrough && OVRManager.hasInputFocus)
                    {
                        if (OVRInput.Get(OVRInput.Button.PrimaryHandTrigger, OVRInput.Controller.LTouch))
                        {
                            greenPlay.HideClub();
                            var pointer = rig.leftControllerAnchor;
                            if (OVRInput.GetControllerPositionTracked(OVRInput.Controller.LTouch) &&
                                OVRInput.GetControllerOrientationTracked(OVRInput.Controller.LTouch) &&
                                greenPlay.TryPassthroughSpot(new Ray(pointer.position, pointer.forward), out Vector3 spot))
                            {
                                floorSpot = spot;
                                cursor.position = spot + Vector3.up * .006f;
                                cursor.gameObject.SetActive(true);
                                greenPlay.ShowClubHint("Release left grip to place the ball here");
                            }
                            else
                            {
                                floorSpot = null;
                                greenPlay.ShowClubHint("Point at a spot on the floor within reach");
                            }
                            return;
                        }
                        if (floorSpot.HasValue)
                            greenPlay.PlacePassthroughBall(course, putting.BallCenter, floorSpot.Value);
                    }
                    floorSpot = null;
                    if (!putting.Rolling && OVRInput.GetDown(OVRInput.Button.One, OVRInput.Controller.RTouch))
                        greenPlay.Spawn(course, putting.Holed ? course.transform.TransformPoint(course.Tee) : putting.BallCenter, keepAim: true);
                    if (!greenPlay.AtLie)
                    {
                        greenPlay.HideClub();
                        greenPlay.ShowClubHint("Press A to bring the ball to your stance");
                        return;
                    }
                    if (clubMode == ClubMode.Mounted && OVRManager.hasInputFocus)
                    {
                        var controller = OVRInput.GetControllerPositionTracked(OVRInput.Controller.RTouch) &&
                            OVRInput.GetControllerOrientationTracked(OVRInput.Controller.RTouch)
                            ? rig.rightControllerAnchor : null;
                        greenPlay.UpdateMountedClub(course, putting, controller,
                            OVRInput.GetDown(OVRInput.Button.One, OVRInput.Controller.LTouch));
                        return;
                    }
                    if (useSensorClub && OVRManager.hasInputFocus)
                    {
                        bool fresh = clubLink.TryMotion(out ClubLink.Motion motion);
                        if (!putting.Rolling && !putting.Holed)
                        {
                            if (OVRInput.GetDown(OVRInput.Button.PrimaryThumbstick, OVRInput.Controller.RTouch))
                            {
                                FlipBackswing();
                                return;
                            }
                            if (greenPlay.TrainBackswing(fresh ? motion : null,
                                OVRInput.GetDown(OVRInput.Button.PrimaryThumbstick, OVRInput.Controller.LTouch)))
                                return;
                            if (OVRInput.Get(OVRInput.Button.PrimaryIndexTrigger, OVRInput.Controller.RTouch))
                            {
                                if (OVRInput.GetControllerPositionTracked(OVRInput.Controller.RTouch))
                                {
                                    var controller = rig.rightControllerAnchor;
                                    greenPlay.PreviewSensorAim(course, putting.BallCenter, new Ray(controller.position, controller.forward));
                                }
                                else
                                    greenPlay.HideClub();
                                return;
                            }
                            greenPlay.FinishSensorAim();
                            greenPlay.UpdateAimStick(OVRInput.Get(OVRInput.Axis2D.PrimaryThumbstick, OVRInput.Controller.RTouch).x);
                            bool left = OVRInput.GetDown(OVRInput.Button.One, OVRInput.Controller.LTouch);
                            bool right = OVRInput.GetDown(OVRInput.Button.Two, OVRInput.Controller.LTouch);
                            if (left != right)
                                greenPlay.AdjustSensorAim(left ? -5 : 5);
                        }
                        greenPlay.UpdateSensorClub(course, putting, fresh ? motion : null);
                        if (!fresh && !putting.Rolling && !putting.Holed)
                            greenPlay.ShowClubHint(clubLink.Status == "Club disconnected" ?
                                "B menu · Connect club" : clubLink.Status);
                        return;
                    }
                    if (OVRInput.GetControllerPositionTracked(OVRInput.Controller.RTouch) && OVRManager.hasInputFocus)
                        greenPlay.UpdateClub(course, putting, rig.rightControllerAnchor,
                            OVRInput.Get(OVRInput.Button.PrimaryHandTrigger, OVRInput.Controller.RTouch) ||
                            OVRInput.Get(OVRInput.Button.PrimaryIndexTrigger, OVRInput.Controller.RTouch));
                    else
                        greenPlay.HideClub();
                    return;
                }
            }

            if (!GetPointer(out Ray ray, out bool pressed, out Vector3 placement, out Transform source))
            {
                putting.CancelAim();
                if (!droppingBall)
                    held = false;
                grabbed = null;
                HidePointer();
                return;
            }

            bool down = pressed && !held;
            held = pressed;
            if (droppingBall)
            {
                bool valid = putting.TryDropTarget(ray, out Vector3 center);
                SetPointer(ray, center, valid, false);
                if (valid && down)
                {
                    droppingBall = false;
                    HidePointer();
                    putting.Drop(center);
                }
                return;
            }
            if (!pressed)
                grabbed = null;
            if (menu.Raycast(ray, out RaycastHit gui))
            {
                SetPointer(ray, gui.point, xr, false);
                menu.UpdateHover(gui.collider);
                putting.CancelAim();
                if (down)
                    menu.Press(gui.collider);
                return;
            }
            if (greenPlay.Active && menuOpen)
            {
                HidePointer();
                return;
            }
            bool hit = Physics.Raycast(ray, out RaycastHit intersection, 5f, Physics.DefaultRaycastLayers,
                QueryTriggerInteraction.Collide);
            Vector3 end = hit ? intersection.point : ray.GetPoint(1.6f);
            var plane = new Plane(table.transform.up, table.transform.position);
            float tableDistance = 0;
            bool aimAtTable = addObstacle && plane.Raycast(ray, out tableDistance) && tableDistance <= 5f;
            if (aimAtTable && (!hit || tableDistance < intersection.distance))
                end = ray.GetPoint(tableDistance);
            SetPointer(ray, end, xr && (hit || aimAtTable));
            menu.UpdateHover(null);
            if (putting.Aiming)
            {
                if (source != aimSource)
                    putting.CancelAim();
                else if (pressed)
                    putting.UpdateAim(ray);
                else
                    putting.Release();
                return;
            }
            if (grabbed)
            {
                grabbed.position = ray.GetPoint(grabDistance) + grabOffset;
                grabbed.rotation = Quaternion.Euler(0, Heading(ray.direction) - grabYaw, 0) * grabRotation;
                if (grabbed == stage)
                    UpdateObstacleGround();
                return;
            }
            if (!down)
                return;
            if (page == "Play")
            {
                if (putting.TryAim(ray, intersection))
                    aimSource = source;
                return;
            }
            if (placeTable)
            {
                PlaceTable(ray, placement);
                return;
            }
            if (addObstacle)
            {
                if (aimAtTable)
                {
                    Vector3 local = table.transform.InverseTransformPoint(ray.GetPoint(tableDistance));
                    if (Mathf.Abs(local.x) <= CourseLayout.Table.x / 2 && Mathf.Abs(local.z) <= CourseLayout.Table.y / 2)
                    {
                        Guard(() => physical.Add(local), "Obstacle added.");
                        addObstacle = false;
                        UpdateEnvironment();
                        RefreshMenu();
                    }
                    else
                        Status("Aim inside the table outline.");
                }
                return;
            }
            if (!hit || !intersection.transform.IsChildOf(stage) || view != View.Course)
                return;
            if (grabStage)
                BeginGrab(stage, ray, intersection.distance);
            else
            {
                int index = course.Movable.FindIndex(item => intersection.transform.IsChildOf(item));
                if (index >= 0)
                {
                    selectedObject = index;
                    BeginGrab(course.Movable[index], ray, intersection.distance);
                    Status("Grabbed " + course.Movable[index].name);
                }
            }
        }

        private void HidePointer()
        {
            laser.enabled = false;
            cursor.gameObject.SetActive(false);
            menu.UpdateHover(null);
        }

        private void SetPointer(Ray ray, Vector3 end, bool visible, bool drawLine = true)
        {
            laser.enabled = visible && drawLine;
            cursor.gameObject.SetActive(visible);
            if (!visible)
                return;
            Vector3 tip = end - ray.direction * .007f;
            laser.SetPosition(0, ray.origin);
            laser.SetPosition(1, tip);
            cursor.position = tip;
        }

        private void ToggleMenu()
        {
            floorSpot = null;
            if (droppingBall)
            {
                droppingBall = false;
                HidePointer();
                Status(PlayHelp);
                return;
            }
            putting.CancelAim();
            greenPlay.HideClub();
            held = true;
            if (greenPlay.Active)
                menuOpen = !menuOpen;
            else
                expanded = !expanded;
            PlaceMenu();
            RefreshMenu();
        }

        private bool GetPointer(out Ray ray, out bool pressed, out Vector3 placement, out Transform source)
        {
            ray = default;
            pressed = false;
            placement = default;
            source = null;
            if (!xr)
            {
                var mouse = Mouse.current;
                if (mouse == null)
                    return false;
                ray = eye.ScreenPointToRay(mouse.position.ReadValue());
                pressed = mouse.leftButton.isPressed;
                return true;
            }
            var active = OVRInput.GetActiveController();
            bool left = (active & OVRInput.Controller.LTouch) != 0;
            bool right = (active & OVRInput.Controller.RTouch) != 0;
            if (left && right && (putting.Aiming && aimSource == rig.leftControllerAnchor ||
                OVRInput.Get(OVRInput.Button.PrimaryIndexTrigger, OVRInput.Controller.LTouch)))
                right = false;
            if (left || right)
            {
                var controller = right ? OVRInput.Controller.RTouch : OVRInput.Controller.LTouch;
                if (OVRInput.GetControllerPositionTracked(controller))
                {
                    var pose = right ? rig.rightControllerAnchor : rig.leftControllerAnchor;
                    source = pose;
                    ray = new Ray(pose.position, pose.forward);
                    placement = pose.position;
                    pressed = OVRInput.Get(OVRInput.Button.PrimaryIndexTrigger, controller);
                    return true;
                }
            }

            bool Valid(OVRHand hand) => hand.IsTracked && hand.IsPointerPoseValid && !hand.IsSystemGestureInProgress;
            var hand = putting.Aiming && aimSource == leftHand.PointerPose ? leftHand :
                Valid(rightHand) ? rightHand : leftHand;
            if (!Valid(hand))
                return false;
            var pointer = hand.PointerPose;
            source = pointer;
            ray = new Ray(pointer.position, pointer.forward);
            placement = hand.transform.position;
            pressed = hand.GetFingerIsPinching(OVRHand.HandFinger.Index);
            return true;
        }

        private void DesktopControls()
        {
            var mouse = Mouse.current;
            if (mouse?.rightButton.isPressed == true)
            {
                if (wasMouse)
                {
                    Vector2 delta = mouse.delta.ReadValue() * .16f;
                    Vector3 angle = eye.transform.eulerAngles;
                    float pitch = Mathf.DeltaAngle(0, angle.x);
                    eye.transform.rotation = Quaternion.Euler(Mathf.Clamp(pitch - delta.y, -85, 85), angle.y + delta.x, 0);
                }
                wasMouse = true;
            }
            else
                wasMouse = false;
            var keyboard = Keyboard.current;
            if (keyboard == null)
                return;
            float x = (keyboard.dKey.isPressed ? 1 : 0) - (keyboard.aKey.isPressed ? 1 : 0);
            float z = (keyboard.wKey.isPressed ? 1 : 0) - (keyboard.sKey.isPressed ? 1 : 0);
            if (!greenPlay.Active)
                eye.transform.position += (eye.transform.right * x + eye.transform.forward * z) * (Time.deltaTime * .8f);
            if (keyboard.tabKey.wasPressedThisFrame)
            {
                if (greenPlay.Active)
                    ToggleMenu();
                else
                    PlaceMenu();
            }
            if (keyboard.rKey.wasPressedThisFrame)
                Recenter();
            if (keyboard.spaceKey.wasPressedThisFrame && page == "Play")
                ResetHole();
        }

        private void BeginGrab(Transform target, Ray ray, float distance)
        {
            RecordUndo(target);
            grabbed = target;
            grabDistance = distance;
            grabOffset = target.position - ray.GetPoint(distance);
            grabYaw = Heading(ray.direction);
            grabRotation = target.rotation;
        }

        private static float Heading(Vector3 direction) => Mathf.Atan2(direction.x, direction.z) * Mathf.Rad2Deg;

        private void RecordUndo(Transform target) => undo.Push((target, target.localPosition, target.localRotation));

        private void Undo()
        {
            if (undo.TryPop(out var edit) && edit.Target)
            {
                edit.Target.SetLocalPositionAndRotation(edit.Position, edit.Rotation);
                if (edit.Target == stage)
                    UpdateObstacleGround();
            }
        }

        private void Nudge(Vector3 translation, float yaw = 0)
        {
            var target = grabStage ? stage : course.Movable[selectedObject % course.Movable.Count];
            RecordUndo(target);
            target.position += table.transform.TransformDirection(translation);
            target.Rotate(Vector3.up, yaw, Space.World);
            if (target == stage)
                UpdateObstacleGround();
        }

        private void Recenter()
        {
            putting?.CancelAim();
            putting?.Stop();
            if (greenPlay.Active)
            {
                greenPlay.Spawn(course, putting.Holed ? course.transform.TransformPoint(course.Tee) : putting.BallCenter, keepAim: true);
                PlaceMenu();
                return;
            }
            if (mixedReality || table.Busy)
            {
                PlaceMenu();
                return;
            }
            table.Detach();
            Vector3 direction = Quaternion.Euler(0, Heading(eye.transform.forward), 0) * Vector3.forward;
            Vector3 position = eye.transform.position + direction * .88f;
            position.y = xr ? .83f : .77f;
            table.transform.SetPositionAndRotation(position, Quaternion.LookRotation(direction));
            PlaceMenu();
        }

        private void PlaceMenu() => menu.Place(eye, xr && !greenPlay.Active ? table.transform.position.y : null);

        private void PlaceTable(Ray ray, Vector3 placement)
        {
            if (table.Busy)
            {
                Status("Wait for the anchor operation to finish.");
                return;
            }
            if (!xr || !mixedReality)
            {
                Plane plane = new(Vector3.up, table.transform.position);
                if (!plane.Raycast(ray, out float distance) || distance > 3)
                {
                    Status("Aim down at the table height.");
                    return;
                }
                placement = ray.GetPoint(distance);
            }
            table.Detach();
            table.transform.SetPositionAndRotation(placement, Quaternion.Euler(0, Heading(eye.transform.forward), 0));
            placeTable = false;
            Status("Table placed. Fine-tune in Stage or save the anchor.");
            UpdateEnvironment();
        }

        private void TogglePassthrough()
        {
            if (table.Busy)
            {
                Status("Wait for the anchor operation to finish.");
                return;
            }
            if (!xr || !OVRManager.IsInsightPassthroughSupported())
            {
                Status("Passthrough requires a supported Quest headset.");
                return;
            }
            mixedReality = !mixedReality;
            PlayerPrefs.SetInt(PassthroughPreference, mixedReality ? 1 : 0);
            PlayerPrefs.Save();
            putting.CancelAim();
            putting.Stop();
            placeTable = addObstacle = false;
            SyncPlayMode();
            PlaceMenu();
            Status(mixedReality && !greenPlay.Active ? "Passthrough active. Place or restore the table." : PlayHelp);
        }

        private void SyncPlayMode()
        {
            bool immersive = page == "Play" && view == View.Course;
            bool passthroughPlay = immersive && mixedReality;
            bool changed = putting.Immersive != immersive;
            bool changedPassthrough = greenPlay.Passthrough != passthroughPlay;
            if (changed)
            {
                pendingArrival = null;
                putting.CancelAim();
                putting.Stop();
                if (immersive)
                    greenPlay.Enter();
                else
                    greenPlay.Exit();
                course.transform.SetParent(immersive ? green : stage, false);
                putting.Immersive = immersive;
                course.SetScale(scale, immersive ? GreenPlay.BallDiameter / GreenPlay.CourseMagnification : null);
                putting.ResetRound();
                Physics.SyncTransforms();
                if (!immersive)
                    menuOpen = true;
            }
            if (changedPassthrough)
            {
                pendingArrival = null;
                putting.Stop();
                greenPlay.SetPassthrough(passthroughPlay);
                green.localPosition = Vector3.up * .32f;
                Physics.SyncTransforms();
            }
            if (changed || changedPassthrough)
            {
                if (immersive)
                    greenPlay.Spawn(course, putting.Holed ? course.transform.TransformPoint(course.Tee) : putting.BallCenter);
                PlaceMenu();
            }
            UpdateEnvironment();
        }

        private void UpdateEnvironment()
        {
            passthrough.hidden = !mixedReality;
            eye.backgroundColor = mixedReality ? Color.clear : new Color32(18, 25, 38, 255);
            course.SetPassthrough(greenPlay.Passthrough);
            room.gameObject.SetActive(!mixedReality);
            stand.gameObject.SetActive(!mixedReality && !greenPlay.Active);
            outline.gameObject.SetActive(!greenPlay.Active && (boundsVisible || view == View.Calibration || placeTable || addObstacle));
            course.gameObject.SetActive(view != View.Calibration && !placeTable && !addObstacle);
            physical.Show(!greenPlay.Active && view != View.Gallery);
            UpdateObstacleGround();
        }

        private void UpdateObstacleGround() => physical.SetGround(
            !greenPlay.Active && view == View.Course && !placeTable && !addObstacle ? course.TerrainCollider : null);

        private async void AnchorOperation(bool save)
        {
            if (!xr || !mixedReality || table.Busy)
            {
                Status("Anchor controls are available in passthrough.");
                return;
            }
            placeTable = addObstacle = false;
            UpdateEnvironment();
            Status(save ? "Saving spatial anchor…" : "Looking for the saved table…");
            try
            {
                string result = save ? await table.SaveAsync() : await table.RestoreAsync();
                if (this)
                    Status(result);
            }
            catch (Exception error)
            {
                if (this)
                    Status("Anchor error: " + error.Message);
            }
        }

        private CourseLayout GenerateLayout(int requestedSeed, string mode, int resolution, int? decorationCount = null,
            double? margin = null)
        {
            var timer = System.Diagnostics.Stopwatch.StartNew();
            var data = CourseLayout.Generate(requestedSeed, mode, Math.Round(scale, 6), Math.Round(ball, 6), resolution,
                mixedReality ? physical.Footprints(stage) : Array.Empty<Bounds>(), margin ?? layout?.margin_m ?? .03,
                decorationCount ?? layout?.decoration_count ?? layout?.decor.Count ?? 4);
            Debug.Log($"[golf-generation] Seed {requestedSeed} | {mode} | {timer.Elapsed.TotalMilliseconds:F1} ms");
            return data;
        }

        private void Generate(string mode, int requestedSeed, int? resolution = null, int? decorationCount = null,
            double? margin = null)
        {
            Guard(() =>
            {
                int nextGrid = resolution ?? grid;
                var data = GenerateLayout(requestedSeed, mode, nextGrid, decorationCount, margin);
                Swap(data, scale);
                message = $"Seed {seed} · {difficulty} · {layout.archetype}";
            });
            if (layout == null)
            {
                var fallback = CourseLayout.Generate(CourseLayout.FixedSeed, "easy", scale, ball,
                    CourseLayout.ReferenceGrid, Array.Empty<Bounds>());
                Swap(fallback, scale);
                Status("Started with the easy fallback course.");
            }
        }

        private void Swap(CourseLayout data, float liveScale)
        {
            data.ValidateVrClearance(liveScale * GreenPlay.CourseMagnification, GreenPlay.BallDiameter);
            var timer = System.Diagnostics.Stopwatch.StartNew();
            var pending = CourseView.Group("Course scale", stage).gameObject.AddComponent<CourseView>();
            pending.gameObject.SetActive(false);
            Putting nextPutting;
            try
            {
                pending.Build(data, terrainShader, flatShader);
                pending.SetScale(liveScale);
                nextPutting = pending.gameObject.AddComponent<Putting>();
                nextPutting.Initialize(pending, data, Status);
            }
            catch
            {
                Destroy(pending.gameObject);
                throw;
            }
            grabbed = null;
            undo.Clear();
            previous = layout;
            previousScale = scale;
            layout = data;
            scale = liveScale;
            ball = data.ball_diameter_m;
            grid = data.terrain.grid_size;
            ApplyGraphicsPreset();
            difficulty = data.difficulty;
            seed = data.seed;
            selectedObject = 0;
            if (course)
            {
                course.gameObject.SetActive(false);
                Destroy(course.gameObject);
            }
            course = pending;
            putting = nextPutting;
            droppingBall = false;
            pendingArrival = null;
            putting.BallRested += QueueArrival;
            view = View.Course;
            pending.gameObject.SetActive(true);
            putting.ResetRound();
            SetView(View.Course);
            Debug.Log($"[golf-report] Seed {seed} | {difficulty} | {data.archetype} | " +
                $"{data.segments} segments | {data.obstacles.Count} barriers | {data.hazards.Count} pools | " +
                $"{data.decor.Count} props | build {timer.Elapsed.TotalMilliseconds:F1} ms | " +
                JsonConvert.SerializeObject(data.validation));
        }

        private void ChangeScale(float delta)
        {
            Guard(() =>
            {
                float next = Mathf.Clamp(delta == 0 ? CourseLayout.DefaultScale : scale + delta, .10f, 1f);
                layout.ValidateVrClearance(next * GreenPlay.CourseMagnification, GreenPlay.BallDiameter);
                scale = next;
                course.SetScale(scale);
                putting.ResetRound();
                UpdateObstacleGround();
                bool overflow = layout.terrain.width_m * scale > CourseLayout.Table.x ||
                    layout.terrain.length_m * scale > CourseLayout.Table.y;
                message = $"Course scale {scale:F2}" + (overflow ? " · extends past table bounds" : "");
            });
        }

        private void ApplyGraphicsPreset()
        {
            bool performance = grid <= 65;
            int samples = performance ? 2 : 4;
            int anisotropy = performance ? 4 : 8;
            QualitySettings.antiAliasing = samples;
            QualitySettings.anisotropicFiltering = AnisotropicFiltering.Enable;
            Texture.SetGlobalAnisotropicFilteringLimits(1, anisotropy);
            if (!xr)
                return;

            SubsystemManager.GetSubsystems(displays);
            foreach (XRDisplaySubsystem display in displays)
            {
                if (!display.running)
                    continue;
                display.SetMSAALevel(samples);
                if (graphicsReport != null)
                    StopCoroutine(graphicsReport);
                graphicsReport = StartCoroutine(ReportGraphics(display, samples, anisotropy));
                break;
            }
        }

        private IEnumerator ReportGraphics(XRDisplaySubsystem display, int samples, int anisotropy)
        {
            const int count = 45;
            for (int i = 0; i < 12; i++)
                yield return null;
            float frameSeconds = 0;
            float gpuSeconds = 0;
            int gpuFrames = 0;
            for (int i = 0; i < count; i++)
            {
                yield return null;
                frameSeconds += Time.unscaledDeltaTime;
                if (display.TryGetAppGPUTimeLastFrame(out float gpu))
                {
                    gpuSeconds += gpu;
                    gpuFrames++;
                }
            }
            int targetSamples = 0;
            if (display.GetRenderPassCount() > 0)
            {
                display.GetRenderPass(0, out XRDisplaySubsystem.XRRenderPass pass);
                targetSamples = pass.renderTargetDesc.msaaSamples;
            }
            string gpuTime = gpuFrames == 0 ? "unavailable" : $"{1000 * gpuSeconds / gpuFrames:F2} ms";
            Debug.Log($"[golf-graphics] {grid}x{grid} | MSAA requested {samples} | " +
                $"eye descriptor {XRSettings.eyeTextureDesc.msaaSamples} | XR target {targetSamples} | " +
                $"anisotropy limit {anisotropy} | avg frame {1000 * frameSeconds / count:F2} ms | app GPU {gpuTime}");
            graphicsReport = null;
        }

        private void ChangeBall(float delta)
        {
            float nextBall = Mathf.Clamp(ball + delta, .020f, .043f);
            float old = ball;
            ball = nextBall;
            Generate(difficulty, seed);
            ball = layout.ball_diameter_m;
            if (ball != old)
                Status($"Ball diameter {ball * 1000:F0} mm");
        }

        private void SaveCourse()
        {
            var snapshot = CourseLayout.Parse(layout.ToJson());
            snapshot.course_scale = scale;
            snapshot.Validate();
            File.WriteAllText(CoursePath, snapshot.ToJson());
        }

        private void SetView(View next)
        {
            view = next;
            course.ShowGallery(view == View.Gallery, galleryIndex);
            course.ShowNeon(neon && view == View.Course);
            course.ShowDebug(diagnostics && view == View.Course);
            SyncPlayMode();
            RefreshMenu();
        }

        private void BuildRoom()
        {
            RenderSettings.ambientMode = UnityEngine.Rendering.AmbientMode.Flat;
            RenderSettings.ambientLight = new Color(.26f, .29f, .34f);
            var key = CourseView.Group("Course key light", transform).gameObject.AddComponent<Light>();
            key.type = LightType.Directional;
            key.intensity = 1;
            key.color = new Color(.92f, .95f, 1);
            key.transform.rotation = Quaternion.LookRotation(new Vector3(.4f, -1, .4f));

            room = CourseView.Group("VR workshop", transform);
            var floor = new Color32(37, 50, 68, 255);
            var wall = new Color32(28, 36, 52, 255);
            Solid(room, "Floor", new Vector3(0, -.04f, 0), new Vector3(18, .08f, 18), floor);
            Solid(room, "Back wall", new Vector3(0, 2, 8f), new Vector3(16, 4, .1f), wall);
            Solid(room, "Left wall", new Vector3(-8f, 2, 0), new Vector3(.1f, 4, 16), wall);
            Solid(room, "Right wall", new Vector3(8f, 2, 0), new Vector3(.1f, 4, 16), wall);
            for (int i = -7; i <= 7; i++)
            {
                Solid(room, "Floor grid", new Vector3(i, .001f, 0), new Vector3(.009f, .003f, 16), wall);
                Solid(room, "Floor grid", new Vector3(0, .001f, i), new Vector3(16, .003f, .009f), wall);
            }
            stand = CourseView.Group("Virtual tabletop", table.transform);
            Solid(stand, "Tabletop", new Vector3(0, -.045f, 0), new Vector3(.72f, .035f, .52f), floor);
            Solid(stand, "Stand", new Vector3(0, -.42f, 0), new Vector3(.18f, .74f, .19f), wall);
            outline = CourseView.Group("Table bounds", table.transform);
            Vector2 size = CourseLayout.Table;
            for (int sign = -1; sign <= 1; sign += 2)
            {
                Solid(outline, "Long edge", new Vector3(0, .002f, sign * size.y / 2),
                    new Vector3(size.x, .003f, .003f), CourseView.Cyan);
                Solid(outline, "Short edge", new Vector3(sign * size.x / 2, .002f, 0),
                    new Vector3(.003f, .003f, size.y), CourseView.Cyan);
            }
            outline.gameObject.SetActive(false);
        }

        private void BuildPointer()
        {
            cursor = Solid(transform, "Pointer hit", Vector3.zero, Vector3.one * .008f, CourseView.Lime);
            cursor.gameObject.SetActive(false);
            laser = CourseView.Group("Pointer ray", transform).gameObject.AddComponent<LineRenderer>();
            laser.positionCount = 2;
            laser.widthMultiplier = .0018f;
            laser.sharedMaterial = palette.Paint(CourseView.Cyan);
            laser.enabled = false;
        }

        private Transform Solid(Transform parent, string name, Vector3 center, Vector3 size, Color color)
        {
            var obj = palette.Block(parent, name, center, size, color);
            obj.GetComponent<Collider>().enabled = false;
            return obj;
        }

        private void Guard(Action action, string success = null)
        {
            try
            {
                action();
                if (success != null)
                    message = success;
            }
            catch (Exception error) when (error is ArgumentException or IOException or JsonException)
            {
                message = error.Message;
                Debug.LogWarning("[GolfAR] " + error.Message);
            }
            RefreshMenu();
        }

        private void Status(string value)
        {
            message = value;
            RefreshMenu();
        }

        private TableMenu.Entry Entry(string label, Action action) => new(label, action);

        private void FlipBackswing()
        {
            Status(greenPlay.FlipBackswing() ? "Swing direction flipped · hold still at address" :
                "Click left stick and take the club straight back to set direction");
        }

        private void SetClubMode(ClubMode mode)
        {
            clubMode = mode;
            if (xr)
            {
                PlayerPrefs.SetInt(ClubModePreference, (int)mode);
                PlayerPrefs.Save();
            }
            greenPlay.HideClub();
            if (mode == ClubMode.Mounted)
                greenPlay.ClearMountedCalibration();
        }

        private void ResetHole()
        {
            droppingBall = false;
            pendingArrival = null;
            putting.ResetRound();
            if (greenPlay.Active)
            {
                greenPlay.Spawn(course, putting.BallCenter);
                menuOpen = false;
            }
            Status(PlayHelp);
        }

        private void BeginDrop()
        {
            if (!greenPlay.Active || putting.Rolling || putting.Holed)
                return;
            droppingBall = true;
            held = true;
            menuOpen = false;
            putting.CancelAim();
            greenPlay.HideClub();
            Status(xr ? "Aim within 1.5 m · trigger to drop (+1) · B cancel" :
                "Aim within 1.5 m · click to drop (+1) · Tab cancel");
        }

        private void QueueArrival(Putting rested)
        {
            if (greenPlay.Active && rested == putting)
                pendingArrival = rested;
        }

        private TableMenu.Entry Tab(string label) => Entry(label, () =>
        {
            if (label == page)
                return;
            putting.CancelAim();
            putting.Stop();
            page = label;
            if (page == "Play")
            {
                grabbed = null;
                placeTable = addObstacle = false;
                SetView(View.Course);
                ResetHole();
            }
            else
            {
                SyncPlayMode();
                // Edit mode shows the ball at the tee even after a completed hole.
                if (putting.Holed)
                    putting.ResetRound();
                RefreshMenu();
            }
        });

        private void RefreshMenu()
        {
            if (menu == null)
                return;
            string headline = $"GolfAR · {(mixedReality ? "MR" : "VR")} · {page}";
            string line = message.Length > 63 ? message[..60] + "…" : message;
            menu.Visible = !greenPlay.Active || menuOpen;
            greenPlay.ShowStatus(line, !menuOpen);
            if (!menu.Visible)
                return;
            if (!expanded && !greenPlay.Active)
            {
                menu.Set(headline, line, new[] { Entry("Show menu", () => { expanded = true; RefreshMenu(); }) });
                return;
            }
            var entries = new List<TableMenu.Entry>
            {
                Tab("Play"), Tab("Course"), Tab("Stage"), Tab("Obstacles"), Tab("Display"),
                Entry(mixedReality ? "Enter VR" : "Passthrough", TogglePassthrough),
                Entry("Hide menu", () => { if (greenPlay.Active) ToggleMenu(); else { expanded = false; RefreshMenu(); } })
            };
            switch (page)
            {
                case "Play":
                    if (greenPlay.Active && !putting.Rolling && !putting.Holed)
                        entries.Add(Entry("Drop ball", BeginDrop));
                    entries.Insert(0, Entry(clubLink.Requested ? "Disconnect club" : "Connect club", () =>
                    {
                        clubLink.Toggle();
                        if (clubLink.Requested || useSensorClub)
                            SetClubMode(clubLink.Requested ? ClubMode.Gyro : ClubMode.Touch);
                        Status(clubLink.Status);
                    }));
                    if (clubMode != ClubMode.Touch)
                        entries.Insert(1, Entry("Use Touch", () => { SetClubMode(ClubMode.Touch); Status(PlayHelp); }));
                    if (!useSensorClub && clubLink.Requested)
                        entries.Add(Entry("Use gyro", () => { SetClubMode(ClubMode.Gyro); Status(PlayHelp); }));
                    if (xr && clubMode != ClubMode.Mounted)
                        entries.Insert(1, Entry("Track club", () => { SetClubMode(ClubMode.Mounted); Status(PlayHelp); }));
                    if (useSensorClub && !putting.Rolling && !putting.Holed)
                    {
                        entries.Add(Entry("Flip swing", FlipBackswing));
                        entries.Add(Entry("Aim left 5°", () => greenPlay.AdjustSensorAim(-5)));
                        entries.Add(Entry("Aim right 5°", () => greenPlay.AdjustSensorAim(5)));
                    }
                    entries.Add(Entry("Reset hole", ResetHole));
                    break;
                case "Course":
                    entries.AddRange(new[] {
                        Entry("Easy", () => Generate("easy", seed)), Entry("Medium", () => Generate("medium", seed)),
                        Entry("Hard", () => Generate("hard", seed)), Entry("New seed", Randomize),
                        Entry("Regenerate", () => Generate(difficulty, seed)),
                        Entry("Fixed demo", () => Generate("medium", CourseLayout.FixedSeed,
                            CourseLayout.ReferenceGrid, decorationCount: 6, margin: .03)),
                        Entry("Previous", () => Guard(() => { if (previous != null) Swap(previous, previousScale); }, "Previous course restored.")),
                        Entry("Save layout", () => Guard(SaveCourse, "Course saved.")),
                        Entry("Load layout", () => Guard(() => { var data = CourseLayout.Parse(File.ReadAllText(CoursePath)); Swap(data, data.course_scale); }, "Course loaded.")),
                        Tab("Enter seed"), Entry("Ball −1 mm", () => ChangeBall(-.001f)), Entry("Ball +1 mm", () => ChangeBall(.001f))
                    });
                    break;
                case "Stage":
                    entries.AddRange(new[] {
                        Entry(placeTable ? "Cancel placement" : "Place table", () => { placeTable = !placeTable; addObstacle = false; UpdateEnvironment();
                            Status(placeTable ? mixedReality ? "Touch the tabletop center and trigger or pinch." : "Aim at table height and select." : "Placement canceled."); }),
                        Entry("Save anchor", () => AnchorOperation(true)), Entry("Restore anchor", () => AnchorOperation(false)),
                        Entry("Recenter", Recenter), Entry(grabStage ? "Grab: stage" : "Grab: object", () => { grabStage = !grabStage; RefreshMenu(); }),
                        Entry("Next object", () => { selectedObject = (selectedObject + 1) % course.Movable.Count; Status(course.Movable[selectedObject].name); }),
                        Entry("Undo move", Undo), Entry("Reset stage", () => { RecordUndo(stage); stage.SetLocalPositionAndRotation(Vector3.zero, Quaternion.identity); UpdateObstacleGround(); }),
                        Entry("Scale reset", () => ChangeScale(0)), Entry("Scale −", () => ChangeScale(-.05f)), Entry("Scale +", () => ChangeScale(.05f)),
                        Entry("Fine tune", () => { page = "Fine tune"; RefreshMenu(); })
                    });
                    break;
                case "Fine tune":
                    entries.AddRange(NudgeEntries(Nudge));
                    break;
                case "Obstacles":
                    entries.AddRange(new[] {
                        Entry(addObstacle ? "Cancel add" : "Add obstacle", () => { addObstacle = !addObstacle; placeTable = false; UpdateEnvironment();
                            Status(addObstacle ? "Aim at the object's footprint and select." : "Placement canceled."); }),
                        Entry("Next obstacle", () => ObstacleEdit(physical.Cycle)), Entry("Change type", () => ObstacleEdit(physical.ChangeKind)),
                        Entry("Footprint −", () => ObstacleEdit(() => physical.Resize(-.005f))),
                        Entry("Footprint +", () => ObstacleEdit(() => physical.Resize(.005f))),
                        Entry("Highlight", () => ObstacleEdit(physical.ToggleHighlight)),
                        Entry("Remove", () => ObstacleEdit(physical.Remove)), Entry("Clear all", () => ObstacleEdit(physical.Clear)), Tab("Move obstacle"),
                        Entry("Save obstacles", () => Guard(() => physical.Save(ObstaclePath), "Obstacles saved.")),
                        Entry("Load obstacles", () => Guard(() => physical.Load(ObstaclePath), "Obstacles loaded."))
                    });
                    break;
                case "Move obstacle":
                    entries.AddRange(NudgeEntries((delta, _) => ObstacleEdit(() =>
                    {
                        physical.Move(new Vector2(delta.x, delta.z));
                        if (delta.y != 0)
                            physical.ChangeHeight(delta.y);
                    }), false));
                    break;
                case "Display":
                    entries.AddRange(new[] {
                        Entry("Course view", () => SetView(View.Course)), Entry("Calibration", () => SetView(View.Calibration)),
                        Entry("Prop gallery", () => SetView(View.Gallery)),
                        Entry("Next prop", () => { galleryIndex = (galleryIndex + 1) % CourseView.GalleryAssets.Length;
                            SetView(View.Gallery); Status(CourseView.GalleryAssets[galleryIndex]); }),
                        Entry("Table outline", () => { boundsVisible = !boundsVisible; UpdateEnvironment(); }),
                        Entry("Route debug", () => { diagnostics = !diagnostics; SetView(view); }),
                        Entry("Neon trim", () => { neon = !neon; SetView(view); }),
                        Entry("Performance", () => Generate(difficulty, seed, 65)),
                        Entry("Balanced", () => Generate(difficulty, seed, 97)),
                        Entry("Quality", () => Generate(difficulty, seed, 129))
                    });
                    break;
                case "Enter seed":
                    line = $"Seed: {seedText}";
                    for (int digit = 0; digit < 10; digit++)
                    {
                        string key = digit.ToString();
                        entries.Add(Entry(key, () => { if (seedText.Length < 11) seedText += key; RefreshMenu(); }));
                    }
                    entries.Add(Entry("±", () => { seedText = seedText.StartsWith("-") ? seedText[1..] : "-" + seedText; RefreshMenu(); }));
                    entries.Add(Entry("Backspace", () => { if (seedText.Length > 0) seedText = seedText[..^1]; RefreshMenu(); }));
                    entries.Add(Entry("Apply seed", () =>
                    {
                        if (int.TryParse(seedText, out int value))
                        {
                            page = "Course";
                            Generate(difficulty, value);
                        }
                        else
                        {
                            page = "Course";
                            Status("Enter a signed 32-bit seed.");
                        }
                    }));
                    break;
            }
            menu.Set(headline, line, entries.ToArray());
        }

        private IEnumerable<TableMenu.Entry> NudgeEntries(Action<Vector3, float> adjust, bool yaw = true)
        {
            yield return Entry("Left 1 cm", () => adjust(Vector3.left * .01f, 0));
            yield return Entry("Right 1 cm", () => adjust(Vector3.right * .01f, 0));
            yield return Entry("Forward 1 cm", () => adjust(Vector3.forward * .01f, 0));
            yield return Entry("Back 1 cm", () => adjust(Vector3.back * .01f, 0));
            yield return Entry("Up 1 cm", () => adjust(Vector3.up * .01f, 0));
            yield return Entry("Down 1 cm", () => adjust(Vector3.down * .01f, 0));
            if (yaw)
            {
                yield return Entry("Yaw −5°", () => adjust(Vector3.zero, -5));
                yield return Entry("Yaw +5°", () => adjust(Vector3.zero, 5));
            }
        }

        private void ObstacleEdit(Action edit)
        {
            edit();
            Status(physical.Summary);
        }

        private void Randomize()
        {
            for (int attempt = 0; attempt < 12; attempt++)
            {
                try
                {
                    var next = GenerateLayout(UnityEngine.Random.Range(1, int.MaxValue), difficulty, grid);
                    Swap(next, scale);
                    Status($"Seed {seed} · {difficulty} · {layout.archetype}");
                    return;
                }
                catch (ArgumentException)
                {
                    // Some bends cannot accommodate the shortcut blockers.
                }
            }
            Status("Could not fit a validated layout. Try a different difficulty.");
        }

        private void OnDestroy() => clubLink.Dispose();
    }
}
