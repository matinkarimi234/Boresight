/* drm_overlay_example.c

   A simplified DRM/KMS application that:
   - Opens a DRM device (e.g. /dev/dri/card1),
   - Finds a connected connector and display mode,
   - Sets the CRTC with a primary “dumb” framebuffer (dummy content),
   - Creates an overlay “dumb” buffer with a drawn white cross,
   - Queries property IDs dynamically for the overlay plane,
   - And uses an atomic commit to add the overlay on top.

   Compile with:
       gcc -D_FILE_OFFSET_BITS=64 -o drm_overlay_example drm_overlay_example.c -ldrm

   Make sure your /boot/config.txt is set for full KMS:
       dtoverlay=vc4-kms-v3d
       disable_fw_kms_setup=1
*/

#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <fcntl.h>
#include <unistd.h>
#include <string.h>
#include <errno.h>
#include <sys/mman.h>
#include <xf86drm.h>
#include <xf86drmMode.h>
#include <drm/drm_mode.h>

// Structure for a dumb buffer
struct dumb_buf {
    uint32_t handle;
    uint32_t pitch;
    uint64_t size;
    void *map;
    uint32_t fb_id;
};

// Create a dumb buffer, add it as an FB, and mmap it.
int create_dumb_buffer(int fd, uint32_t width, uint32_t height, struct dumb_buf *buf) {
    struct drm_mode_create_dumb create_req = {0};
    create_req.width = width;
    create_req.height = height;
    create_req.bpp = 32;
    if (drmIoctl(fd, DRM_IOCTL_MODE_CREATE_DUMB, &create_req) < 0) {
        perror("DRM_IOCTL_MODE_CREATE_DUMB");
        return -1;
    }
    buf->handle = create_req.handle;
    buf->pitch = create_req.pitch;
    buf->size = create_req.size;

    if (drmModeAddFB(fd, width, height, 24, 32, buf->pitch, buf->handle, &buf->fb_id)) {
        perror("drmModeAddFB");
        return -1;
    }

    struct drm_mode_map_dumb map_req = {0};
    map_req.handle = buf->handle;
    if (drmIoctl(fd, DRM_IOCTL_MODE_MAP_DUMB, &map_req) < 0) {
        perror("DRM_IOCTL_MODE_MAP_DUMB");
        return -1;
    }
    buf->map = mmap(0, buf->size, PROT_READ | PROT_WRITE, MAP_SHARED, fd, map_req.offset);
    if (buf->map == MAP_FAILED) {
        perror("mmap");
        return -1;
    }
    return 0;
}

// Helper function to get a property ID by name for a DRM object
uint32_t get_property_id(int fd, uint32_t object_id, uint32_t object_type, const char *prop_name) {
    drmModeObjectProperties *props = drmModeObjectGetProperties(fd, object_id, object_type);
    if (!props) {
        fprintf(stderr, "Failed to get properties for object %u\n", object_id);
        return 0;
    }

    uint32_t prop_id = 0;
    for (uint32_t i = 0; i < props->count_props; i++) {
        drmModePropertyPtr prop = drmModeGetProperty(fd, props->props[i]);
        if (prop) {
            if (strcmp(prop->name, prop_name) == 0) {
                prop_id = prop->prop_id;
                drmModeFreeProperty(prop);
                break;
            }
            drmModeFreeProperty(prop);
        }
    }
    drmModeFreeObjectProperties(props);
    return prop_id;
}

