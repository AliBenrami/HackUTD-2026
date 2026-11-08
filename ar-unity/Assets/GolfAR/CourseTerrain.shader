Shader "GolfAR/CourseTerrain"
{
    Properties
    {
        _Tint ("Tint", Color) = (1, 1, 1, 1)
        _UseVertexColor ("Vertex colors", Float) = 1
        _Coverage ("Passthrough coverage", Range(0, 1)) = 1
    }
    SubShader
    {
        Tags { "RenderType"="Opaque" }
        Pass
        {
            CGPROGRAM
            #pragma vertex vert
            #pragma fragment frag
            #pragma multi_compile_instancing
            #include "UnityCG.cginc"

            fixed4 _Tint;
            half _UseVertexColor;
            half _Coverage;

            struct VertexInput
            {
                float4 position : POSITION;
                float3 normal : NORMAL;
                fixed4 color : COLOR;
                UNITY_VERTEX_INPUT_INSTANCE_ID
            };

            struct VertexOutput
            {
                float4 position : SV_POSITION;
                fixed4 color : COLOR;
                half3 normal : TEXCOORD0;
                UNITY_VERTEX_OUTPUT_STEREO
            };

            VertexOutput vert(VertexInput input)
            {
                VertexOutput output;
                UNITY_SETUP_INSTANCE_ID(input);
                UNITY_INITIALIZE_OUTPUT(VertexOutput, output);
                UNITY_INITIALIZE_VERTEX_OUTPUT_STEREO(output);
                output.position = UnityObjectToClipPos(input.position);
                output.normal = UnityObjectToWorldNormal(input.normal);
                output.color = fixed4(lerp(_Tint.rgb, input.color.rgb, _UseVertexColor), 1);
                return output;
            }

            fixed4 frag(VertexOutput input) : SV_Target
            {
                half3 normal = normalize(input.normal);
                half key = saturate(dot(normal, normalize(half3(-.4, 1, -.4))));
                half fill = saturate(dot(normal, normalize(half3(.58, .57, .58))));
                half3 light = half3(.22, .27, .32) + key * half3(.92, .95, 1) + fill * half3(.16, .27, .31);
                // The XR compositor blends the premultiplied eye buffer over camera passthrough.
                return fixed4(input.color.rgb * light * _Coverage, _Coverage);
            }
            ENDCG
        }
    }
}
