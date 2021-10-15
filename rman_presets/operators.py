# ##### BEGIN MIT LICENSE BLOCK #####
#
# Copyright (c) 2015 - 2021 Pixar
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.
#
#
# ##### END MIT LICENSE BLOCK #####

from ..rfb_utils import filepath_utils
from ..rfb_utils.envconfig_utils import envconfig
from ..rfb_utils import object_utils
from ..rfb_utils.shadergraph_utils import is_renderman_nodetree
from ..rfb_logger import rfb_log
from ..rfb_icons import get_icon
import os
import bpy
import glob
from bpy.props import StringProperty, EnumProperty, BoolProperty, CollectionProperty, IntProperty
from . import rmanAssetsBlender as rab
from .properties import RendermanPresetMetaData
from rman_utils.rman_assets import lib as ral
from rman_utils.filepath import FilePath
from rman_utils.rman_assets.common.external_files import Storage
import getpass

def safe_mkdir(filepath):
    if not filepath.exists():
        try:
            os.mkdir(filepath.os_path())
        except BaseException as err:
                rfb_log().error('Failed to create: %s', filepath.os_path())
                rfb_log().error('  |_ %s', err)        

# if the library isn't present copy it from rmantree to the path in addon prefs
class PRMAN_OT_init_preset_library(bpy.types.Operator):
    bl_idname = "renderman.init_preset_library"
    bl_label = "Init RenderMan Preset Library"
    bl_description = "Choose a preset browser library. If not found, copies the factory library from RMANTREE to the path chosen."

    directory: bpy.props.StringProperty(subtype='FILE_PATH')

    def invoke(self, context, event):
        self.op = getattr(context, 'op_ptr', None)      
        context.window_manager.fileselect_add(self)

        return {'RUNNING_MODAL'}

    def execute(self, context):

        json_file = os.path.join(self.directory, 'library.json')
        hostPrefs = rab.get_host_prefs()

        if not os.path.exists(json_file):        
            if os.access(self.directory, os.W_OK):
                rmantree_lib_path = os.path.join(envconfig().rmantree, 'lib', 'RenderManAssetLibrary')
                self.directory = ral.copyLibrary(FilePath(rmantree_lib_path), FilePath(self.directory))
            else:
                raise Exception("No preset library found or directory chosen is not writable.")
                return {'FINISHED'}

        hostPrefs.cfg.setCurrentLibraryByPath(FilePath(self.directory))
        lib_info = hostPrefs.cfg.getCurrentLibraryInfos()
        hostPrefs.setSelectedLibrary(FilePath(self.directory))
        lib_info.setData('protected', False) 
        lib_info.save(FilePath(self.directory))
        hostPrefs.setSelectedCategory(os.path.join(FilePath(self.directory), 'EnvironmentMaps'))
        hostPrefs.setSelectedPreset('')
        hostPrefs.saveAllPrefs()     

        # re-open the preset browser
        bpy.ops.renderman.rman_open_presets_editor('INVOKE_DEFAULT')

        return {'FINISHED'}

class PRMAN_OT_edit_library_info(bpy.types.Operator):
    bl_idname = "renderman.edit_library_info"
    bl_label = "Edit Library Info"
    bl_description = "Edit the current library info"

    name: StringProperty(name="Library Name", default="")
    author: StringProperty(name="Author", default="")
    description: StringProperty(name="Description", default="")
    protected: BoolProperty(name="Protected", default=True)
    version: StringProperty(name="Version", default="")

    def execute(self, context):

        hostPrefs = rab.get_host_prefs()
        directory = hostPrefs.cfg.getCurrentLibraryPath()
        lib_info = hostPrefs.cfg.getCurrentLibraryInfos()
        lib_info.setData('name', self.properties.name)
        lib_info.setData('author', self.properties.author)
        lib_info.setData('description', self.properties.description) 
        lib_info.setData('version', self.properties.version)
        lib_info.setData('protected', self.properties.protected) 
        lib_info.save(FilePath(directory))

        if self.op:
            self.op.library_name = self.properties.name  
            self.op.is_editable = not self.properties.protected    
            self.op.preset_categories_index = self.op.preset_categories_index

        return {'FINISHED'}        

    def invoke(self, context, event):
        hostPrefs = rab.get_host_prefs()
        lib_info = hostPrefs.cfg.getCurrentLibraryInfos()
        self.op = getattr(context, 'op_ptr', None)

        self.properties.name = lib_info.getData('name')
        self.properties.author = lib_info.getData('author')
        self.properties.description = lib_info.getData('description')
        self.properties.protected = lib_info.getData('protected')
        self.properties.version = lib_info.getData('version')

        return context.window_manager.invoke_props_dialog(self)

    def draw(self, context):
        row = self.layout
        row.prop(self, "name")
        row.prop(self, "author")
        row.prop(self, "description")
        row.prop(self, "version")
        row.prop(self, "protected")

