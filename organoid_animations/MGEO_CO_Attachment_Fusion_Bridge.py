"""MGEO -> cortical organoid fusion and polarized interneuron migration (V11.2 — attached MGEO, mesh-attached streams, dense distributed settling). Blender 4.x/5.x.
Run in Scripting > Open > Run Script. WARNING: clears current scene.
Illustrative tissue fusion/migration, not a physical or quantitative biological model.
Save as .blend after running. All organoids and neurons remain native editable objects.

EDITING GUIDE:
  1) Script top: change MGEO_COLOR, CO_COLOR, NEURON_COLOR, NUCLEUS_COLOR.
  2) Material Properties: each material is shared by its category of objects.
  3) SURFACE_SOMA_CENTER_OFFSET adjusts how closely surface-cell somata hug CO.
  4) CO_OPACITY changes visibility of internal cells.
  5) Outliner collections 02A / 02B separate surface and interior neurons.
  6) Changing script parameters requires rerunning in a NEW/unsaved scene;
     the script clears the scene, including manual edits. Save a .blend first.

"""
import bpy, math, random
from mathutils import Vector, noise

# ===================== USER CONTROLS =====================
# COLOR CONTROLS: RGB values range from 0.0 to 1.0.
# Change these three tuples, rerun the script, and the whole scene updates.
# Alternatively, after running, select an object > Material Properties > Base Color.
# The CO is transparent, so its apparent color also depends on CO_OPACITY.
MGEO_COLOR = (0.57, 0.16, 0.42)   # MGEO tissue: muted purple
CO_COLOR = (0.10, 0.54, 0.65)     # cortical tissue: cyan
NEURON_COLOR = (0.96, 0.22, 0.45) # migrating interneurons: bright rose
NUCLEUS_COLOR = (0.36, 0.08, 0.26) # nuclei: darker magenta

# ORGANOID GEOMETRY AND SURFACE (your previously approved settings).
FRAME_START, FRAME_CONTACT, FRAME_FUSED, FRAME_END = 1, 75, 190, 320
CO_RADIUS = 1.35
SMALL_MGEO_RATIO = 0.50
SURFACE_IRREGULARITY = 0.06
SHADER_BUMP_STRENGTH = 0.3
SEED = 21 # repeatable random movement; change for a new realization

# NEURON POPULATION AND STREAMS.
MIGRATING_NEURONS = 560
MIGRATION_STREAMS = 12
SURFACE_STREAM_FRACTION = 0.43 # 0 = all internal; 1 = all exterior
STREAM_WINDING = 1.35         # shared winding/turning within each stream
STREAM_FOLLOWING = 0.88       # conceptual cohesion control
SURFACE_LANE_WIDTH = 0.045    # angular spread around surface corridors
DEEP_LANE_WIDTH = 0.085       # angular spread around interior corridors
PATH_TURN_STRENGTH = 0.23    # reserved for future path refinement
SHOW_STREAM_GUIDES = False

# IMPORTANT: EXTERIOR SURFACE ATTACHMENT.
# This is the CENTER of the soma above the actual irregular tissue mesh,
# NOT the gap between the soma and the tissue. The soma has radius ~0.02–0.04.
# A center offset of 0.015 means the soma slightly overlaps/touches the tissue.
# Increase toward 0.035 for more separation; decrease toward 0.005 to embed more.
SURFACE_SOMA_CENTER_OFFSET = 0.008
# In Blender the actual CO surface is queried with mesh ray casts (not an
# idealized sphere), so the surface paths hug your custom irregular geometry.

