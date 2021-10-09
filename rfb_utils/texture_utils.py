from . import string_utils
from . import filepath_utils
from . import scene_utils
from . import shadergraph_utils
#from . import object_utils
from .prefs_utils import get_pref
from ..rfb_logger import rfb_log
from rman_utils import txmanager
from rman_utils.txmanager import core as txcore
from rman_utils.txmanager import txparams as txparams
from .color_manager_blender import color_manager

from bpy.app.handlers import persistent

import os
import glob
import subprocess
import bpy
import uuid

__RFB_TXMANAGER__ = None

class RfBTxManager(object):

    def __init__(self):        
        self.txmanager = txcore.TxManager(host_token_resolver_func=self.host_token_resolver_func, 
                                        host_prefs_func=self.get_prefs,
                                        host_tex_done_func=self.done_callback,
                                        host_load_func=load_scene_state,
                                        host_save_func=save_scene_state,
                                        texture_extensions=self.get_ext_list(),
                                        color_manager=color_manager())
        self.rman_scene = None

    @property
    def rman_scene(self):
        return self.__rman_scene

    @rman_scene.setter
    def rman_scene(self, rman_scene):
        self.__rman_scene = rman_scene      

    def get_prefs(self):
        prefs = dict()
        prefs['num_workers'] = get_pref('rman_txmanager_workers')
        prefs['fallback_path'] = string_utils.expand_string(get_pref('path_fallback_textures_path'), 
                                                  asFilePath=True)
        prefs['fallback_always'] = get_pref('path_fallback_textures_path_always')
        prefs['keep_extension'] = get_pref('rman_txmanager_keep_extension')

        return prefs

    def get_ext_list(self):
        ext_prefs = get_pref('rman_txmanager_tex_extensions')
        ext_list = ['.%s' % ext for ext in ext_prefs.split()]
        return ext_list

    def host_token_resolver_func(self, outpath):
        if self.rman_scene:
            outpath = string_utils.expand_string(outpath, frame=self.rman_scene.bl_frame_current, asFilePath=True)
        else:
            outpath = string_utils.expand_string(outpath, asFilePath=True)
        return outpath

    def done_callback(self, nodeID, txfile):
        def tex_done():
            try:
                # try and refresh the texture manager UI
                bpy.ops.rman_txmgr_list.refresh('EXEC_DEFAULT')
            except:
                pass
            from .. import rman_render
            output_texture = self.get_output_tex(txfile)
            rr = rman_render.RmanRender.get_rman_render()
            rr.rman_scene_sync.flush_texture_cache([output_texture])
            rr.rman_scene_sync.texture_updated(nodeID)
            
        return tex_done    

    def get_output_tex(self, txfile):
        '''
        Get the real output texture path given a TxFile 
        '''
        if txfile.state in (txmanager.STATE_EXISTS, txmanager.STATE_IS_TEX):
            output_tex = txfile.get_output_texture()
            if self.rman_scene:
                output_tex = string_utils.expand_string(output_tex, frame=self.rman_scene.bl_frame_current, asFilePath=True)
            else:
                output_tex = string_utils.expand_string(output_tex, asFilePath=True)    
        elif txfile.state == txmanager.STATE_INPUT_MISSING:       
            output_tex = txfile.input_image
            if self.rman_scene:
                output_tex = string_utils.expand_string(output_tex, frame=self.rman_scene.bl_frame_current, asFilePath=True)
            else:
                output_tex = string_utils.expand_string(output_tex, asFilePath=True)                
        else:
            output_tex = self.txmanager.get_placeholder_tex()

        return output_tex        


    def get_output_tex_from_id(self, nodeID):
        '''
        Get the real output texture path given a nodeID
        '''
        txfile = self.txmanager.get_txfile_from_id(nodeID)
        if not txfile:
            return ''

        return self.get_output_tex(txfile)

    def get_txfile_from_id(self, nodeID):
        '''
        Get the txfile from given a nodeID
        '''
        txfile = self.txmanager.get_txfile_from_id(nodeID)
        return txfile       
            
    def get_txfile_from_path(self, filepath):
        return self.txmanager.get_txfile_from_path(filepath)                

    def txmake_all(self, blocking=True):
        self.txmanager.txmake_all(start_queue=True, blocking=blocking)   

    def add_texture(self, node, ob, param_name, file_path, node_type='PxrTexture', category='pattern'):
        nodeID = generate_node_id(node, param_name, ob=ob)

        if file_path == "":
            txfile = self.txmanager.get_txfile_from_id(nodeID)
            if txfile:
                self.txmanager.remove_texture(nodeID)
                bpy.ops.rman_txmgr_list.remove_texture('EXEC_DEFAULT', nodeID=nodeID)
        else:
            txfile = self.txmanager.add_texture(nodeID, file_path, nodetype=node_type, category=category)    
            bpy.ops.rman_txmgr_list.add_texture('EXEC_DEFAULT', filepath=file_path, nodeID=nodeID)
            txmake_all(blocking=False)
            if txfile:
                self.done_callback(nodeID, txfile)      

    def is_file_src_tex(self, file_path):
        txfile = self.txmanager.get_txfile_from_path(file_path)
        if txfile:
            return (txfile.state == txmanager.STATE_IS_TEX)  
        return False

    def does_file_exist(self, file_path):
        txfile = self.txmanager.get_txfile_from_path(file_path)
        if txfile:
            return (txfile.state != txmanager.STATE_INPUT_MISSING)  
        return True

    def does_nodeid_exists(self, nodeID):
        txfile = self.txmanager.get_txfile_from_id(nodeID)
        if txfile:
            return True
        return False