int main(void)
{
    /* Open the correct DRM device node.
       For example, if HDMI is on card1, change the path accordingly. */
    int fd = open("/dev/dri/card1", O_RDWR | O_CLOEXEC);
    if (fd < 0) {
        perror("open /dev/dri/card1");
        return EXIT_FAILURE;
    }

    /* Get DRM resources */
    drmModeRes *res = drmModeGetResources(fd);
    if (!res) {
        perror("drmModeGetResources");
        close(fd);
        return EXIT_FAILURE;
    }

    /* Find the first connected connector with available modes */
    drmModeConnector *conn = NULL;
    for (int i = 0; i < res->count_connectors; i++) {
        conn = drmModeGetConnector(fd, res->connectors[i]);
        if (conn && conn->connection == DRM_MODE_CONNECTED && conn->count_modes > 0)
            break;
        drmModeFreeConnector(conn);
        conn = NULL;
    }
    if (!conn) {
        fprintf(stderr, "No connected connector found\n");
        drmModeFreeResources(res);
        close(fd);
        return EXIT_FAILURE;
    }

    /* Choose a display mode – here we pick the first available mode */
    drmModeModeInfo mode = conn->modes[0];
    printf("Using mode: %s (%dx%d)\n", mode.name, mode.hdisplay, mode.vdisplay);

    /* Get the encoder and CRTC.
       For simplicity, we take the encoder's CRTC_id */
    drmModeEncoder *enc = drmModeGetEncoder(fd, conn->encoder_id);
    uint32_t crtc_id = 0;
    if (enc) {
        crtc_id = enc->crtc_id;
        drmModeFreeEncoder(enc);
    }
    if (!crtc_id) {
        fprintf(stderr, "No CRTC found\n");
        drmModeFreeConnector(conn);
        drmModeFreeResources(res);
        close(fd);
        return EXIT_FAILURE;
    }

    /* Create primary (background) buffer with the full screen dimensions.
       Here we fill it with a dummy dark gray color. */
    struct dumb_buf primary_buf;
    if (create_dumb_buffer(fd, mode.hdisplay, mode.vdisplay, &primary_buf) < 0) {
        fprintf(stderr, "Failed to create primary buffer\n");
        return EXIT_FAILURE;
    }
    memset(primary_buf.map, 0x20, primary_buf.size);

    /* Set the CRTC using the primary framebuffer */
    if (drmModeSetCrtc(fd, crtc_id, primary_buf.fb_id, 0, 0, &conn->connector_id, 1, &mode)) {
        perror("drmModeSetCrtc");
        return EXIT_FAILURE;
    }

    /* Create overlay buffer – for example, 100x100 pixels */
    int overlay_width = 100, overlay_height = 100;
    struct dumb_buf overlay_buf;
    if (create_dumb_buffer(fd, overlay_width, overlay_height, &overlay_buf) < 0) {
        fprintf(stderr, "Failed to create overlay buffer\n");
        return EXIT_FAILURE;
    }

    /* Clear overlay to transparent (0x00000000) */
    uint32_t *p = (uint32_t *)overlay_buf.map;
    for (int i = 0; i < overlay_width * overlay_height; i++)
        p[i] = 0x00000000;

    /* Draw a white cross in the center of the overlay buffer */
    int cross_thickness = 5;
    for (int y = 0; y < overlay_height; y++) {
        for (int x = 0; x < overlay_width; x++) {
            if ((y >= overlay_height/2 - cross_thickness/2 && y < overlay_height/2 + cross_thickness/2) ||
                (x >= overlay_width/2 - cross_thickness/2 && x < overlay_width/2 + cross_thickness/2)) {
                p[y * overlay_width + x] = 0xFFFFFFFF;
            }
        }
    }

    /* --- Set Up Atomic Mode Setting for the Overlay --- */
    /* Query available overlay planes */
    drmModePlaneRes *plane_res = drmModeGetPlaneResources(fd);
    if (!plane_res) {
        perror("drmModeGetPlaneResources");
        return EXIT_FAILURE;
    }

    drmModePlane *overlay_plane = NULL;
    for (uint32_t i = 0; i < plane_res->count_planes; i++) {
        drmModePlane *plane = drmModeGetPlane(fd, plane_res->planes[i]);
        /* Check if this plane can be used with our CRTC.
           (The check below is simplified; in production, verify against actual CRTC bitmask.) */
        if (plane && (plane->possible_crtcs & (1 << 0))) {
            overlay_plane = plane;
            break;
        }
        drmModeFreePlane(plane);
    }
    if (!overlay_plane) {
        fprintf(stderr, "No overlay plane found\n");
        drmModeFreePlaneResources(plane_res);
        return EXIT_FAILURE;
    }
    printf("Using overlay plane id: %u\n", overlay_plane->plane_id);

    /* Dynamically query the required property IDs for the overlay plane */
    uint32_t prop_fb_id   = get_property_id(fd, overlay_plane->plane_id, DRM_MODE_OBJECT_PLANE, "FB_ID");
    uint32_t prop_crtc_id = get_property_id(fd, overlay_plane->plane_id, DRM_MODE_OBJECT_PLANE, "CRTC_ID");
    uint32_t prop_src_x   = get_property_id(fd, overlay_plane->plane_id, DRM_MODE_OBJECT_PLANE, "SRC_X");
    uint32_t prop_src_y   = get_property_id(fd, overlay_plane->plane_id, DRM_MODE_OBJECT_PLANE, "SRC_Y");
    uint32_t prop_src_w   = get_property_id(fd, overlay_plane->plane_id, DRM_MODE_OBJECT_PLANE, "SRC_W");
    uint32_t prop_src_h   = get_property_id(fd, overlay_plane->plane_id, DRM_MODE_OBJECT_PLANE, "SRC_H");
    uint32_t prop_crtc_x  = get_property_id(fd, overlay_plane->plane_id, DRM_MODE_OBJECT_PLANE, "CRTC_X");
    uint32_t prop_crtc_y  = get_property_id(fd, overlay_plane->plane_id, DRM_MODE_OBJECT_PLANE, "CRTC_Y");
    uint32_t prop_crtc_w  = get_property_id(fd, overlay_plane->plane_id, DRM_MODE_OBJECT_PLANE, "CRTC_W");
    uint32_t prop_crtc_h  = get_property_id(fd, overlay_plane->plane_id, DRM_MODE_OBJECT_PLANE, "CRTC_H");

    if (!prop_fb_id || !prop_crtc_id || !prop_src_x || !prop_src_y ||
        !prop_src_w || !prop_src_h || !prop_crtc_x || !prop_crtc_y ||
        !prop_crtc_w || !prop_crtc_h) {
        fprintf(stderr, "Failed to get one or more property IDs\n");
        drmModeFreePlane(overlay_plane);
        drmModeFreePlaneResources(plane_res);
        return EXIT_FAILURE;
    }

    /* Allocate an atomic request */
    drmModeAtomicReq *req = drmModeAtomicAlloc();
    if (!req) {
        fprintf(stderr, "drmModeAtomicAlloc failed\n");
        drmModeFreePlane(overlay_plane);
        drmModeFreePlaneResources(plane_res);
        return EXIT_FAILURE;
    }

    int ret = 0;
    ret += drmModeAtomicAddProperty(req, overlay_plane->plane_id, prop_fb_id, overlay_buf.fb_id);
    ret += drmModeAtomicAddProperty(req, overlay_plane->plane_id, prop_crtc_id, crtc_id);
    ret += drmModeAtomicAddProperty(req, overlay_plane->plane_id, prop_src_x, 0);
    ret += drmModeAtomicAddProperty(req, overlay_plane->plane_id, prop_src_y, 0);
    ret += drmModeAtomicAddProperty(req, overlay_plane->plane_id, prop_src_w, overlay_width << 16);
    ret += drmModeAtomicAddProperty(req, overlay_plane->plane_id, prop_src_h, overlay_height << 16);

    /* Position the overlay at the center of the screen */
    int dst_x = (mode.hdisplay - overlay_width) / 2;
    int dst_y = (mode.vdisplay - overlay_height) / 2;
    ret += drmModeAtomicAddProperty(req, overlay_plane->plane_id, prop_crtc_x, dst_x);
    ret += drmModeAtomicAddProperty(req, overlay_plane->plane_id, prop_crtc_y, dst_y);
    ret += drmModeAtomicAddProperty(req, overlay_plane->plane_id, prop_crtc_w, overlay_width);
    ret += drmModeAtomicAddProperty(req, overlay_plane->plane_id, prop_crtc_h, overlay_height);
    if (ret < 0) {
        fprintf(stderr, "Failed to add atomic properties\n");
        drmModeAtomicFree(req);
        drmModeFreePlane(overlay_plane);
        drmModeFreePlaneResources(plane_res);
        return EXIT_FAILURE;
    }

    ret = drmModeAtomicCommit(fd, req, DRM_MODE_ATOMIC_NONBLOCK, NULL);
    if (ret < 0) {
        perror("drmModeAtomicCommit");
        drmModeAtomicFree(req);
        drmModeFreePlane(overlay_plane);
        drmModeFreePlaneResources(plane_res);
        return EXIT_FAILURE;
    }
    printf("Overlay applied. Press Enter to exit.\n");
    getchar();

    /* Cleanup */
    drmModeAtomicFree(req);
    drmModeFreePlane(overlay_plane);
    drmModeFreePlaneResources(plane_res);
    drmModeFreeConnector(conn);
    drmModeFreeResources(res);
    close(fd);
    return EXIT_SUCCESS;
}