# MIGRATION, INCHWORM MOVEMENT, AND FINAL POSITIONS.
INCHWORM_CYCLES = 9
SOMA_TRANSLOCATION_CYCLES = 4
LEADING_PROCESS_LENGTH = 0.115
TRAILING_PROCESS_LENGTH = 0.065
MIGRATION_START, MIGRATION_END = 80, 285
MGEO_FINAL_SIZE = 0.12
CO_OPACITY = 0.29            # 0 fully transparent; 1 opaque
CELL_RADIUS = 0.030
SETTLED_FRACTION = 1.0
LAUNCH_SPREAD = 155
TRAVEL_FRAMES_MIN, TRAVEL_FRAMES_MAX = 75, 160
CELL_WOBBLE = 0.30
FINAL_SURFACE_FRACTION = 0.52
SURFACE_TERMINAL_SPREAD = 0.52
INTERIOR_TERMINAL_RADIUS = (0.10, 0.93)
SETTLE_BY_FRAME = 309
FINAL_PROCESS_SCALE = 0.70
# FINAL DISTRIBUTION: every cell gets its own destination across CO, not just
# the distal hemisphere. Fibonacci-sphere directions give approximately even
# surface coverage, and cube-root radial sampling gives approximately uniform
# VOLUME density (rather than clustering in the center).
FINAL_SURFACE_JITTER = 0.10   # radians; stochastic scatter of evenly spaced targets
FINAL_INTERIOR_MIN_RADIUS = 0.06  # fraction of CO radius
# MGEO is an attached donor compartment, not a penetrating/merging volume.
# X-compression gives a soft "squished onto the CO" silhouette.
MGEO_CONTACT_X_COMPRESSION = 0.78  # applied AFTER contact, never during approach
MGEO_LATE_X_COMPRESSION = 0.62
# V11.2: bridge appears ONLY after contact, joining the two tissue boundaries.
BRIDGE_RADIUS_AT_FUSION = 0.20  # thickness of tissue neck at intermediate fusion
BRIDGE_RADIUS_FINAL = 0.105    # neck remains visible when MGEO is depleted
BRIDGE_EMERGENCE_FRAME = 88    # after first contact (frame 75)
BRIDGE_TISSUE_OVERLAP = 0.075 # slight overlap hides seams at the two surfaces
# Process morphology: change these without altering the tissue geometry.
SOMA_WIDTH = 0.026
SOMA_DEPTH = 0.021
SOMA_LENGTH = 0.039
# =========================================================

# -------------------------------------------------------
random.seed(SEED)
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete(use_global=False)
scene = bpy.context.scene
scene.frame_start, scene.frame_end = FRAME_START, FRAME_END
scene.render.engine = 'CYCLES'
scene.cycles.samples = 48
scene.render.resolution_x, scene.render.resolution_y = 1920, 1080
scene.render.resolution_percentage = 100
scene.render.film_transparent = True
scene.render.image_settings.file_format = 'PNG'
scene.render.filepath = '//MGEO_CO_migration_v11_2.png'
scene.view_settings.view_transform = 'AgX'
scene.world.color = (0.10, 0.10, 0.10)

def collection(name):
    c = bpy.data.collections.new(name)
    scene.collection.children.link(c)
    return c

def put(obj, coll):
    for c in list(obj.users_collection): c.objects.unlink(obj)
    coll.objects.link(obj)

TISSUE = collection('01 | Tissue - edit surfaces and materials')
NEURONS = collection('02 | Migrating MGE interneurons - editable morphologies')
SURFACE_CELLS = collection('02A | SURFACE migration and settled neurons')
DEEP_CELLS = collection('02B | INTERNAL migration and settled neurons')
STUDIO = collection('03 | Camera and lights')