class PRMAN_OT_load_asset_to_scene(bpy.types.Operator):
    bl_idname = "renderman.load_asset_to_scene"
    bl_label = "Load Asset to Scene"
    bl_description = "Load the Asset to scene"

    preset_path: StringProperty(default='')
    assign: BoolProperty(default=False)
    preset_description: StringProperty(default='')

    @classmethod
    def description(cls, context, properties):    
        info = cls.bl_description
        if properties.preset_description:
            info = properties.preset_description
        return info    

    def invoke(self, context, event):
        from . import rmanAssetsBlender
        mat = rmanAssetsBlender.importAsset(self.properties.preset_path)
        if self.properties.assign and mat and type(mat) == bpy.types.Material:
            for ob in context.selected_objects:
                if ob.type == 'EMPTY':
                    ob.renderman.rman_material_override = mat
                    ob.update_tag(refresh={'OBJECT'})
                else:
                    ob.active_material = mat

        return {'FINISHED'}

class PRMAN_UL_Presets_Meta_Data_List(bpy.types.UIList):

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        layout.label(text=item.key)

class PRMAN_OT_preset_add_metadata(bpy.types.Operator):
    bl_idname = "renderman.preset_add_metadata"
    bl_label = "Add"
    bl_description = "Add Meta Data"
    bl_options = {'INTERNAL'}

    def execute(self, context):
        op_ptr = context.op_ptr
        md = op_ptr.meta_data.add()
        op_ptr.meta_data_index = len(op_ptr.meta_data)-1
        md.key = 'key%d' % op_ptr.meta_data_index
        md.value = 'value %d' % op_ptr.meta_data_index

        return {'FINISHED'}        

class PRMAN_OT_preset_delete_metadata(bpy.types.Operator):
    bl_idname = "renderman.preset_delete_metadata"
    bl_label = "Delete"
    bl_description = "Delete Meta Data"
    bl_options = {'INTERNAL'}

    def execute(self, context):
        op_ptr = context.op_ptr
        op_ptr.meta_data.remove(op_ptr.meta_data_index)
        op_ptr.meta_data_index = len(op_ptr.meta_data)-1

        return {'FINISHED'}                