def get_txmanager():
    global __RFB_TXMANAGER__
    if __RFB_TXMANAGER__ is None:
        __RFB_TXMANAGER__ = RfBTxManager()
    return __RFB_TXMANAGER__    

def update_texture(node, ob=None, check_exists=False):
    if hasattr(node, 'bl_idname'):
        if node.bl_idname == "PxrPtexturePatternNode":
            return
        elif node.bl_idname == "PxrOSLPatternNode":
            for input_name, input in node.inputs.items():
                if hasattr(input, 'is_texture') and input.is_texture:
                    prop = input.default_value
                    nodeID = generate_node_id(node, input_name)
                    real_file = filepath_utils.get_real_path(prop)
                    get_txmanager().txmanager.add_texture(nodeID, real_file)    
                    bpy.ops.rman_txmgr_list.add_texture('EXEC_DEFAULT', filepath=real_file)                                                      
            return
        elif node.bl_idname == 'ShaderNodeGroup':
            nt = node.node_tree
            for node in nt.nodes:
                update_texture(node, ob=ob)
            return

    if hasattr(node, 'prop_meta'):
        for prop_name, meta in node.prop_meta.items():
            if hasattr(node, prop_name):
                prop = getattr(node, prop_name)

                if meta['renderman_type'] == 'page':
                    continue
                else:
                    if 'widget' in meta and meta['widget'] in ['assetidinput', 'fileinput'] and prop_name != 'iesProfile':
                        node_type = ''
                        if isinstance(ob, bpy.types.Object):
                            if ob.type == 'LIGHT':
                                node_type = ob.data.renderman.get_light_node_name()
                            else:
                                node_type = node.bl_label                            
                        else:
                            node_type = node.bl_label

                        if ob and check_exists:
                            nodeID = generate_node_id(node, prop_name, ob=ob)
                            if get_txmanager().does_nodeid_exists(nodeID):
                                continue

                        category = getattr(node, 'renderman_node_type', 'pattern') 
                        get_txmanager().add_texture(node, ob, prop_name, prop, node_type=node_type, category=category)

def generate_node_id(node, prop_name, ob=None):
    if ob:
        nodeID = '%s|%s|%s' % (node.name, prop_name, ob.name)    
    else:
        prop = ''
        real_file = ''
        if hasattr(node, prop_name):
            prop = getattr(node, prop_name)
            real_file = filepath_utils.get_real_path(prop)
        nodeID = '%s|%s|%s' % (node.name, prop_name, real_file)
    return nodeID

