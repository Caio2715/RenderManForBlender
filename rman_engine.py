import bpy
import bgl
import blf

from .rfb_utils.prefs_utils import get_pref
from .rfb_utils import string_utils
from .rfb_logger import rfb_log

class PRManRender(bpy.types.RenderEngine):
    bl_idname = 'PRMAN_RENDER'
    bl_label = "RenderMan"
    bl_use_preview = False # Turn off preview renders
    bl_use_save_buffers = True
    bl_use_shading_nodes = True # We support shading nodes
    bl_use_shading_nodes_custom = False
    bl_use_eevee_viewport = True # Use Eevee for look dev viewport mode
    bl_use_postprocess = True

    def __init__(self):
        from . import rman_render
        self.rman_render = rman_render.RmanRender.get_rman_render()
        self.export_failed = None
        self.ipr_already_running = False
        if self.rman_render.rman_interactive_running:
            # If IPR is already running, just flag it
            # and don't do anything in the update methods
            self.ipr_already_running = True
            return 

    def __del__(self):
        try:
            from . import rman_render
        except ModuleNotFoundError:
            return

        rr = rman_render.RmanRender.get_rman_render()
        try:
            if self.is_preview:
                # If this was a preview render, return
                return
        except:
            pass

        if rr.rman_running:
            if rr.rman_interactive_running:
                rfb_log().debug("Stop interactive render.")
                rr.rman_is_live_rendering = False            
            elif rr.is_regular_rendering():
                rfb_log().debug("Stop render.")
            rr.stop_render(stop_draw_thread=False)                 

    def update(self, data, depsgraph):
        pass

    def view_update(self, context, depsgraph):
        '''
        For viewport renders. Blender calls view_update when starting viewport renders
        and/or something changes in the scene.
        '''

        # check if we are already doing a regular render
        if self.rman_render.is_regular_rendering():
            return

        if self.export_failed:
            return            

        if self.ipr_already_running:
            return

        if self.rman_render.is_ipr_to_it():
            # if we are already IPRing to "it", stop the render
            self.rman_render.stop_render(stop_draw_thread=False)

        # if interactive rendering has not started, start it
        if not self.rman_render.rman_interactive_running and self.rman_render.sg_scene is None:
            self.rman_render.bl_engine = self
            self.rman_render.rman_scene.ipr_render_into = 'blender'
            if not self.rman_render.start_interactive_render(context, depsgraph):
                self.export_failed = True
                return
            self.export_failed = False
                
        if self.rman_render.rman_interactive_running and not self.rman_render.rman_license_failed:
            self.rman_render.update_scene(context, depsgraph)   

    def view_draw(self, context, depsgraph):
        '''
        For viewport renders. Blender calls view_draw whenever it redraws the 3D viewport.
        This is where we check for camera moves and draw pxiels from our
        Blender display driver.
        '''
        if self.export_failed:
            return
        if self.ipr_already_running:
            self.draw_viewport_message(context, 'Multiple viewport rendering not supported.')
            return

        if self.rman_render.rman_interactive_running and not self.rman_render.rman_license_failed:               
            self.rman_render.update_view(context, depsgraph)

        self._draw_pixels(context, depsgraph)

    def _increment_version_tokens(self, external_render=False):
        bl_scene = bpy.context.scene
        vi = get_pref('rman_scene_version_increment', default='MANUALLY')
        ti = get_pref('rman_scene_take_increment', default='MANUALLY')

        if (vi == 'RENDER' and not external_render) or (vi == 'BATCH_RENDER' and external_render):
            bl_scene.renderman.version_token += 1
            string_utils.set_var('version', bl_scene.renderman.version_token)
        
        if (ti == 'RENDER' and not external_render) or (ti == 'BATCH_RENDER' and external_render):
            bl_scene.renderman.take_token += 1
            string_utils.set_var('take', bl_scene.renderman.take_token)            

    def update_render_passes(self, scene=None, renderlayer=None):
        # this method allows us to add our AOVs as ports to the RenderLayer node
        # in the compositor.

        from .rfb_utils import display_utils
        if self.is_preview:
            return

        if self.rman_render.rman_render_into != 'blender':
            return

        if self.ipr_already_running:
            return            

        self.rman_render.rman_scene.bl_scene = scene
        dspy_dict = display_utils.get_dspy_dict(self.rman_render.rman_scene, include_holdouts=False)
        self.register_pass(scene, renderlayer, "Combined", 4, "RGBA", 'COLOR')
        for i, dspy_nm in enumerate(dspy_dict['displays'].keys()):
            if i == 0:
                continue
            dspy = dspy_dict['displays'][dspy_nm]
            dspy_chan = dspy['params']['displayChannels'][0]
            chan_info = dspy_dict['channels'][dspy_chan]
            chan_type = chan_info['channelType']['value']

            if chan_type  == 'color':
                 self.register_pass(scene, renderlayer, dspy_nm, 3, "RGB", 'COLOR')
            elif chan_type in ['vector', 'normal', 'point']:
                self.register_pass(scene, renderlayer, dspy_nm, 3, "XYZ", 'VECTOR')
            else:
                self.register_pass(scene, renderlayer, dspy_nm, 1, "Z", 'VALUE')
     
    def render(self, depsgraph):
        '''
        Main render entry point. Blender calls this when doing final renders or preview renders.
        '''
   
        bl_scene = depsgraph.scene_eval
        rm = bl_scene.renderman
        baking = (rm.hider_type in ['BAKE', 'BAKE_BRICKMAP_SELECTED'])   

        if self.rman_render.rman_interactive_running:
            # report an error if a render is trying to start while IPR is running
            if self.is_preview and get_pref('rman_do_preview_renders', False):
                #self.report({'ERROR'}, 'Cannot start a preview render when IPR is running')
                rfb_log().debug('Cannot start a preview render when IPR is running')
                pass
            elif not self.is_preview:
                self.report({'ERROR'}, 'Cannot start a render when IPR is running')
            return
        elif self.is_preview:
            # double check we're not already viewport rendering
            if self.rman_render.rman_interactive_running:
                if get_pref('rman_do_preview_renders', False):
                    rfb_log().error("Cannot preview render while viewport rendering.")
                return            
            if not get_pref('rman_do_preview_renders', False):
                # user has turned off preview renders, just load the placeholder image
                self.rman_render.bl_scene = depsgraph.scene_eval
                #self.rman_render._load_placeholder_image()
                return    
            if self.rman_render.rman_swatch_render_running:
                return       
            self.rman_render.bl_engine = self                                  
            self.rman_render.start_swatch_render(depsgraph)
        elif baking:
            self.rman_render.bl_engine = self    
            if rm.enable_external_rendering:
                self.rman_render.start_external_bake_render(depsgraph) 
            elif not self.rman_render.start_bake_render(depsgraph, for_background=bpy.app.background):
                return
        elif rm.enable_external_rendering:
            self.rman_render.bl_engine = self
            self.rman_render.start_external_render(depsgraph)         
            self._increment_version_tokens(external_render=True)                 
        else:
            for_background = bpy.app.background
            self.rman_render.bl_engine = self
            if not self.rman_render.start_render(depsgraph, for_background=for_background):
                return    
            if not for_background:
                self._increment_version_tokens(external_render=False)

    def draw_viewport_message(self, context, msg):
        w = context.region.width     

        pos_x = w / 2 - 100
        pos_y = 20
        blf.enable(0, blf.SHADOW)
        blf.shadow_offset(0, 1, -1)
        blf.shadow(0, 5, 0.0, 0.0, 0.0, 0.8)
        blf.size(0, 32, 36)
        blf.position(0, pos_x, pos_y, 0)
        blf.color(0, 1.0, 0.0, 0.0, 1.0)
        blf.draw(0, "%s" % (msg))
        blf.disable(0, blf.SHADOW)   

    def _draw_pixels(self, context, depsgraph):         

        if self.rman_render.rman_license_failed:
            self.draw_viewport_message(context, self.rman_render.rman_license_failed_message)

        if not self.rman_render.rman_is_viewport_rendering:
            return       

        scene = depsgraph.scene
        w = context.region.width
        h = context.region.height                       

        # Bind shader that converts from scene linear to display space,
        bgl.glEnable(bgl.GL_BLEND)
        bgl.glBlendFunc(bgl.GL_ONE, bgl.GL_ONE_MINUS_SRC_ALPHA)
        self.bind_display_space_shader(scene)

        self.rman_render.draw_pixels(w, h)

        self.unbind_display_space_shader()
        bgl.glDisable(bgl.GL_BLEND)       

classes = [
    PRManRender,
]

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    
def unregister():    
    for cls in classes:
        try:
            bpy.utils.unregister_class(cls)
        except RuntimeError:
            rfb_log().debug('Could not unregister class: %s' % str(cls))
            pass