# save the current material to the library
class PRMAN_OT_save_asset_to_lib(bpy.types.Operator):
    bl_idname = "renderman.save_asset_to_library"
    bl_label = "Save Asset to Library"
    bl_description = "Save Asset to Library"

    category_path: StringProperty(default='')
    material_label: StringProperty(name='Asset Name', default='')
    material_author: StringProperty(name='Author', default='')
    material_version: StringProperty(name='Version', default='1.0')
    include_display_filters: BoolProperty(name='Include DisplayFilters', 
        description="Include display filters with this preset. This is necessary if you want to export any stylized materials.",
        default=False)
    meta_data: CollectionProperty(type=RendermanPresetMetaData,
                                      name="Meta Data")
    meta_data_index: IntProperty(default=-1)

    def preview_render_items(self, context):
        items=[
            ('std', 'Standard', 'Standard scene'),
            ('fur', 'Fur', 'Fur scene'),
            ('none', 'None', 'No preview render')
        ]
        return items

    preview_render: EnumProperty(name="Preview",
        items=preview_render_items,
        default=0,
        description='Select which preview render scene to use.'
    )

    storage_mode: EnumProperty(name="Storage",
        items=[
            ('0', 'Asset', 'Save dependencies with the asset'),
            ('1', 'Library', 'Save depedencies in the global library storage'),
            ('2', 'External', 'A path external to the library')
        ],
        default='0',
        description='Select where to save the dependencies for this preset'
    )

    storage_path: StringProperty(name="Path", default="")

    def get_storage_keys(self, context):
        items = []
        hostPrefs = rab.get_host_prefs()  
        lib_root = FilePath(hostPrefs.cfg.getCurrentLibraryPath())
        gs_path = lib_root.join('global_storage', '*')
        for f in glob.glob(gs_path.os_path()):
            items.append((f, f, ''))          
        return items

    storage_key: EnumProperty(name="Storage Key",
        items=get_storage_keys
    )

    convert_to_tex: BoolProperty(name="Convert to Tex",
        default=True
    )

    @classmethod
    def poll(cls, context):
        ob = context.active_object
        if ob is None:
            return False
        if not hasattr(ob, 'active_material'):
            return False
        mat = ob.active_material
        return is_renderman_nodetree(mat)

    def get_current_material(self, context):
        ob = context.active_object
        return ob.active_material
        
    def getStorage(self):
        hostPrefs = rab.get_host_prefs()
        lib_path = FilePath(hostPrefs.cfg.getCurrentLibraryPath())
        category = hostPrefs.getSelectedCategory()
        label = rab.asset_name_from_label(self.material_label)
        storage_path = filepath_utils.get_real_path(self.storage_path)
        storage_mode = int(self.storage_mode)

        key = None
        path = None
        asset_path = lib_path.join(category, label)
        if storage_mode == 1:
            key = self.storage_key
        if storage_mode == 2:
            if storage_path != '':
                path = FilePath(storage_path)
            else:
                storage_mode = 0

        storage = Storage(
            storage_mode,
            asset_path=asset_path,
            lib_path=lib_path,
            key=key,
            path=path
        )      

        return storage  

    def draw(self, context):
        layout = self.layout
        col = layout.column()
        col.prop(self, 'material_label')
        col.prop(self, 'material_author')
        col.prop(self, 'material_version')
        col.prop(self, 'include_display_filters')

        row = col.row()
        split = row.split(factor=0.55)
        col2 = split.column()
        col2.prop(self, 'storage_mode', text='Storage')
        if int(self.storage_mode) == 1:
            col2 = split.column()
            split = col2.split(factor=0.85)
            split.prop(self, 'storage_key', text='')
            split.operator('renderman.preset_add_storage_key', text='', icon='ADD')
        if int(self.storage_mode) == 2:
            col2 = split.column()
            col2.prop(self, 'storage_path', text='')

        col.prop(self, 'convert_to_tex')

        row = col.row()
        col2 = row.column()
        col2.prop(self, 'preview_render')
        icon = get_icon(name='rman_preview_%s' % self.properties.preview_render)
        col2.template_icon(icon.icon_id, scale=5.0)         

        col.separator()
        col.label(text="Meta Data:")
        row = col.row()
        row.context_pointer_set('op_ptr', self)
        col2 = row.column()
        col2.operator('renderman.preset_add_metadata')
        col2 = row.column()
        col2.operator('renderman.preset_delete_metadata')
        if self.meta_data_index < 0 or self.meta_data_index >= len(self.meta_data):
            col2.enabled = False

        col.template_list("PRMAN_UL_Presets_Meta_Data_List", "Meta Data",
                            self.properties, "meta_data", self.properties, 'meta_data_index', rows=5)
        if self.properties.meta_data_index >= 0:
            md = self.properties.meta_data[self.properties.meta_data_index]
            col.prop(md, 'key')
            col.prop(md, 'value')

    def execute(self, context):
        hostPrefs = rab.get_host_prefs()
        if hostPrefs.preExportCheck('material', hdr=None, context=context, include_display_filters=self.include_display_filters):
            label = rab.asset_name_from_label(self.material_label)
            infodict = dict()
            infodict['metadict'] = {'label': label,
                        'author': self.material_author,
                        'version': self.material_version}     
            for md in self.meta_data:
                infodict['metadict'][md.key] = md.value
            infodict['storage'] = self.getStorage()
            infodict['convert_to_tex'] = self.convert_to_tex                
            category = hostPrefs.getSelectedCategory()   
            hostPrefs.exportMaterial(category, infodict, self.preview_render)

        if self.op:
            self.op.preset_categories_index = 0 
        return {'FINISHED'}

    def invoke(self, context, event):
        hostPrefs = rab.get_host_prefs()
        wm = context.window_manager
        mat = self.get_current_material(context)        
        self.material_label = mat.name
        self.material_author = getpass.getuser()
        self.material_version = '1.0'
        self.storage_mode = str(hostPrefs.rpbStorageMode)
        #self.storage_key = hostPrefs.rpbStorageKey
        #self.storage_path = hostPrefs.rpbStoragePath
        self.op = getattr(context, 'op_ptr', None) 
        return wm.invoke_props_dialog(self) 

