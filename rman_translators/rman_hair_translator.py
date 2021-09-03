from .rman_translator import RmanTranslator
from ..rfb_utils import object_utils
from ..rfb_utils import scenegraph_utils
from ..rman_sg_nodes.rman_sg_hair import RmanSgHair
from mathutils import Vector
import math
import bpy    
import numpy as np
   

class RmanHairTranslator(RmanTranslator):

    def __init__(self, rman_scene):
        super().__init__(rman_scene)
        self.bl_type = 'HAIR'  

    def export(self, ob, psys, db_name):

        sg_node = self.rman_scene.sg_scene.CreateGroup(db_name)
        rman_sg_hair = RmanSgHair(self.rman_scene, sg_node, db_name)

        return rman_sg_hair

    def clear_children(self, ob, psys, rman_sg_hair):
        if rman_sg_hair.sg_node:
            for c in [ rman_sg_hair.sg_node.GetChild(i) for i in range(0, rman_sg_hair.sg_node.GetNumChildren())]:
                rman_sg_hair.sg_node.RemoveChild(c)
                self.rman_scene.sg_scene.DeleteDagNode(c)     
                rman_sg_hair.sg_curves_list.clear()   

    def export_deform_sample(self, rman_sg_hair, ob, psys, time_sample):

        curves = self._get_strands_(ob, psys)
        for i, (vertsArray, points, widths, scalpST) in enumerate(curves):
            curves_sg = rman_sg_hair.sg_curves_list[i]
            if not curves_sg:
                continue
            primvar = curves_sg.GetPrimVars()

            primvar.SetPointDetail(self.rman_scene.rman.Tokens.Rix.k_P, points, "vertex", time_sample)  
            curves_sg.SetPrimVars(primvar)

    def update(self, ob, psys, rman_sg_hair):
        if rman_sg_hair.sg_node:
            if rman_sg_hair.sg_node.GetNumChildren() > 0:
                self.clear_children(ob, psys, rman_sg_hair)

        curves = self._get_strands_(ob, psys)
        if not curves:
            return

        for i, (vertsArray, points, widths, scalpST) in enumerate(curves):
            curves_sg = self.rman_scene.sg_scene.CreateCurves("%s-%d" % (rman_sg_hair.db_name, i))
            curves_sg.Define(self.rman_scene.rman.Tokens.Rix.k_cubic, "nonperiodic", "catmull-rom", len(vertsArray), len(points))
            primvar = curves_sg.GetPrimVars()

            primvar.SetPointDetail(self.rman_scene.rman.Tokens.Rix.k_P, points, "vertex")                
            primvar.SetIntegerDetail(self.rman_scene.rman.Tokens.Rix.k_Ri_nvertices, vertsArray, "uniform")
            index_nm = psys.settings.renderman.hair_index_name
            if index_nm == '':
                index_nm = 'index'
            primvar.SetIntegerDetail(index_nm, range(len(vertsArray)), "uniform")

            width_detail = "constant"
            if isinstance(widths, list):
                width_detail = "vertex"
            primvar.SetFloatDetail(self.rman_scene.rman.Tokens.Rix.k_width, widths, width_detail)
            
            if len(scalpST):
                primvar.SetFloatArrayDetail("scalpST", scalpST, 2, "uniform")
                    
            if rman_sg_hair.motion_steps:
                super().set_primvar_times(rman_sg_hair.motion_steps, primvar)

            curves_sg.SetPrimVars(primvar)
            rman_sg_hair.sg_node.AddChild(curves_sg)  
            rman_sg_hair.sg_curves_list.append(curves_sg)

        # Attach material
        mat_idx = psys.settings.material - 1
        if mat_idx < len(ob.material_slots):
            mat = ob.material_slots[mat_idx].material
            material_sg_node = None
            if mat:
                rman_sg_material = self.rman_scene.rman_materials.get(mat.original, None)
                if rman_sg_material:
                    material_sg_node = rman_sg_material.sg_node
            scenegraph_utils.set_material(rman_sg_hair.sg_node, material_sg_node)
        
    def add_object_instance(self, rman_sg_hair, rman_sg_group):
        rman_sg_hair.sg_node.AddChild(rman_sg_group.sg_node)                
        rman_sg_hair.instances[rman_sg_group.db_name] = rman_sg_group
        rman_sg_group.rman_sg_group_parent = rman_sg_hair

    def _get_strands_(self, ob, psys):

        psys_modifier = None
        for mod in ob.modifiers:
            if hasattr(mod, 'particle_system') and mod.particle_system == psys:
                psys_modifier = mod
                break

        if self.rman_scene.is_interactive:
            if psys_modifier and not psys_modifier.show_viewport:
                return None
        else:
            if psys_modifier and not psys_modifier.show_render:
                return None             

        tip_width = psys.settings.tip_radius * psys.settings.radius_scale
        base_width = psys.settings.root_radius * psys.settings.radius_scale

        conwidth = (tip_width == base_width)

        if self.rman_scene.is_interactive:
            steps = (2 ** psys.settings.display_step)+1
        else:
            steps = (2 ** psys.settings.render_step)+1
        
        if conwidth:
            hair_width = base_width
        else:
            hair_width = []

        num_parents = len(psys.particles)
        num_children = len(psys.child_particles)
        if self.rman_scene.is_interactive:
            num_children = int(num_children * psys.settings.display_percentage / 100.0)
        total_hair_count = num_parents + num_children
        export_st = psys.settings.renderman.export_scalp_st and psys_modifier and len(
            ob.data.uv_layers) > 0

        curve_sets = []

        points = []

        vertsArray = []
        scalpST = []
        nverts = 0

        ob_inv_mtx = ob.matrix_world.inverted_safe()
        start_idx = 0
        if psys.settings.child_type != 'NONE' and num_children > 0:
            start_idx = num_parents
        
        for pindex in range(start_idx, total_hair_count):
            strand_points = []
            # walk through each strand
            for step in range(0, steps):           
                pt = psys.co_hair(ob, particle_no=pindex, step=step)

                if pt.length_squared == 0:
                    # this strand ends prematurely                    
                    break                

                # put points in object space
                pt = ob_inv_mtx @ pt

                strand_points.append(pt)

            if len(strand_points) > 1:
                # double the first and last
                strand_points = strand_points[:1] + \
                    strand_points + strand_points[-1:]
                vertsInStrand = len(strand_points)

                # catmull-rom requires at least 4 vertices
                if vertsInStrand < 4:
                    continue

                # for varying width make the width array
                if not conwidth:
                    decr = (base_width - tip_width) / (vertsInStrand - 2)
                    hair_width.extend([base_width] + [(base_width - decr * i)
                                                    for i in range(vertsInStrand - 2)] +
                                    [tip_width])

                # add the last point again
                points.extend(strand_points)
                vertsArray.append(vertsInStrand)
                nverts += vertsInStrand

                # get the scalp ST
                if export_st:
                    particle = psys.particles[
                        (pindex - num_parents) % num_parents]                        
                    st = psys.uv_on_emitter(psys_modifier, particle=particle, particle_no=pindex)
                    scalpST.append([st[0], st[1]])

            # if we get more than 100000 vertices, export ri.Curve and reset.  This
            # is to avoid a maxint on the array length
            if nverts > 100000:
                curve_sets.append(
                    (vertsArray, points, hair_width, scalpST))

                nverts = 0
                points = []
                vertsArray = []
                if not conwidth:
                    hair_width = []
                scalpST = []

        if nverts > 0:
            curve_sets.append((vertsArray, points,
                            hair_width, scalpST))

        return curve_sets              
            