#version 410
// A rectangle in its own pixel space [origin, origin + extent], projected by u_mvp.
// Every render target stores the image top at row 0, so clip y is flipped.
uniform mat4 u_mvp;
uniform vec2 u_origin;
uniform vec2 u_extent;
out vec2 v_p;

void main() {
    vec2 corner = vec2(gl_VertexID & 1, (gl_VertexID >> 1) & 1);
    v_p = u_origin + corner * u_extent;
    vec4 clip = u_mvp * vec4(v_p, 0.0, 1.0);
    clip.y = -clip.y;
    gl_Position = clip;
}
