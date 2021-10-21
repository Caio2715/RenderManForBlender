from .rman_translator import RmanTranslator
from ..rman_sg_nodes.rman_sg_mesh import RmanSgMesh
from ..rfb_utils import object_utils
from ..rfb_utils import string_utils
from ..rfb_utils import property_utils
from ..rfb_utils import scenegraph_utils
from ..rfb_logger import rfb_log

import bpy
import math
import numpy as np

def _get_mats_faces_(nverts, material_ids):

    mats = {}
    for face_id, num_verts in enumerate(nverts):
        mat_id = material_ids[face_id]
        if mat_id not in mats:
            mats[mat_id] = []
        mats[mat_id].append(face_id)
    return mats

def _is_multi_material_(ob, mesh):
    if type(mesh) != bpy.types.Mesh or len(ob.data.materials) < 2 \
            or len(mesh.polygons) == 0:
        return False
    first_mat = mesh.polygons[0].material_index
    for p in mesh.polygons:
        if p.material_index != first_mat:
            return True
    return False

# requires facevertex interpolation
def _get_mesh_uv_(mesh, name=""):
    uvs = []
    if not name:
        uv_loop_layer = mesh.uv_layers.active
    else:
        # assuming uv loop layers and uv textures share identical indices
        #idx = mesh.uv_textures.keys().index(name)
        #uv_loop_layer = mesh.uv_layers[idx]
        uv_loop_layer = mesh.uv_layers.get(name, None)

    if uv_loop_layer is None:
        return None

    uv_count = len(uv_loop_layer.data)
    fastuvs = np.zeros(uv_count * 2)
    uv_loop_layer.data.foreach_get("uv", fastuvs)
    fastuvs = fastuvs.reshape(uv_count, 2)    
    uvs = fastuvs.tolist()

    return uvs

def _get_mesh_vcol_(mesh, name=""):
    vcol_layer = mesh.vertex_colors[name] if name != "" \
        else mesh.vertex_colors.active

    if vcol_layer is None:
        return None

    vcol_count = len(vcol_layer.data)
    fastvcols = np.zeros(vcol_count * 4)
    vcol_layer.data.foreach_get("color", fastvcols)
    fastvcols = np.reshape(fastvcols, (vcol_count, 4))
    pre_cols = fastvcols.tolist()     
    
    cols = [ [c[0], c[1], c[2]] for c in pre_cols ]

    return cols    

def _get_mesh_vattr_(mesh, name=""):
    if not name in mesh.attributes and mesh != "":
        rfb_log().error("Cannot find color attribute ")
        return None
    vattr_layer = mesh.attributes[name] if name != "" \
        else mesh.attributes.active

    if vattr_layer is None:
        return None

    vcol_count = len(vattr_layer.data)
    fastvattrs = np.zeros(vcol_count * 4)
    vattr_layer.data.foreach_get("color", fastvattrs)
    fastvattrs = np.reshape(fastvattrs, (vcol_count, 4))
    pre_cols = fastvattrs.tolist()     
    
    attrs = [ [a[0], a[1], a[2]] for a in pre_cols ]

    return attrs 

def _get_mesh_vgroup_(ob, mesh, name=""):
    vgroup = ob.vertex_groups[name] if name != "" else ob.vertex_groups.active
    weights = []

    if vgroup is None:
        return None

    for v in mesh.vertices:
        if len(v.groups) == 0:
            weights.append(0.0)
        else:
            weights.extend([g.weight for g in v.groups
                            if g.group == vgroup.index])

    return weights

def _get_material_ids(ob, geo):
        
    material_ids = string_utils.convert_val([p.material_index for p in geo.polygons])
    return material_ids