def tissue_material(name, color, alpha=1.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    m.diffuse_color = (*color, alpha)
    nodes = m.node_tree.nodes
    p = nodes.get('Principled BSDF')
    p.inputs['Base Color'].default_value = (*color, 1)
    p.inputs['Roughness'].default_value = 0.54
    p.inputs['Subsurface Weight'].default_value = 0.23
    p.inputs['Coat Weight'].default_value = 0.08
    tex = nodes.new('ShaderNodeTexNoise')
    tex.inputs['Scale'].default_value = 55
    tex.inputs['Detail'].default_value = 2
    bump = nodes.new('ShaderNodeBump')
    bump.inputs['Strength'].default_value = SHADER_BUMP_STRENGTH
    bump.inputs['Distance'].default_value = 0.012
    m.node_tree.links.new(tex.outputs['Fac'], bump.inputs['Height'])
    m.node_tree.links.new(bump.outputs['Normal'], p.inputs['Normal'])
    if alpha < 1:
        # True transparency in Cycles; works without relying on Blender-version blend modes.
        trans = nodes.new('ShaderNodeBsdfTransparent')
        mix = nodes.new('ShaderNodeMixShader')
        output = nodes.get('Material Output')
        m.node_tree.links.new(p.outputs['BSDF'], mix.inputs[1])
        m.node_tree.links.new(trans.outputs['BSDF'], mix.inputs[2])
        mix.inputs[0].default_value = 1-alpha
        m.node_tree.links.new(mix.outputs[0], output.inputs['Surface'])
    return m

# These are shared material datablocks: editing one updates all objects using it.
mge_mat = tissue_material('MGEO | tissue color', MGEO_COLOR)
co_mat = tissue_material('CO | tissue color + transparency', CO_COLOR, CO_OPACITY)
cell_mat = tissue_material('MGE interneurons | soma + processes', NEURON_COLOR)
nucleus_mat = tissue_material('MGE interneurons | nuclei', NUCLEUS_COLOR)

def organoid(name, radius, material, offset):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=112, ring_count=72, radius=radius)
    ob = bpy.context.object
    ob.name = name
    put(ob, TISSUE)
    ob.data.materials.append(material)
    for v in ob.data.vertices:
        u = v.co.normalized()
        p = u * 2.1 + Vector((offset*3.1,offset*1.7,offset*2.4))
        irregular = noise.noise(p*1.25) + 0.27*noise.noise(p*3.2)
        v.co = u * radius * (1 + SURFACE_IRREGULARITY*irregular)
    for poly in ob.data.polygons: poly.use_smooth = True
    return ob

def animate(obj, path, values):
    for frame, value in values:
        setattr(obj, path, value)
        obj.keyframe_insert(data_path=path, frame=frame)

co = organoid('CO | main cortical organoid', CO_RADIUS, co_mat, 3)

# EVALUATED-MESH SURFACE ATTACHMENT
# Query evaluated geometry so modifiers you add to the CO can affect the
# sampled surface. The CO itself remains stationary. This is done once here;
# re-running the script after modifying CO geometry recomputes the attachment.
from mathutils.bvhtree import BVHTree
bpy.context.view_layer.update()
_depsgraph = bpy.context.evaluated_depsgraph_get()
# Build a BVH directly from the evaluated Blender object (Blender 4.x/5.x).
# BVHTree.FromMesh does not exist in Blender's Python API.
_co_bvh = BVHTree.FromObject(co, _depsgraph)

def attach_to_co_surface(world_position):
    """Project a point radially onto the actual evaluated CO mesh.

    Uses a ray launched OUTSIDE the tissue and pointed inward, which avoids
    selecting a back-facing intersection. Offset is soma-CENTER to surface.
    This projection applies to the soma trajectory and its resting destination.
    """
    direction = (Vector(world_position) - co.location).normalized()
    if direction.length < 1e-8: direction = Vector((1,0,0))
    origin_local = direction * (CO_RADIUS * 3.0)
    hit, normal, face_index, distance = _co_bvh.ray_cast(origin_local, -direction)
    if hit is None:
        hit, normal, face_index, distance = _co_bvh.find_nearest(direction*CO_RADIUS)
    if hit is None:
        return co.location + direction*(CO_RADIUS+SURFACE_SOMA_CENTER_OFFSET)
    return co.matrix_world @ (hit + normal.normalized()*SURFACE_SOMA_CENTER_OFFSET)

mge = organoid('MGEO | attached donor - no tissue penetration', CO_RADIUS*SMALL_MGEO_RATIO, mge_mat, 4)
# MGEO stays entirely LEFT of the CO. As it becomes smaller, the donor tissue
# stays juxtaposed to the cortex instead of translating into the CO volume.
# The apparent depletion is illustrative: migration does not physically
# consume an MGEO in a measured or mechanistically modeled manner.
co.location = (0.40,0,0)
bpy.context.view_layer.update()  # refresh CO world matrix used by surface projection
# During the approach the MGEO retains its FULL original dimensions.
# In V11.1 it was already compressed by the contact frame; this is corrected.
# Its RIGHT boundary first meets the LEFT boundary of the CO at FRAME_CONTACT.
contact_x = co.location.x - CO_RADIUS - CO_RADIUS*SMALL_MGEO_RATIO
start_x = contact_x - 1.15
late_radius = CO_RADIUS*SMALL_MGEO_RATIO*MGEO_FINAL_SIZE*MGEO_LATE_X_COMPRESSION
late_x = co.location.x - CO_RADIUS - late_radius + 0.008