class PRMAN_OT_add_storage_key(bpy.types.Operator):
    bl_idname = "renderman.preset_add_storage_key"
    bl_label = "Add Storage Key"
    bl_description = "Add a storage key to the library"

    storage_key: StringProperty(name="Key", default='')

    def draw(self, context):
        layout = self.layout
        col = layout.column()
        col.prop(self, 'storage_key')     

    def execute(self, context):
        if self.storage_key == '':
            return {'FINISHED'}

        hostPrefs = rab.get_host_prefs()
        lib_root = FilePath(hostPrefs.cfg.getCurrentLibraryPath())
        storage_path = lib_root.join('global_storage')
        safe_mkdir(storage_path)
        safe_mkdir(storage_path.join(self.storage_key))        

        return {'FINISHED'}

    def invoke(self, context, event):
        wm = context.window_manager
        return wm.invoke_props_dialog(self)         

class PRMAN_OT_save_lightrig_to_lib(bpy.types.Operator):
    bl_idname = "renderman.save_lightrig_to_library"
    bl_label = "Save LightRig to Library"
    bl_description = "Save LightRig to Library"

    category_path: StringProperty(default='')
    label: StringProperty(name='Asset Name', default='')
    author: StringProperty(name='Author', default='')
    version: StringProperty(name='Version', default='1.0')
    category: StringProperty(name='Category', default='')
    meta_data: CollectionProperty(type=RendermanPresetMetaData,
                                      name="Meta Data")
    meta_data_index: IntProperty(default=-1)   

    def preview_render_items(self, context):
        items=[
            ('std', 'Standard', 'Standard scene'),
            ('fur', 'Fur', 'Fur scene'),
            ('none', 'None', 'No preview render')
        ]
        return items

    preview_render: EnumProperty(name="Preview",
        items=preview_render_items,
        default=0,
        description='Select which preview render scene to use.'
    )

    storage_mode: EnumProperty(name="Storage",
        items=[
            ('0', 'Asset', 'Save dependencies with the asset'),
            ('1', 'Library', 'Save depedencies in the global library storage'),
            ('2', 'External', 'A path external to the library')
        ],
        default='0',
        description='Select where to save the dependencies for this preset'
    )     
    storage_path: StringProperty(name="Path", default="")

    def get_storage_keys(self, context):
        items = []
        hostPrefs = rab.get_host_prefs()  
        lib_root = FilePath(hostPrefs.cfg.getCurrentLibraryPath())
        gs_path = lib_root.join('global_storage', '*')
        for f in glob.glob(gs_path.os_path()):
            items.append((f, f, ''))          
        return items

    storage_key: EnumProperty(name="Storage Key",
        items=get_storage_keys
    )

    convert_to_tex: BoolProperty(name="Convert to Tex",
        default=True
    )    

    @classmethod
    def poll(cls, context):
        selected_light_objects = []
        if context.selected_objects:
            for obj in context.selected_objects:  
                if object_utils._detect_primitive_(obj) == 'LIGHT':
                    selected_light_objects.append(obj)

        if not selected_light_objects:
            return False
            
        return True

    def getStorage(self):
        hostPrefs = rab.get_host_prefs()
        lib_path = FilePath(hostPrefs.cfg.getCurrentLibraryPath())
        category = hostPrefs.getSelectedCategory()
        label = rab.asset_name_from_label(self.label)
        storage_path = filepath_utils.get_real_path(self.storage_path)
        storage_mode = int(self.storage_mode)

        key = None
        path = None
        asset_path = lib_path.join(category, label)
        if storage_mode == 1:
            key = self.storage_key
        if storage_mode == 2:
            if storage_path != '':
                path = FilePath(storage_path)
            else:
                storage_mode = 0

        storage = Storage(
            storage_mode,
            asset_path=asset_path,
            lib_path=lib_path,
            key=key,
            path=path
        )      

        return storage          

    def draw(self, context):
        layout = self.layout
        col = layout.column()
        col.prop(self, 'label')
        col.prop(self, 'author')
        col.prop(self, 'version')

        row = col.row()
        split = row.split(factor=0.55)
        col2 = split.column()
        col2.prop(self, 'storage_mode', text='Storage')
        if int(self.storage_mode) == 1:
            col2 = split.column()
            split = col2.split(factor=0.85)
            split.prop(self, 'storage_key', text='')
            split.operator('renderman.preset_add_storage_key', text='', icon='ADD')
        if int(self.storage_mode) == 2:
            col2 = split.column()
            col2.prop(self, 'storage_path', text='')

        col.prop(self, 'convert_to_tex')

        row = col.row()
        col2 = row.column()
        col2.prop(self, 'preview_render')
        icon = get_icon(name='rman_preview_%s' % self.properties.preview_render)
        col2.template_icon(icon.icon_id, scale=5.0)            

        col.separator()
        col.label(text="Meta Data:")
        row = col.row()
        row.context_pointer_set('op_ptr', self)
        col2 = row.column()
        col2.operator('renderman.preset_add_metadata')
        col2 = row.column()
        col2.operator('renderman.preset_delete_metadata')
        if self.meta_data_index < 0 or self.meta_data_index >= len(self.meta_data):
            col2.enabled = False

        col.template_list("PRMAN_UL_Presets_Meta_Data_List", "Meta Data",
                            self.properties, "meta_data", self.properties, 'meta_data_index', rows=5)
        if self.properties.meta_data_index >= 0:
            md = self.properties.meta_data[self.properties.meta_data_index]
            col.prop(md, 'key')
            col.prop(md, 'value')     

    def execute(self, context):
        hostPrefs = rab.get_host_prefs()
        if hostPrefs.preExportCheck('lightrigs', hdr=None, context=context):
            label = rab.asset_name_from_label(self.label)
            infodict = dict()
            infodict['metadict'] =  {'label': label,
                        'author': self.author,
                        'version': self.version}    
            for md in self.meta_data:
                infodict['metadict'][md.key] = md.value
            infodict['storage'] = self.getStorage()
            infodict['convert_to_tex'] = self.convert_to_tex                    
            category = hostPrefs.getSelectedCategory()   
            hostPrefs.exportMaterial(category, infodict, self.preview_render)        
        if self.op:
            self.op.preset_categories_index = 0 
        return {'FINISHED'}

    def invoke(self, context, event):
        wm = context.window_manager
        ob = context.active_object    
        if ob:
            self.label = ob.name
        self.author = getpass.getuser()
        self.version = '1.0'
        self.op = getattr(context, 'op_ptr', None) 
        return wm.invoke_props_dialog(self) 