def _export_reference_pose(ob, rm, rixparams, vertex_detail):
    rman__Pref = []
    rman__WPref = []
    rman__Nref = []
    rman__WNref = []
    for rp in rm.reference_pose:
        if rp.has_Pref:
            rman__Pref.append( rp.rman__Pref)
        if rp.has_WPref:
            rman__WPref.append( rp.rman__WPref)
        if rp.has_Nref:
            rman__Nref.append( rp.rman__Nref)
        if rp.has_WPref:
            rman__WNref.append( rp.rman__WNref)

    if rman__Pref:
        if len(rman__Pref) == vertex_detail:
            rixparams.SetPointDetail('__Pref', rman__Pref, 'vertex')
        else:
            rfb_log().error("Number of Pref primvars do not match. Please re-freeze the reference position.")

    if rman__WPref:
        if len(rman__WPref) == vertex_detail:
            rixparams.SetPointDetail('__WPref', rman__WPref, 'vertex')
        else:
            rfb_log().error("Number of WPref primvars do not match. Please re-freeze the reference position.")
                
    if rman__Nref:
        if len(rman__Nref) == vertex_detail:
            rixparams.SetNormalDetail('__Nref', rman__Nref, 'vertex')
        else:
            rfb_log().error("Number of Nref primvars do not match. Please re-freeze the reference position.")
        
    if rman__WNref:
        if len(rman__WNref) == vertex_detail:
            rixparams.SetNormalDetail('__WNref', rman__WNref, 'vertex')
        else:
            rfb_log().error("Number of WNref primvars do not match. Please re-freeze the reference position.")
        
    '''
    if rman__Pref:
        rixparams.SetPointDetail('__Pref', rman__Pref, 'vertex')
    if rman__WPref:
        rixparams.SetPointDetail('__WPref', rman__WPref, 'vertex')
    if rman__Nref:
        rixparams.SetNormalDetail('__Nref', rman__Nref, 'vertex')
    if rman__WNref:
        rixparams.SetNormalDetail('__WNref', rman__WNref, 'vertex')
    '''

def _get_primvars_(ob, rman_sg_mesh, geo, rixparams):
    #rm = ob.data.renderman
    # Stange problem here : ob seems to not be in sync with the scene
    # when a geometry node is active...
    rm = ob.original.data.renderman

    vertex_detail = rman_sg_mesh.npoints 
    facevarying_detail = rman_sg_mesh.nverts 

    if rm.export_default_uv:
        uvs = _get_mesh_uv_(geo)
        if uvs and len(uvs) > 0:
            detail = "facevarying" if facevarying_detail == len(uvs) else "vertex"
            rixparams.SetFloatArrayDetail("st", uvs, 2, detail)

            # also export the tangent and bitangent vectors
            try:
                geo.calc_tangents(uvmap=geo.uv_layers.active.name)         
                loops = len(geo.loops)
                fasttangent = np.zeros(loops*3, dtype=np.float32)
                geo.loops.foreach_get('tangent', fasttangent)
                fasttangent = np.reshape(fasttangent, (loops, 3))
                tangents = fasttangent.tolist()    

                fastbitangent = np.zeros(loops*3, dtype=np.float32)
                geo.loops.foreach_get('bitangent', fastbitangent)
                bitangent = fastbitangent.tolist()      
                geo.free_tangents()    

                rixparams.SetVectorDetail('Tn', tangents, 'facevarying')
                rixparams.SetVectorDetail('Bn', bitangent, 'facevarying')    
            except RuntimeError as err:
                rfb_log().debug("Can't export tangent vectors: %s" % str(err))          

    if rm.export_default_vcol:
        vcols = _get_mesh_vcol_(geo)
        if vcols and len(vcols) > 0:
            detail = "facevarying" if facevarying_detail == len(vcols) else "vertex"
            rixparams.SetColorDetail("Cs", vcols, detail)

    # reference pose
    if hasattr(rm, 'reference_pose'):
        _export_reference_pose(ob, rm, rixparams, vertex_detail)
    
    # custom prim vars
    for p in rm.prim_vars:
        if p.data_source == 'VERTEX_COLOR':
            vcols = _get_mesh_vcol_(geo, p.data_name)
            
            if vcols and len(vcols) > 0:
                detail = "facevarying" if facevarying_detail == len(vcols) else "vertex"
                rixparams.SetColorDetail(p.name, vcols, detail)
            
        elif p.data_source == 'UV_TEXTURE':
            uvs = _get_mesh_uv_(geo, p.data_name)
            if uvs and len(uvs) > 0:
                detail = "facevarying" if facevarying_detail == len(uvs) else "vertex"
                rixparams.SetFloatArrayDetail(p.name, uvs, 2, detail)

        elif p.data_source == 'VERTEX_GROUP':
            weights = _get_mesh_vgroup_(ob, geo, p.data_name)
            if weights and len(weights) > 0:
                detail = "facevarying" if facevarying_detail == len(weights) else "vertex"
                rixparams.SetFloatDetail(p.name, weights, detail)
        elif p.data_source == 'VERTEX_ATTR_COLOR':
            vattr = _get_mesh_vattr_(geo, p.data_name)            
            if vattr and len(vattr) > 0:
                detail = "facevarying" if facevarying_detail == len(vattr) else "vertex"
                rixparams.SetColorDetail(p.data_name, vattr, detail)

    rm_scene = rman_sg_mesh.rman_scene.bl_scene.renderman
    for prop_name, meta in rm.prop_meta.items():
        if 'primvar' not in meta:
            continue

        val = getattr(rm, prop_name)
        if not val:
            continue

        if 'inheritable' in meta:
            if float(val) == meta['inherit_true_value']:
                if hasattr(rm_scene, prop_name):
                    val = getattr(rm_scene, prop_name)

        ri_name = meta['primvar']
        is_array = False
        array_len = -1
        if 'arraySize' in meta:
            is_array = True
            array_len = meta['arraySize']
        param_type = meta['renderman_type']
        property_utils.set_rix_param(rixparams, param_type, ri_name, val, is_reference=False, is_array=is_array, array_len=array_len, node=rm)