# The donor begins shrinking/compressing only AFTER it has touched the CO.
# At every later keyframe its right edge stays adjacent to the cortical surface.
post_contact_frame = FRAME_CONTACT + 24
compressed_x_radius = CO_RADIUS*SMALL_MGEO_RATIO*MGEO_CONTACT_X_COMPRESSION
compressed_x = co.location.x - CO_RADIUS - compressed_x_radius + 0.008
mid_scale = (0.53, 0.60, 0.60)
mid_x_radius = CO_RADIUS*SMALL_MGEO_RATIO*mid_scale[0]
mid_x = co.location.x - CO_RADIUS - mid_x_radius + 0.008
animate(mge, 'location', [
    (FRAME_START,(start_x,0,0)),
    (FRAME_CONTACT,(contact_x,0,0)),
    (post_contact_frame,(compressed_x,0,0)),
    (FRAME_FUSED,(mid_x,0,0)),
    (FRAME_END,(late_x,0,0)),
])
animate(mge, 'scale', [
    (FRAME_START,(1,1,1)),
    (FRAME_CONTACT,(1,1,1)),  # no shrinking while approaching!
    (post_contact_frame,(MGEO_CONTACT_X_COMPRESSION,1,1)),
    (FRAME_FUSED,mid_scale),
    (FRAME_END,(MGEO_FINAL_SIZE*MGEO_LATE_X_COMPRESSION,MGEO_FINAL_SIZE,MGEO_FINAL_SIZE)),
])

# A short, visible tissue bridge forms between the donor and cortex AFTER
# first contact. It is a SEPARATE, EDITABLE object, not an MGEO mesh that
# enters or fills the cortical volume. Slight boundary overlap hides seams.
# You can select 'FUSION BRIDGE' in the Outliner and adjust its material,
# dimensions, or keyframes without modifying either organoid.
bridge_mat = tissue_material('MGEO-CO | fusion neck tissue',
                             tuple((a+b)*0.5 for a,b in zip(MGEO_COLOR,CO_COLOR)))
bpy.ops.mesh.primitive_uv_sphere_add(segments=48, ring_count=32, radius=1)
bridge = bpy.context.object
bridge.name = 'FUSION BRIDGE | visible tissue neck - editable'
put(bridge,TISSUE)
bridge.data.materials.append(bridge_mat)
for face in bridge.data.polygons: face.use_smooth=True

# Keyframes are calculated using the actual animated donor position and scale.
# The neck touches the two facing boundaries without extending into the CO.
# Tiny overlaps at the interface are intentional, to visually join surfaces.
bridge_keyframes = [
    (FRAME_START, 0.0),
    (FRAME_CONTACT, 0.0),
    (BRIDGE_EMERGENCE_FRAME, 0.055),
    (post_contact_frame, 0.14),
    (FRAME_FUSED, BRIDGE_RADIUS_AT_FUSION),
    (FRAME_END, BRIDGE_RADIUS_FINAL),
]
for frame, thickness in bridge_keyframes:
    scene.frame_set(frame)
    bpy.context.view_layer.update()
    donor_right = (mge.location.x +
                   CO_RADIUS*SMALL_MGEO_RATIO*mge.scale.x)
    cortex_left = co.location.x - CO_RADIUS
    # Bridge midpoint is between the two nearest tissue boundaries.
    center_x = 0.5*(donor_right+cortex_left)
    half_span = 0.5*abs(cortex_left-donor_right)+BRIDGE_TISSUE_OVERLAP
    bridge.location = (center_x,0,0)
    # An ellipsoidal neck has enough axial span to connect both compartments.
    # Zero radius makes it invisible until contact; the scale remains editable.
    bridge.scale = (max(0.001,half_span), max(0.0001,thickness),
                    max(0.0001,thickness))
    bridge.keyframe_insert(data_path='location',frame=frame)
    bridge.keyframe_insert(data_path='scale',frame=frame)