def get_textures(id, check_exists=False):
    if id is None or not id.node_tree:
        return

    nt = id.node_tree
    for node in nt.nodes:
        update_texture(node, ob=id, check_exists=check_exists)

def get_blender_image_path(bl_image):
    if bl_image.packed_file:
        bl_image.unpack()
    real_file = bpy.path.abspath(bl_image.filepath, library=bl_image.library)          
    return real_file 

def add_images_from_image_editor():
    
    # convert images in the image editor
    for img in bpy.data.images:
        if img.type != 'IMAGE':
            continue
        img_path = get_blender_image_path(img)
        if img_path != '' and os.path.exists(img_path): 
            nodeID = str(uuid.uuid1())
            txfile = get_txmanager().txmanager.add_texture(nodeID, img_path)        
            bpy.ops.rman_txmgr_list.add_texture('EXEC_DEFAULT', filepath=img_path, nodeID=nodeID)       
            if txfile:
                get_txmanager().done_callback(nodeID, txfile)  

def parse_scene_for_textures(bl_scene=None):

    #add_images_from_image_editor()

    mats_to_scan = []
    if bl_scene:
        for o in scene_utils.renderable_objects(bl_scene):
            if o.type == 'EMPTY':
                continue
            elif o.type == 'CAMERA':
                node = shadergraph_utils.find_projection_node(o) 
                if node:
                    update_texture(node, ob=o)
            elif o.type == 'LIGHT':
                node = o.data.renderman.get_light_node()
                if node:
                    update_texture(node, ob=o)

    for world in bpy.data.worlds:
        if not world.use_nodes:
            continue
        node = shadergraph_utils.find_integrator_node(world)
        if node:
            update_texture(node, ob=world)
        for node in shadergraph_utils.find_displayfilter_nodes(world):
            update_texture(node, ob=world)
        for node in shadergraph_utils.find_samplefilter_nodes(world):
            update_texture(node, ob=world)            
 
    for mat in bpy.data.materials:
        get_textures(mat)
            
def parse_for_textures(bl_scene):    
    rfb_log().debug("Parsing scene for textures.")                                   
    parse_scene_for_textures(bl_scene)

def save_scene_state(state):
    """Save the serialized TxManager object in scene.renderman.txmanagerData.
    """
    if bpy.context.engine != 'PRMAN_RENDER':
        return
    scene = bpy.context.scene
    rm = getattr(scene, 'renderman', None)
    if rm:
        setattr(rm, 'txmanagerData', state)

def load_scene_state():
    """Load the JSON serialization from scene.renderman.txmanagerData and use it
    to update the texture manager.
    """
    if bpy.context.engine != 'PRMAN_RENDER':
        return
    scene = bpy.context.scene
    rm = getattr(scene, 'renderman', None)
    state = '{}'
    if rm:
        state = getattr(rm, 'txmanagerData', state)
    return state

@persistent
def txmanager_load_cb(bl_scene):
    if bpy.context.engine != 'PRMAN_RENDER':
        return    
    get_txmanager().txmanager.load_state()
    bpy.ops.rman_txmgr_list.parse_scene('EXEC_DEFAULT')

@persistent
def txmanager_pre_save_cb(bl_scene):
    if bpy.context.engine != 'PRMAN_RENDER':
        return    
    get_txmanager().txmanager.save_state()  

@persistent
def link_file_handler(bl_scene):
    for update in bpy.context.evaluated_depsgraph_get().updates:
        id = update.id
        if id.library:
            # only look at objects coming from a library
            if isinstance(id, bpy.types.Material):
                get_textures(id, check_exists=True)

            elif isinstance(id, bpy.types.Object):
                if id.type == 'CAMERA':
                    node = shadergraph_utils.find_projection_node(id) 
                    if node:
                        update_texture(node, ob=id, check_exists=True)

                elif id.type == 'LIGHT':
                    node = id.data.renderman.get_light_node()
                    if node:
                        update_texture(node, ob=id, check_exists=True)           

def txmake_all(blocking=True):
    get_txmanager().txmake_all(blocking=blocking)        