class RmanMeshTranslator(RmanTranslator):

    def __init__(self, rman_scene):
        super().__init__(rman_scene)
        self.bl_type = 'MESH' 

    def _get_subd_tags_(self, ob, mesh, primvar):
        creases = []

        # only do creases 1 edge at a time for now,
        # detecting chains might be tricky..
        for e in mesh.edges:
            if e.crease > 0.0:
                creases.append((e.vertices[0], e.vertices[1],
                                e.crease * e.crease * 10))
                # squared, to match blender appareance better
                #: range 0 - 10 (infinitely sharp)

        tags = ['interpolateboundary', 'facevaryinginterpolateboundary']
        nargs = [1, 0, 0, 1, 0, 0]
        intargs = [ int(ob.data.renderman.rman_subdivInterp),
                int(ob.data.renderman.rman_subdivFacevaryingInterp)]
        floatargs = []
        stringargs = []   

        if len(creases) > 0:
            for c in creases:
                tags.append('crease')
                nargs.extend([2, 1, 0])
                intargs.extend([c[0], c[1]])
                floatargs.append(c[2])           

        primvar.SetStringArray(self.rman_scene.rman.Tokens.Rix.k_Ri_subdivtags, tags, len(tags))
        primvar.SetIntegerArray(self.rman_scene.rman.Tokens.Rix.k_Ri_subdivtagnargs, nargs, len(nargs))
        primvar.SetIntegerArray(self.rman_scene.rman.Tokens.Rix.k_Ri_subdivtagintargs, intargs, len(intargs))
        primvar.SetFloatArray(self.rman_scene.rman.Tokens.Rix.k_Ri_subdivtagfloatargs, floatargs, len(floatargs))
        primvar.SetStringArray(self.rman_scene.rman.Tokens.Rix.k_Ri_subdivtagstringtags, stringargs, len(stringargs))        

    def export(self, ob, db_name):
        
        sg_node = self.rman_scene.sg_scene.CreateMesh(db_name)
        rman_sg_mesh = RmanSgMesh(self.rman_scene, sg_node, db_name)

        if self.rman_scene.do_motion_blur:
            rman_sg_mesh.is_transforming = object_utils.is_transforming(ob)
            rman_sg_mesh.is_deforming = object_utils._is_deforming_(ob)

        return rman_sg_mesh

    def export_deform_sample(self, rman_sg_mesh, ob, time_sample, sg_node=None):

        mesh = None
        mesh = ob.to_mesh()
        if not sg_node:
            sg_node = rman_sg_mesh.sg_node
        primvar = sg_node.GetPrimVars()
        P = object_utils._get_mesh_points_(mesh)
        npoints = len(P)

        if rman_sg_mesh.npoints != npoints:
            primvar.SetTimes([])
            sg_node.SetPrimVars(primvar)
            rman_sg_mesh.is_transforming = False
            rman_sg_mesh.is_deforming = False
            if rman_sg_mesh.is_multi_material:
                for c in rman_sg_mesh.multi_material_children:
                    pvar = c.GetPrimVars()
                    pvar.SetTimes( [] )                               
                    c.SetPrimVars(pvar)            
            return       

        primvar.SetPointDetail(self.rman_scene.rman.Tokens.Rix.k_P, P, "vertex", time_sample)                            

        sg_node.SetPrimVars(primvar)

        if rman_sg_mesh.is_multi_material:
            for c in rman_sg_mesh.multi_material_children:
                pvar = c.GetPrimVars()
                pvar.SetPointDetail(self.rman_scene.rman.Tokens.Rix.k_P, P, "vertex", time_sample)                                  
                c.SetPrimVars(pvar)

        ob.to_mesh_clear()    

    def update(self, ob, rman_sg_mesh, input_mesh=None, sg_node=None):
        rm = ob.renderman
        mesh = input_mesh
        if not mesh:
            mesh = ob.to_mesh()
            if not mesh:
                return True

        if not sg_node:
            sg_node = rman_sg_mesh.sg_node

        rman_sg_mesh.is_subdiv = object_utils.is_subdmesh(ob)
        use_smooth_normals = getattr(ob.data.renderman, 'rman_smoothnormals', False)
        get_normals = (rman_sg_mesh.is_subdiv == 0 and not use_smooth_normals)
        (nverts, verts, P, N) = object_utils._get_mesh_(mesh, get_normals=get_normals)
        
        # if this is empty continue:
        if nverts == []:
            if not input_mesh:
                ob.to_mesh_clear()
            sg_node = None
            rman_sg_mesh.is_transforming = False
            rman_sg_mesh.is_deforming = False
            return None

        npolys = len(nverts) 
        npoints = len(P)
        numnverts = len(verts)

        rman_sg_mesh.npoints = npoints
        rman_sg_mesh.npolys = npolys
        rman_sg_mesh.nverts = numnverts

        sg_node.Define( npolys, npoints, numnverts )
        rman_sg_mesh.is_multi_material = _is_multi_material_(ob, mesh)
            
        primvar = sg_node.GetPrimVars()
        primvar.Clear()

        if rman_sg_mesh.is_deforming and len(rman_sg_mesh.deform_motion_steps) > 1:
            super().set_primvar_times(rman_sg_mesh.deform_motion_steps, primvar)
        
        primvar.SetPointDetail(self.rman_scene.rman.Tokens.Rix.k_P, P, "vertex")
        _get_primvars_(ob, rman_sg_mesh, mesh, primvar)   

        primvar.SetIntegerDetail(self.rman_scene.rman.Tokens.Rix.k_Ri_nvertices, nverts, "uniform")
        primvar.SetIntegerDetail(self.rman_scene.rman.Tokens.Rix.k_Ri_vertices, verts, "facevarying")                  

        if rman_sg_mesh.is_subdiv:
            creases = self._get_subd_tags_(ob, mesh, primvar)
            if ob.data.renderman.rman_subdiv_scheme == 'none':
                # we were tagged as a subdiv by a modifier
                sg_node.SetScheme(self.rman_scene.rman.Tokens.Rix.k_catmullclark) 
            else:
                sg_node.SetScheme(ob.data.renderman.rman_subdiv_scheme) 

        else:
            sg_node.SetScheme(None)
            if N:
                if len(N) == numnverts:
                    primvar.SetNormalDetail(self.rman_scene.rman.Tokens.Rix.k_N, N, "facevarying")         
                else:
                    primvar.SetNormalDetail(self.rman_scene.rman.Tokens.Rix.k_N, N, "uniform")         
        subdiv_scheme = getattr(ob.data.renderman, 'rman_subdiv_scheme', 'none')
        rman_sg_mesh.subdiv_scheme = subdiv_scheme

        if rman_sg_mesh.is_multi_material:
            material_ids = _get_material_ids(ob, mesh)
            for mat_id, faces in \
                _get_mats_faces_(nverts, material_ids).items():

                mat = ob.data.materials[mat_id]
                if not mat:
                    continue
                mat_handle = object_utils.get_db_name(mat) 
                sg_material = self.rman_scene.rman_materials.get(mat.original, None)

                if mat_id == 0:
                    primvar.SetIntegerArray(self.rman_scene.rman.Tokens.Rix.k_shade_faceset, faces, len(faces))
                    scenegraph_utils.set_material(sg_node, sg_material.sg_node)
                else:                
                    sg_sub_mesh =  self.rman_scene.sg_scene.CreateMesh("")
                    sg_sub_mesh.Define( npolys, npoints, numnverts )                   
                    if rman_sg_mesh.is_subdiv:
                        sg_sub_mesh.SetScheme(self.rman_scene.rman.Tokens.Rix.k_catmullclark)
                    pvars = sg_sub_mesh.GetPrimVars()  
                    if rman_sg_mesh.is_deforming and len(rman_sg_mesh.deform_motion_steps) > 1:
                        super().set_primvar_times(rman_sg_mesh.deform_motion_steps, pvars)
                    pvars.Inherit(primvar)
                    pvars.SetIntegerArray(self.rman_scene.rman.Tokens.Rix.k_shade_faceset, faces, len(faces))                    
                    sg_sub_mesh.SetPrimVars(pvars)
                    # call export_object_primvars so we can get things like displacement bound
                    super().export_object_primvars(ob, rman_sg_mesh, sg_sub_mesh)
                    scenegraph_utils.set_material(sg_sub_mesh, sg_material.sg_node)
                    sg_node.AddChild(sg_sub_mesh)
                    rman_sg_mesh.multi_material_children.append(sg_sub_mesh)
        else:
            rman_sg_mesh.multi_material_children = []

        sg_node.SetPrimVars(primvar)

        if not input_mesh:
            ob.to_mesh_clear()  

        return True    