class PRMAN_OT_save_envmap_to_lib(bpy.types.Operator):
    bl_idname = "renderman.save_envmap_to_library"
    bl_label = "Save EnvMap to Library"
    bl_description = "Save EnvMap to Library"

    category_path: StringProperty(default='')
    label: StringProperty(name='Asset Name', default='')
    author: StringProperty(name='Author', default=getpass.getuser())
    version: StringProperty(name='Version', default='1.0')
    meta_data: CollectionProperty(type=RendermanPresetMetaData,
                                      name="Meta Data")
    meta_data_index: IntProperty(default=-1)    

    def preview_render_items(self, context):
        items=[
            ('std', 'Standard', 'Standard scene'),
            ('fur', 'Fur', 'Fur scene'),
            ('none', 'None', 'No preview render')
        ]
        return items

    preview_render: EnumProperty(name="Preview",
        items=preview_render_items,
        default=0,
        description='Select which preview render scene to use.'
    )

    storage_mode: EnumProperty(name="Storage",
        items=[
            ('0', 'Asset', 'Save dependencies with the asset'),
            ('1', 'Library', 'Save depedencies in the global library storage'),
            ('2', 'External', 'A path external to the library')
        ],
        default='0',
        description='Select where to save the dependencies for this preset'
    )     
    storage_path: StringProperty(name="Path", default="")

    def get_storage_keys(self, context):
        items = []
        hostPrefs = rab.get_host_prefs()  
        lib_root = FilePath(hostPrefs.cfg.getCurrentLibraryPath())
        gs_path = lib_root.join('global_storage', '*')
        for f in glob.glob(gs_path.os_path()):
            items.append((f, f, ''))          
        return items

    storage_key: EnumProperty(name="Storage Key",
        items=get_storage_keys
    )

    convert_to_tex: BoolProperty(name="Convert to Tex",
        default=True
    )        

    filepath: bpy.props.StringProperty(
        subtype="FILE_PATH")

    filename: bpy.props.StringProperty(
        subtype="FILE_NAME",
        default="")

    filter_glob: bpy.props.StringProperty(
        default="*.hdr;*.tex",
        options={'HIDDEN'},
        )        

    @classmethod
    def poll(cls, context):
        rd = context.scene.render
        return rd.engine == 'PRMAN_RENDER'

    def getStorage(self):
        hostPrefs = rab.get_host_prefs()
        lib_path = FilePath(hostPrefs.cfg.getCurrentLibraryPath())
        category = hostPrefs.getSelectedCategory()
        label = rab.asset_name_from_label(self.label)
        storage_path = filepath_utils.get_real_path(self.storage_path)
        storage_mode = int(self.storage_mode)

        key = None
        path = None
        asset_path = lib_path.join(category, label)
        if storage_mode == 1:
            key = self.storage_key
        if storage_mode == 2:
            if storage_path != '':
                path = FilePath(storage_path)
            else:
                storage_mode = 0

        storage = Storage(
            storage_mode,
            asset_path=asset_path,
            lib_path=lib_path,
            key=key,
            path=path
        )      

        return storage

    def draw(self, context):
        layout = self.layout
        col = layout.column()
        col.prop(self, 'label')
        col.prop(self, 'author')
        col.prop(self, 'version')

        row = col.row()
        split = row.split(factor=0.55)
        col2 = split.column()
        col2.prop(self, 'storage_mode', text='Storage')
        if int(self.storage_mode) == 1:
            col2 = split.column()
            split = col2.split(factor=0.85)
            split.prop(self, 'storage_key', text='')
            split.operator('renderman.preset_add_storage_key', text='', icon='ADD')
        if int(self.storage_mode) == 2:
            col2 = split.column()
            col2.prop(self, 'storage_path', text='')

        col.prop(self, 'convert_to_tex')

        row = col.row()
        col2 = row.column()
        col2.prop(self, 'preview_render')
        icon = get_icon(name='rman_preview_%s' % self.properties.preview_render)
        col2.template_icon(icon.icon_id, scale=5.0)            

        col.separator()
        col.label(text="Meta Data:")
        row = col.row()
        row.context_pointer_set('op_ptr', self)
        col2 = row.column()
        col2.operator('renderman.preset_add_metadata')
        col2 = row.column()
        col2.operator('renderman.preset_delete_metadata')
        if self.meta_data_index < 0 or self.meta_data_index >= len(self.meta_data):
            col2.enabled = False

        col.template_list("PRMAN_UL_Presets_Meta_Data_List", "Meta Data",
                            self.properties, "meta_data", self.properties, 'meta_data_index', rows=5)
        if self.properties.meta_data_index >= 0:
            md = self.properties.meta_data[self.properties.meta_data_index]
            col.prop(md, 'key')
            col.prop(md, 'value')  

    def execute(self, context):
        if self.properties.filename == '':
            return {'FINISHED'}            

        hostPrefs = rab.get_host_prefs()
        hdr = FilePath(self.properties.filepath)
        if self.label == '':
            self.label = os.path.splitext(os.path.basename(self.properties.filepath))[0]
        if hostPrefs.preExportCheck('envmap', hdr=hdr):
            label = rab.asset_name_from_label(self.label)
            infodict = dict()
            infodict['metadict'] = {'label': label,
                        'author': self.author,
                        'version': self.version}     
            for md in self.meta_data:
                infodict['metadict'][md.key] = md.value
            infodict['storage'] = self.getStorage()
            infodict['convert_to_tex'] = self.convert_to_tex                   
            category = hostPrefs.getSelectedCategory()   
            hostPrefs.exportEnvMap(category, infodict, self.preview_render)

        if self.op:
            self.op.preset_categories_index = 0 
        return {'FINISHED'}

    def invoke(self, context, event=None):
        context.window_manager.fileselect_add(self)
        self.op = getattr(context, 'op_ptr', None)         
        return{'RUNNING_MODAL'}                

