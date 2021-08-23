from ..rman_constants import RFB_ARRAYS_MAX_LEN, __RMAN_SOCKET_MAP__
from .shadergraph_utils import has_lobe_enable_props

def update_inputs(node):
    if node.bl_idname == 'PxrMeshLightLightNode':
        return
    for prop_name in node.prop_names:
        page_name = prop_name
        if node.prop_meta[page_name]['renderman_type'] == 'page':
            for prop_name in getattr(node, page_name):
                if prop_name.startswith('enable'):
                    recursive_enable_inputs(node, getattr(
                        node, page_name), getattr(node, prop_name))
                    break

def recursive_enable_inputs(node, prop_names, enable=True):
    for prop_name in prop_names:
        if type(prop_name) == str and node.prop_meta[prop_name]['renderman_type'] == 'page':
            recursive_enable_inputs(node, getattr(node, prop_name), enable)
        elif hasattr(node, 'inputs') and prop_name in node.inputs:
            node.inputs[prop_name].hide = not enable
        else:
            continue

def find_enable_param(params):
    for prop_name in params:
        if prop_name.startswith('enable'):
            return prop_name


def node_add_inputs(node, node_name, prop_names, first_level=True, label_prefix='', remove=False):
    ''' Add new input sockets to this ShadingNode
    '''

    for name in prop_names:
        meta = node.prop_meta[name]
        param_type = meta['renderman_type']
        param_type = getattr(meta, 'renderman_array_type', param_type)

        if name in node.inputs.keys() and remove:
            node.inputs.remove(node.inputs[name])
            continue
        elif name in node.inputs.keys():
            continue

        # if this is a page recursively add inputs
        if 'renderman_type' in meta and meta['renderman_type'] == 'page':
            if first_level and has_lobe_enable_props(node) and name != 'Globals':
                # add these
                enable_param = find_enable_param(getattr(node, name))
                if enable_param and getattr(node, enable_param):
                    node_add_inputs(node, node_name, getattr(node, name),
                                    label_prefix=name + ' ',
                                    first_level=False)
                else:
                    node_add_inputs(node, node_name, getattr(node, name),
                                    label_prefix=name + ' ',
                                    first_level=False, remove=True)
                continue

            else:
                node_add_inputs(node, node_name, getattr(node, name),
                                first_level=first_level,
                                label_prefix=label_prefix, remove=remove)
                continue
        elif 'renderman_type' in meta and meta['renderman_type'] == 'array':
            arraylen = getattr(node, '%s_arraylen' % name)
            sub_prop_names = getattr(node, name)
            sub_prop_names = sub_prop_names[:arraylen]
            node_add_inputs(node, node_name, sub_prop_names,
                label_prefix='',
                first_level=False, remove=False)
            continue

        if remove:
            continue
        # # if this is not connectable don't add socket
        if param_type not in __RMAN_SOCKET_MAP__:
            continue
        if '__noconnection' in meta and meta['__noconnection']:
            continue

        param_name = name

        param_label = label_prefix + meta.get('label', param_name)
        socket = node.inputs.new(
            __RMAN_SOCKET_MAP__[param_type], param_name, identifier=param_label)
        socket.link_limit = 1
        #socket.default_value = meta['default_value']

        if param_type in ['struct', 'normal', 'vector', 'vstruct', 'void']:
            socket.hide_value = True
            if param_type == 'struct':
                struct_name = meta.get('struct_name', 'Manifold')
                socket.struct_name = struct_name

    update_inputs(node)


# add output sockets
def node_add_outputs(node):
    for name, meta in node.output_meta.items():
        rman_type = meta['renderman_type']
        is_vstruct = meta.get('vstruct', False)
        if rman_type in __RMAN_SOCKET_MAP__ and 'vstructmember' not in meta:
            if is_vstruct:
                rman_type = 'vstruct'
            socket = node.outputs.new(__RMAN_SOCKET_MAP__[rman_type], name)
            socket.renderman_type = rman_type
            if rman_type == 'struct':
                struct_name = meta.get('struct_name', 'Manifold')
                socket.struct_name = struct_name