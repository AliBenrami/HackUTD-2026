using System;
using System.IO;
using System.Linq;
using Meta.XR;
using UnityEditor;
using UnityEditor.Build;
using UnityEditor.SceneManagement;
using UnityEditor.XR.Management;
using UnityEditor.XR.Management.Metadata;
using UnityEditor.XR.OpenXR.Features;
using UnityEngine;
using UnityEngine.Rendering;
using UnityEngine.XR.Management;
using UnityEngine.XR.OpenXR;
using UnityEngine.XR.OpenXR.Features.Interactions;
using UnityEngine.XR.OpenXR.Features.MetaQuestSupport;

namespace GolfAR.Editor
{
    public static class QuestProject
    {
        private const string ScenePath = "Assets/GolfAR/GolfTable.unity";
        private const string MetaPrefabs = "Packages/com.meta.xr.sdk.core/Prefabs/";
        private const string XRSettingsPath = "Assets/XR/XRGeneralSettings.asset";

        [MenuItem("GolfAR/Build Quest APK")]
        public static void BuildQuest()
        {
            if (!BuildPipeline.IsBuildTargetSupported(BuildTargetGroup.Android, BuildTarget.Android))
                throw new BuildFailedException("Install Unity Android Build Support with the SDK, NDK, and OpenJDK modules.");
            Directory.CreateDirectory("Builds");
            var report = BuildPipeline.BuildPlayer(new BuildPlayerOptions
            {
                scenes = new[] { ScenePath },
                locationPathName = "Builds/GolfAR-Quest.apk",
                target = BuildTarget.Android
            });
            if (report.summary.result != UnityEditor.Build.Reporting.BuildResult.Succeeded)
                throw new BuildFailedException("Quest APK build failed. See the Unity Console or batch log.");
            Debug.Log($"GolfAR Quest APK: {Path.GetFullPath(report.summary.outputPath)}");
        }

        // The resulting scene and settings are versioned. This also lets a
        // developer recreate the scene with the pinned SDK's original prefabs.
        public static void CreateProject()
        {
            ConfigureAndroid();
            EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
            var rig = (GameObject)PrefabUtility.InstantiatePrefab(AssetDatabase.LoadAssetAtPath<GameObject>(MetaPrefabs + "OVRCameraRig.prefab"));
            var manager = rig.GetComponent<OVRManager>();
            manager.isInsightPassthroughEnabled = true;
            var managerFields = new SerializedObject(manager);
            managerFields.FindProperty("_trackingOriginType").intValue = (int)OVRManager.TrackingOrigin.FloorLevel;
            managerFields.ApplyModifiedPropertiesWithoutUndo();
            var tracking = rig.transform.Find("TrackingSpace");
            var eye = tracking.Find("CenterEyeAnchor").GetComponent<Camera>();
            ConfigureCamera(eye);
            var passthrough = rig.AddComponent<OVRPassthroughLayer>();
            passthrough.hidden = true;
            var left = AddHand(tracking.Find("LeftHandAnchor"), OVRHand.Hand.HandLeft, tracking);
            var right = AddHand(tracking.Find("RightHandAnchor"), OVRHand.Hand.HandRight, tracking);
            rig.SetActive(false);

            var preview = new GameObject("Desktop Preview Camera").AddComponent<Camera>();
            preview.gameObject.AddComponent<AudioListener>();
            preview.transform.SetPositionAndRotation(new Vector3(0, 1.33f, -.55f), Quaternion.Euler(28, 0, 0));
            ConfigureCamera(preview);
            var app = new GameObject("GolfAR").AddComponent<GolfTable>();
            var fields = new SerializedObject(app);
            fields.FindProperty("rig").objectReferenceValue = rig.GetComponent<OVRCameraRig>();
            fields.FindProperty("passthrough").objectReferenceValue = passthrough;
            fields.FindProperty("leftHand").objectReferenceValue = left;
            fields.FindProperty("rightHand").objectReferenceValue = right;
            fields.FindProperty("previewCamera").objectReferenceValue = preview;
            fields.FindProperty("terrainShader").objectReferenceValue = Shader.Find("GolfAR/CourseTerrain");
            fields.FindProperty("flatShader").objectReferenceValue = Shader.Find("Unlit/Color");
            fields.ApplyModifiedPropertiesWithoutUndo();

            EditorSceneManager.SaveScene(app.gameObject.scene, ScenePath);
            EditorBuildSettings.scenes = new[] { new EditorBuildSettingsScene(ScenePath, true) };
            AssetDatabase.SaveAssets();
        }

        private static void ConfigureCamera(Camera camera)
        {
            camera.clearFlags = CameraClearFlags.SolidColor;
            camera.backgroundColor = new Color32(18, 25, 38, 255);
            camera.allowHDR = false;
            camera.nearClipPlane = .05f;
            camera.farClipPlane = 30;
        }

