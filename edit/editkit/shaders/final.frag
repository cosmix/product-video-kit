// Frame finishing: bloom mix, a soft shoulder, fade, encode to display sRGB, film grain.
// Grain is generated at output resolution and doubles as dither against banding.
in vec2 v_uv;
out vec4 f_color;

uniform sampler2D u_frame;
uniform sampler2D u_bloom;
uniform vec2 u_res;
uniform float u_bloom_amt;
uniform float u_grain;
uniform float u_seed;
uniform float u_fade;        // 0..1 fade to black (head and tail)

void main() {
    vec3 c = texture(u_frame, v_uv).rgb + texture(u_bloom, v_uv).rgb * u_bloom_amt;

    // soft shoulder so bloom and bright UI never clip harshly
    c = c / (1.0 + max(c - 0.9, 0.0) * 0.6);
    c *= 1.0 - u_fade;

    vec3 s = linear_to_srgb(c);
    float live = 1.0 - u_fade;   // grain and dither fade with the picture, so black is exactly black
    if (u_grain > 0.0) {
        vec2 px = floor(v_uv * u_res);
        float n = hash12(px + u_seed * 17.13) + hash12(px * 1.37 + u_seed * 31.7) - 1.0;
        float luma = dot(s, vec3(0.2126, 0.7152, 0.0722));
        float amt = u_grain * mix(0.55, 1.0, smoothstep(0.0, 0.5, luma)) * (1.0 - smoothstep(0.75, 1.0, luma) * 0.5);
        s += n * amt * live;
    } else {
        s += (hash12(floor(v_uv * u_res) + u_seed) - 0.5) / 255.0 * live;
    }
    f_color = vec4(clamp(s, 0.0, 1.0), 1.0);
}