class PRMAN_OT_set_current_preset_category(bpy.types.Operator):
    bl_idname = "renderman.set_current_preset_category"
    bl_label = "Set current RenderMan Preset category"
    bl_description = "Sets the clicked category to be the current category"

    preset_current_path: StringProperty(default='')

    def execute(self, context):
        hostPrefs = rab.get_host_prefs()
        hostPrefs.setSelectedCategory(self.properties.preset_current_path)
        hostPrefs.saveAllPrefs()

        return {'FINISHED'}  

class PRMAN_OT_add_new_preset_category(bpy.types.Operator):
    bl_idname = "renderman.add_new_preset_category"
    bl_label = "Add New RenderMan Preset Category"
    bl_description = "Adds a new preset category"

    new_name: StringProperty(default="")
    current_path: StringProperty(default="")
    
    def execute(self, context):
        if self.properties.new_name == '':
            return {'FINISHED'}

        hostPrefs = rab.get_host_prefs()
        rel_path = os.path.relpath(self.properties.current_path, hostPrefs.getSelectedLibrary())          
        rel_path = os.path.join(rel_path, self.properties.new_name)
        ral.createCategory(hostPrefs.cfg, rel_path)
        if self.op:
            self.op.dummy_index = -1
            self.op.preset_categories_index = 0         
        return {'FINISHED'}

    def invoke(self, context, event):
        self.op = getattr(context, 'op_ptr', None)               
        return context.window_manager.invoke_props_dialog(self)

    def draw(self, context):
        row = self.layout
        row.prop(self, "new_name", text="New Name:")      


