from ..rfb_utils import texture_utils
from ..rfb_utils import string_utils
from ..rfb_utils import shadergraph_utils
from ..rman_ui import rman_ui_light_handlers
from bpy.app.handlers import persistent
import bpy

def register():
    # token updater on scene load
    if string_utils.update_blender_tokens_cb not in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(string_utils.update_blender_tokens_cb)

    # clear gl texture cache on scene load
    if rman_ui_light_handlers.clear_gl_tex_cache not in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(rman_ui_light_handlers.clear_gl_tex_cache)       

    # texture manager load state on scene load
    if texture_utils.txmanager_load_cb not in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(texture_utils.txmanager_load_cb)

    # token updater on scene save
    if string_utils.update_blender_tokens_cb not in bpy.app.handlers.save_post:
        bpy.app.handlers.save_post.append(string_utils.update_blender_tokens_cb)     

    # texture manager save state on scene save
    if texture_utils.txmanager_pre_save_cb not in bpy.app.handlers.save_pre:
        bpy.app.handlers.save_pre.append(texture_utils.txmanager_pre_save_cb)    

def unregister():
    if texture_utils.txmanager_load_cb in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(texture_utils.txmanager_load_cb)

    if rman_ui_light_handlers.clear_gl_tex_cache in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(rman_ui_light_handlers.clear_gl_tex_cache)             

    if string_utils.update_blender_tokens_cb in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(string_utils.update_blender_tokens_cb)

    if string_utils.update_blender_tokens_cb in bpy.app.handlers.save_post:
        bpy.app.handlers.save_post.remove(string_utils.update_blender_tokens_cb)       

    if texture_utils.txmanager_pre_save_cb in bpy.app.handlers.save_pre:
        bpy.app.handlers.save_pre.remove(texture_utils.txmanager_pre_save_cb)                