# IMPORTANT: the fusion neck is only a LOCAL attachment interface. The
# donor MGEO remains outside the CO; migrating NEURONS populate the cortex.
# This is a schematic of tissue attachment/fusion, not a tissue simulation.

# Migrating interneurons are polarized: a thin leading process extends first,
# followed by saltatory nuclear/somal translocation and a short trailing process.
# Cells occupy several shared migratory streams, with individual variability.
# Stylized tangential migration; NOT cell tracking or a measured biological model.
rng = random.Random(SEED+200)
# Precompute stratified terminal locations. Assign directions independently
# of migratory stream: streams originate in MGEO, but destinations cover CO.
GOLDEN_ANGLE = math.pi*(3.0-math.sqrt(5.0))
def evenly_spaced_direction(index, count, jitter_seed):
    rr = random.Random(jitter_seed)
    z = 1.0-2.0*(index+0.5)/count
    phi = index*GOLDEN_ANGLE + rr.uniform(-FINAL_SURFACE_JITTER, FINAL_SURFACE_JITTER)
    radial = math.sqrt(max(0.0,1.0-z*z))
    d = Vector((z,radial*math.cos(phi),radial*math.sin(phi)))
    return (d+Vector((rr.gauss(0,0.025),rr.gauss(0,0.025),rr.gauss(0,0.025)))).normalized()

# Shuffle the final destinations so nearby cells in a stream disperse rather
# than arriving at neighboring locations in a fixed order.
final_indices=list(range(MIGRATING_NEURONS))
rng.shuffle(final_indices)


def make_curve(name, points, radius, mat, parent, target_collection=None):
    curve = bpy.data.curves.new(name, 'CURVE')
    curve.dimensions = '3D'
    curve.resolution_u = 12
    curve.bevel_depth = radius
    curve.bevel_resolution = 3
    spl = curve.splines.new('BEZIER')
    spl.bezier_points.add(len(points)-1)
    for bp, xyz in zip(spl.bezier_points, points):
        bp.co = xyz
        bp.handle_left_type = 'AUTO'
        bp.handle_right_type = 'AUTO'
    ob = bpy.data.objects.new(name, curve)
    (target_collection or NEURONS).objects.link(ob)
    curve.materials.append(mat)
    ob.parent = parent
    return ob

def create_soma(name, parent, target_collection):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=12, ring_count=8, radius=1)
    ob = bpy.context.object
    ob.name = name
    put(ob, target_collection)
    ob.parent = parent
    ob.location = (0,0,0)
    ob.scale = (SOMA_WIDTH, SOMA_DEPTH, SOMA_LENGTH)  # polar axis is local Z
    ob.data.materials.append(cell_mat)
    for face in ob.data.polygons: face.use_smooth = True
    return ob

# Migratory streams: curving paths around the surface AND through the volume.
# Saltatory motion: process reaches forward while soma remains paused; then
# soma/nucleus rapidly translocate and the leading process retracts.
streams = []
for j in range(MIGRATION_STREAMS):
    theta = 2*math.pi*j/MIGRATION_STREAMS
    streams.append((math.cos(theta), math.sin(theta)))

def smoothstep(t):
    t=max(0.0,min(1.0,t))
    return t*t*(3-2*t)

def catmull(points, t):
    t=max(0.0,min(1.0,t))*(len(points)-1)
    k=min(len(points)-2,int(t))
    u=t-k
    p0=points[max(0,k-1)]; p1=points[k]
    p2=points[k+1]; p3=points[min(len(points)-1,k+2)]
    return 0.5*((2*p1)+(-p0+p2)*u+(2*p0-5*p1+4*p2-p3)*u*u+(-p0+3*p1-3*p2+p3)*u*u*u)