class PRMAN_OT_remove_preset_category(bpy.types.Operator):
    bl_idname = "renderman.remove_preset_category"
    bl_label = "Remove Current Preset Category"
    bl_description = "Remove preset category"

    @classmethod
    def poll(cls, context):
        hostPrefs = rab.get_host_prefs()
        current_category_path = hostPrefs.getSelectedCategory()
        if current_category_path == '':
            return False
        rel_path = os.path.relpath(current_category_path, hostPrefs.getSelectedLibrary())  
        if rel_path in ['EnvironmentMaps', 'Materials', 'LightRigs']:
            return False
        return True    

    def execute(self, context):
        hostPrefs = rab.get_host_prefs()
        current_category_path = hostPrefs.getSelectedCategory()
        rel_path = os.path.relpath(current_category_path, hostPrefs.getSelectedLibrary())  
        ral.deleteCategory(hostPrefs.cfg, rel_path)
        self.op = getattr(context, 'op_ptr', None)
        if self.op:
            self.op.dummy_index = -1
            self.op.preset_categories_index = 0    

        return {'FINISHED'}

class PRMAN_OT_remove_preset(bpy.types.Operator):
    bl_idname = "renderman.remove_preset"
    bl_label = "Remove RenderMan Preset"
    bl_description = "Remove a Preset"

    preset_path: StringProperty()

    def execute(self, context):
        preset_path = self.properties.preset_path
        hostPrefs = rab.get_host_prefs()
        ral.deleteAsset(preset_path)
        hostPrefs.setSelectedPreset('')
        hostPrefs.saveAllPrefs()
        if self.op:
            self.op.preset_categories_index = self.op.preset_categories_index        
        return {'FINISHED'}

    def invoke(self, context, event):
        self.op = getattr(context, 'op_ptr', None)          
        return context.window_manager.invoke_confirm(self, event)

class PRMAN_OT_move_preset(bpy.types.Operator):
    bl_idname = "renderman.move_preset"
    bl_label = "Move RenderMan Preset"
    bl_description = "Move a Preset"

    def get_categories(self, context):
        hostPrefs = rab.get_host_prefs()
        items = []
        for cat in hostPrefs.getAllCategories(asDict=False):
            tokens = cat.split('/')
            level = len(tokens)
            category_name = ''
            for i in range(0, level-1):
                category_name += '    '            
            category_name = '%s%s' % (category_name, tokens[-1])            
            items.append((str(cat), str(cat), ''))
        return items

    preset_path: StringProperty(default='')
    new_category: EnumProperty(items=get_categories, description='New Category', name="New Category")

    def execute(self, context):
        preset_path = self.properties.preset_path
        hostPrefs = rab.get_host_prefs()
        ral.moveAsset(hostPrefs.cfg, preset_path, self.properties.new_category)
        dst = os.path.join(hostPrefs.getSelectedLibrary(), self.properties.new_category)
        hostPrefs.setSelectedPreset(dst)
        hostPrefs.saveAllPrefs()      
        if self.op:
            self.op.preset_categories_index = self.op.preset_categories_index
        return {'FINISHED'}

    def invoke(self, context, event):
        self.op = getattr(context, 'op_ptr', None)     
        return context.window_manager.invoke_props_dialog(self)

    def draw(self, context):
        row = self.layout
        row.prop(self, "new_category")
 