        private static OVRHand AddHand(Transform parent, OVRHand.Hand hand, Transform tracking)
        {
            var prefab = AssetDatabase.LoadAssetAtPath<GameObject>(MetaPrefabs + "OVRHandPrefab.prefab");
            var handObject = (GameObject)PrefabUtility.InstantiatePrefab(prefab, parent);
            handObject.name = hand == OVRHand.Hand.HandLeft ? "Left Meta hand" : "Right Meta hand";
            var component = handObject.GetComponent<OVRHand>();
            var fields = new SerializedObject(component);
            fields.FindProperty("HandType").intValue = (int)hand;
            fields.FindProperty("_pointerPoseRoot").objectReferenceValue = tracking;
            fields.ApplyModifiedPropertiesWithoutUndo();
            foreach (string componentName in new[] { "OVRSkeleton", "OVRMesh" })
            {
                var behaviour = (Behaviour)handObject.GetComponent(componentName);
                if (behaviour == null)
                    continue;
                var handFields = new SerializedObject(behaviour);
                var type = handFields.FindProperty(componentName == "OVRSkeleton" ? "_skeletonType" : "_meshType");
                if (type != null)
                    type.intValue = (int)hand;
                handFields.ApplyModifiedPropertiesWithoutUndo();
            }
            return component;
        }

        private static void ConfigureAndroid()
        {
            PlayerSettings.companyName = "GolfAR";
            PlayerSettings.productName = "GolfAR Quest";
            PlayerSettings.colorSpace = ColorSpace.Linear;

            PlayerSettings.SetApplicationIdentifier(NamedBuildTarget.Android, "com.golfar.quest");
            PlayerSettings.SetScriptingBackend(NamedBuildTarget.Android, ScriptingImplementation.IL2CPP);
            PlayerSettings.Android.targetArchitectures = AndroidArchitecture.ARM64;
            PlayerSettings.Android.minSdkVersion = AndroidSdkVersions.AndroidApiLevel32;
            PlayerSettings.Android.targetSdkVersion = AndroidSdkVersions.AndroidApiLevel34;
            PlayerSettings.SetUseDefaultGraphicsAPIs(BuildTarget.Android, false);
            PlayerSettings.SetGraphicsAPIs(BuildTarget.Android, new[] { GraphicsDeviceType.Vulkan });
            PlayerSettings.Android.applicationEntry = AndroidApplicationEntry.Activity;
            PlayerSettings.MTRendering = true;
            QualitySettings.antiAliasing = 4;

            var xr = AssetDatabase.LoadAssetAtPath<XRGeneralSettingsPerBuildTarget>(XRSettingsPath);
            if (xr == null)
            {
                if (!AssetDatabase.IsValidFolder("Assets/XR"))
                    AssetDatabase.CreateFolder("Assets", "XR");
                xr = ScriptableObject.CreateInstance<XRGeneralSettingsPerBuildTarget>();
                AssetDatabase.CreateAsset(xr, XRSettingsPath);
            }
            EditorBuildSettings.AddConfigObject(XRGeneralSettings.settingsKey, xr, true);
            if (!xr.HasSettingsForBuildTarget(BuildTargetGroup.Android))
                xr.CreateDefaultSettingsForBuildTarget(BuildTargetGroup.Android);
            if (!xr.HasManagerSettingsForBuildTarget(BuildTargetGroup.Android))
                xr.CreateDefaultManagerSettingsForBuildTarget(BuildTargetGroup.Android);
            var settings = xr.SettingsForBuildTarget(BuildTargetGroup.Android);
            settings.InitManagerOnStart = true;
            var loaders = xr.ManagerSettingsForBuildTarget(BuildTargetGroup.Android);
            if (!loaders.activeLoaders.Any(loader => loader is OpenXRLoader) &&
                !XRPackageMetadataStore.AssignLoader(loaders, typeof(OpenXRLoader).FullName, BuildTargetGroup.Android))
                throw new BuildFailedException("Could not assign the Android OpenXR loader.");

            FeatureHelpers.RefreshFeatures(BuildTargetGroup.Android);
            var openXR = OpenXRSettings.GetSettingsForBuildTargetGroup(BuildTargetGroup.Android);
            openXR.renderMode = OpenXRSettings.RenderMode.SinglePassInstanced;
            foreach (var feature in openXR.GetFeatures())
            {
                feature.enabled = feature is MetaQuestFeature or OculusTouchControllerProfile or MetaXRFeature;
                EditorUtility.SetDirty(feature);
            }
            EditorUtility.SetDirty(openXR);
            EditorUtility.SetDirty(loaders);
            EditorUtility.SetDirty(settings);
            EditorUtility.SetDirty(xr);

            var config = OVRProjectConfig.CachedProjectConfig;
            config.targetDeviceTypes.Clear();
            config.targetDeviceTypes.AddRange(new[]
            {
                OVRProjectConfig.DeviceType.Quest2, OVRProjectConfig.DeviceType.QuestPro,
                OVRProjectConfig.DeviceType.Quest3, OVRProjectConfig.DeviceType.Quest3S
            });
            config.insightPassthroughSupport = OVRProjectConfig.FeatureSupport.Supported;
            config.handTrackingSupport = OVRProjectConfig.HandTrackingSupport.ControllersAndHands;
            config.anchorSupport = OVRProjectConfig.AnchorSupport.Enabled;
            OVRProjectConfig.CommitProjectConfig(config);
        }
    }
}