def make_route(origin, stream, outside, lane_shift, cell_seed):
    """Shared 3D curved corridor; outside routes stay outside CO, deep routes enter CO.

    Every route begins at the MGEO-facing pole and progresses across the interface.
    Stream-specific harmonics produce persistent bends and turns; correlated small
    offsets preserve stream cohesion without making trajectories identical.
    """
    rr = random.Random(cell_seed)
    cy, cz = streams[stream]
    base = math.atan2(cz, cy)
    # Persistent, shared stream shape (not randomized independently per neuron).
    phase = 0.7 * stream
    lane = SURFACE_LANE_WIDTH if outside else DEEP_LANE_WIDTH
    dtheta = rr.gauss(0, lane) + 0.10 * lane_shift.y
    twist = rr.uniform(-0.055, 0.055)
    points = [origin]
    # Depart from the MGE surface and cross the MGEO/CO junction first.
    contact = co.location + Vector((-CO_RADIUS * 0.985, 0, 0))
    points.append(origin.lerp(contact, 0.52) + Vector((0,0.055*cy,0.055*cz)))
    points.append(contact + Vector((0,0.08*cy,0.08*cz)))
    for k in range(1,25):
        u=k/24
        # Polar angle carries cells from left interface toward different CO locations.
        polar = math.pi - (1.96 + 0.65*(stream % 3)/2)*u
        # Strong common stream meanders, including two reversals in turning direction.
        turn = (0.38*math.sin(2.7*math.pi*u+phase)-0.38*math.sin(phase)
                +0.19*math.sin(5.3*math.pi*u+phase*0.4)*math.sin(math.pi*u))
        theta = base + STREAM_WINDING*turn + dtheta + twist*math.sin(5*math.pi*u)
        polar += 0.11*math.sin(3.6*math.pi*u+phase)*math.sin(math.pi*u)
        if outside:
            # Constant radius outside surface, never cuts across tissue volume.
            r = CO_RADIUS + 0.012*math.sin(4*math.pi*u+phase)
        else:
            # Enter below the surface and wind through internal tissue.
            r = CO_RADIUS*(0.95-0.37*math.sin(0.5*math.pi*u))
        point = co.location + Vector((r*math.cos(polar),
                r*math.sin(polar)*math.cos(theta),
                r*math.sin(polar)*math.sin(theta)))
        if outside:
            point = attach_to_co_surface(point)
        points.append(point)
    return points

def animate_visibility(root, launch):
    for f,v in [(FRAME_START,0.001),(launch-1,0.001),(launch,1.0)]:
        root.scale=(v,)*3
        root.keyframe_insert(data_path='scale',frame=f)

