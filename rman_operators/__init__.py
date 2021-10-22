from . import rman_operators_printer
from . import rman_operators_view3d
from . import rman_operators_render
from . import rman_operators_rib
from . import rman_operators_nodetree
from . import rman_operators_collections
from . import rman_operators_editors
from . import rman_operators_stylized
from . import rman_operators_mesh
from . import rman_operators_volumes
from . import rman_operators_utils

def register():
    rman_operators_printer.register()
    rman_operators_view3d.register()
    rman_operators_render.register()
    rman_operators_rib.register()
    rman_operators_nodetree.register()
    rman_operators_collections.register()
    rman_operators_editors.register()
    rman_operators_stylized.register()
    rman_operators_mesh.register()
    rman_operators_volumes.register()
    rman_operators_utils.register()

def unregister():
    rman_operators_printer.unregister()
    rman_operators_view3d.unregister()
    rman_operators_render.unregister()
    rman_operators_rib.unregister()
    rman_operators_nodetree.unregister()
    rman_operators_collections.unregister()
    rman_operators_editors.unregister()
    rman_operators_stylized.unregister()
    rman_operators_mesh.unregister()
    rman_operators_volumes.unregister()
    rman_operators_utils.unregister()