class PRMAN_OT_view_preset_json(bpy.types.Operator):
    bl_idname = "renderman.view_preset_json"
    bl_label = "View Preset JSON"
    bl_description = "View Preset JSON"

    preset_path: StringProperty(default='')
    
    @classmethod
    def poll(cls, context):
        rd = context.scene.render
        return rd.engine == 'PRMAN_RENDER'

    def execute(self, context):
        json_path = self.properties.preset_path
        filepath_utils.view_file(json_path)
        return {'FINISHED'}

class PRMAN_OT_forget_preset_library(bpy.types.Operator):
    bl_idname = "renderman.forget_preset_library"
    bl_label = "Forgot Library"
    bl_description = "Forget the currently selected library"

    library_path: StringProperty(default='')
    
    @classmethod
    def poll(cls, context):
        rd = context.scene.render
        return rd.engine == 'PRMAN_RENDER'

    def execute(self, context):
        self.op = getattr(context, 'op_ptr', None) 
        json_file = os.path.join(self.library_path, 'library.json')
        if not os.path.exists(json_file):
            return {'FINISHED'}

        hostPrefs = rab.get_host_prefs()
        hostPrefs.cfg.removeLibraryFromLibraryList(self.library_path)
        hostPrefs.cfg.setCurrentLibraryByName(None)
        lib_path = hostPrefs.cfg.getCurrentLibraryPath()
        libInfo = hostPrefs.cfg.getCurrentLibraryInfos()
        hostPrefs.cfg.setCurrentLibraryByPath(FilePath(lib_path))
        hostPrefs.setSelectedLibrary(lib_path)       

        hostPrefs.setSelectedPreset('')
        hostPrefs.setSelectedCategory(os.path.join(lib_path, 'EnvironmentMaps'))
        hostPrefs.saveAllPrefs()    

        if self.op:
            self.op.dummy_index = -1
            self.op.preset_categories_index = 0            

        
        return {'FINISHED'}

class PRMAN_OT_select_preset_library(bpy.types.Operator):
    bl_idname = "renderman.select_preset_library"
    bl_label = "Select Library"
    bl_description = "Select a different loaded library."

    def get_libraries(self, context):
        items = []
        hostPrefs = rab.get_host_prefs()
        for p,libinfo in hostPrefs.cfg.libs.items():
            if not os.path.exists(libinfo.getPath()):
                continue
            items.append((p, libinfo.getData('name'), p))    

        return items

    library_paths: EnumProperty(items=get_libraries, name="Select Library")
    
    @classmethod
    def poll(cls, context):
        rd = context.scene.render
        return rd.engine == 'PRMAN_RENDER'

    def execute(self, context):
        json_file = os.path.join(self.library_paths, 'library.json')
        if not os.path.exists(json_file):
            return {'FINISHED'}

        hostPrefs = rab.get_host_prefs()
        hostPrefs.cfg.setCurrentLibraryByPath(FilePath(self.library_paths))
        hostPrefs.setSelectedLibrary(self.library_paths)
      
        hostPrefs.setSelectedPreset('')
        hostPrefs.setSelectedCategory(os.path.join(self.library_paths, 'EnvironmentMaps'))
        hostPrefs.saveAllPrefs()    

        if self.op:
            self.op.dummy_index = -1
            self.op.preset_categories_index = 0         
        
        return {'FINISHED'}        
        
    def invoke(self, context, event):
        self.op = getattr(context, 'op_ptr', None)     
        return context.window_manager.invoke_props_dialog(self)

    def draw(self, context):
        row = self.layout
        row.prop(self, "library_paths")        

classes = [
    PRMAN_OT_init_preset_library,
    PRMAN_OT_set_current_preset_category,
    PRMAN_OT_load_asset_to_scene,
    PRMAN_UL_Presets_Meta_Data_List,
    PRMAN_OT_preset_add_metadata,
    PRMAN_OT_preset_delete_metadata,
    PRMAN_OT_save_asset_to_lib,
    PRMAN_OT_save_lightrig_to_lib,
    PRMAN_OT_save_envmap_to_lib,
    PRMAN_OT_add_new_preset_category,
    PRMAN_OT_remove_preset_category,
    PRMAN_OT_move_preset,
    PRMAN_OT_remove_preset,
    PRMAN_OT_view_preset_json,
    PRMAN_OT_forget_preset_library,
    PRMAN_OT_select_preset_library,
    PRMAN_OT_edit_library_info,
    PRMAN_OT_add_storage_key
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