# Independent departures, variable speeds, and explicit stop-and-settle behavior.
# Blender 4.4+/5.x compatible: never access legacy Action.fcurves.
for i in range(MIGRATING_NEURONS):
    outside=rng.random()<SURFACE_STREAM_FRACTION
    # Multiple stable streams, each populated by a cohort of cells.
    stream=(i // 4) % MIGRATION_STREAMS
    target_collection = SURFACE_CELLS if outside else DEEP_CELLS
    launch=MIGRATION_START+rng.randint(0,LAUNCH_SPREAD)
    launch=min(launch,FRAME_END-TRAVEL_FRAMES_MIN-5)
    duration=rng.randint(TRAVEL_FRAMES_MIN,TRAVEL_FRAMES_MAX)
    arrive=min(SETTLE_BY_FRAME-8,launch+duration)
    scene.frame_set(launch)
    origin=mge.matrix_world.translation.copy()
    # Cells emerge at a visible MGEO pole facing the cortical compartment,
    # rather than materializing inside the cortical organoid.
    # Source radius follows the ACTUAL animated MGEO scale at launch.
    # All neurons start near its CO-facing hemisphere, not inside the cortex.
    mge_radius=CO_RADIUS*SMALL_MGEO_RATIO*float(mge.scale.y)
    mge_x_radius=CO_RADIUS*SMALL_MGEO_RATIO*float(mge.scale.x)
    theta=2*math.pi*stream/MIGRATION_STREAMS
    shift=Vector((0,rng.gauss(0,0.035),rng.gauss(0,0.035)))
    origin=origin+Vector((0.83*mge_x_radius,0.27*mge_radius*math.cos(theta),
                          0.27*mge_radius*math.sin(theta)))+shift
    route=make_route(origin,stream,outside,shift,SEED*10000+i)
    root=bpy.data.objects.new(f'Cell {i+1:03d} | {"SURFACE" if outside else "INTERIOR"} | stream {stream+1}',None)
    target_collection.objects.link(root)
    root.empty_display_type='PLAIN_AXES'; root.empty_display_size=0.035
    soma=create_soma(f'Cell {i+1:03d} | soma',root,target_collection)
    bpy.ops.mesh.primitive_uv_sphere_add(segments=12,ring_count=8,radius=1)
    nucleus=bpy.context.object
    nucleus.name=f'Cell {i+1:03d} | nucleus'
    put(nucleus,target_collection); nucleus.parent=root
    nucleus.scale=(0.013,0.013,0.019)
    nucleus.data.materials.append(nucleus_mat)
    for face in nucleus.data.polygons: face.use_smooth=True
    leading=make_curve(f'Cell {i+1:03d} | leading process',
        [(0,0,0.022),(0.006,0,0.065),(0.014,0.008,LEADING_PROCESS_LENGTH)],0.0035,cell_mat,root,target_collection)
    branch=make_curve(f'Cell {i+1:03d} | exploratory bifurcation',
        [(0.006,0,0.065),(-0.012,0.016,0.090),(-0.022,0.022,0.110)],0.002,cell_mat,root,target_collection)
    trailing=make_curve(f'Cell {i+1:03d} | trailing process',
        [(0,0,-0.018),(0.006,0,-0.044),(0.010,0,-TRAILING_PROCESS_LENGTH)],0.0023,cell_mat,root,target_collection)
    animate_visibility(root,launch)
    cycles=rng.randint(max(4,INCHWORM_CYCLES-3),INCHWORM_CYCLES+4)
    # Unequal cycle lengths; pause / extension / nucleokinesis / somal jump.
    weights=[rng.uniform(0.55,1.65) for _ in range(cycles)]
    cumulative=[0]
    for w in weights: cumulative.append(cumulative[-1]+w)
    cumulative=[v/cumulative[-1] for v in cumulative]
    settled = True  # all neurons have a defined terminal location; arrival remains asynchronous
    # Individually assigned final locations across the FULL CO sphere.
    # Surface: stratified spherical coverage; soma centered close to actual mesh.
    # Interior: uniform-volume radial sampling, including the central volume.
    direction=evenly_spaced_direction(final_indices[i],MIGRATING_NEURONS,SEED*701+i)
    if outside:
        terminal_pos=attach_to_co_surface(co.location+direction*CO_RADIUS*1.4)
    else:
        rr=random.Random(SEED*911+i)
        radius_fraction=(FINAL_INTERIOR_MIN_RADIUS**3 +
                         (0.94**3-FINAL_INTERIOR_MIN_RADIUS**3)*rr.random())**(1.0/3.0)
        terminal_pos=co.location+direction*(CO_RADIUS*radius_fraction)
    # Each cell exits the stream at its own position rather than finishing at the same tip.
    end_progress=rng.uniform(0.30,0.93)
    def cell_position(progress):
        t=max(0.0,min(1.0,progress/end_progress))
        corridor=catmull(route,min(1.0,progress))
        # A smooth branch off the shared stream into a stable terminal position.
        blend=smoothstep((t-0.38)/0.62)
        position = corridor.lerp(terminal_pos,blend)
        # Critical: interpolate in 3D, then reproject to the REAL tissue mesh.
        # Without this step, Catmull-Rom and branching create floating arcs
        # or straight chords that cut through the tissue between control points.
        # At the beginning the cell is still leaving MGEO, so don't project
        # until it has entered the cortical surface portion of its trajectory.
        if outside and t > 0.18:
            position = attach_to_co_surface(position)
        return position
    last_frame=-1
    for c in range(cycles):
        f0=launch+round((arrive-launch)*cumulative[c])
        f1=launch+round((arrive-launch)*cumulative[c+1])
        span=max(5,f1-f0)
        # Each cell has its own variable timing of exploratory extension and soma jump.
        reach_at=rng.uniform(0.30,0.56)
        jump_at=rng.uniform(0.56,0.79)
        steps=[(0.0,0.0,0.0),(reach_at,0.0,1.0),
               (jump_at,0.12,1.0),(min(0.96,jump_at+0.13),0.87,0.38),
               (1.0,1.0,0.22)]
        yaw=rng.uniform(-CELL_WOBBLE,CELL_WOBBLE)
        pitch=rng.uniform(-CELL_WOBBLE,CELL_WOBBLE)
        for local,jump,reach in steps:
            frame=f0+round(span*local)
            if frame<=last_frame: continue
            last_frame=frame
            progress=end_progress*(c+jump)/cycles
            pos=cell_position(progress)
            tangent=cell_position(min(end_progress,progress+0.006))-cell_position(max(0,progress-0.006))
            root.location=pos
            if tangent.length>1e-6:
                root.rotation_euler=tangent.to_track_quat('Z','Y').to_euler()
                root.rotation_euler.rotate_axis('Z',yaw*(0.4+reach))
                root.rotation_euler.rotate_axis('X',pitch*(0.3+reach))
            root.keyframe_insert(data_path='location',frame=frame)
            root.keyframe_insert(data_path='rotation_euler',frame=frame)
            leading.scale=(1,1,0.70+1.05*reach-0.40*jump)
            branch.scale=(1,1,0.65+0.65*reach-0.22*jump)
            branch.rotation_euler=(rng.uniform(-0.23,0.23),rng.uniform(-0.32,0.32),rng.uniform(-0.4,0.4))
            trailing.scale=(1,1,1.0-0.23*reach+0.28*jump)
            soma.scale=(SOMA_WIDTH,SOMA_DEPTH,SOMA_LENGTH*(1+0.24*jump*(1-jump)*4))
            nucleus.location.z=0.024*reach*(1-jump)
            for ob in (leading,branch,trailing,soma): ob.keyframe_insert(data_path='scale',frame=frame)
            branch.keyframe_insert(data_path='rotation_euler',frame=frame)
            nucleus.keyframe_insert(data_path='location',frame=frame)
    # Resting cells remain visibly dispersed after fusion; processes relax.
    if settled:
        for frame in (min(FRAME_END-3,arrive+5),FRAME_END):
            root.location=terminal_pos
            root.keyframe_insert(data_path='location',frame=frame)
            leading.scale=(1,1,FINAL_PROCESS_SCALE); trailing.scale=(1,1,FINAL_PROCESS_SCALE)
            branch.scale=(1,1,FINAL_PROCESS_SCALE*0.8)
            branch.keyframe_insert(data_path='scale',frame=frame)
            for ob in (leading,trailing): ob.keyframe_insert(data_path='scale',frame=frame)
    else:
        # Late arrivals retain their last pose without synchronizing endpoints.
        root.keyframe_insert(data_path='location',frame=FRAME_END)

# Studio camera and lighting
def aim(obj, point):
    obj.rotation_euler = (Vector(point)-obj.location).to_track_quat('-Z','Y').to_euler()

bpy.ops.object.camera_add(location=(0,-9.5,3.0))
cam = bpy.context.object
cam.name = 'CAMERA | orthographic - editable'
put(cam, STUDIO)
aim(cam,(-0.25,0,0))
cam.data.type = 'ORTHO'
cam.data.ortho_scale = 5.7
scene.camera = cam

def light(name, pos, power, size):
    bpy.ops.object.light_add(type='AREA',location=pos)
    obj=bpy.context.object
    obj.name=name
    put(obj,STUDIO)
    obj.data.energy=power
    obj.data.shape='DISK'
    obj.data.size=size
    aim(obj,(0,0,0))

light('Key softbox',(-4,-5,6),1050,7)
light('Fill softbox',(4,-3,2),750,7)
light('Rim softbox',(0,4,5),1100,7)
for label,frame in [('SEPARATE',FRAME_START),('CONTACT',FRAME_CONTACT),
                    ('FUSION',FRAME_FUSED),('MIGRATED',FRAME_END)]:
    scene.timeline_markers.new(label,frame=frame)
scene.frame_set(FRAME_START)
print(f'MGEO-CO V11.2 ready: {MIGRATING_NEURONS} cells; surface neurons projected onto actual CO mesh.')
