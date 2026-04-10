"""HCL Graph Builder Module for TerraVision.

This module builds a graphdict directly from HCL-parsed data without requiring
terraform plan/graph commands. It provides an alternative pipeline for projects
where terraform plan is unavailable or undesirable.

The module reads parsed HCL data from fileparser.read_tfsource() and produces
the same graphdict structure as the traditional tfwrapper pipeline, enabling
downstream processing (add_relations, consolidate_nodes, etc.) to work unchanged.

Usage Example:
    import modules.fileparser as fileparser
    import modules.hcl_graph_builder as hcl_builder
    
    # Parse Terraform files
    tfdata = {}
    tfdata = fileparser.read_tfsource(
        source_list=("./terraform",),
        varfile_list=(),
        annotate="",
        tfdata=tfdata
    )
    
    # Build graph from HCL (alternative to terraform plan/graph)
    tfdata = hcl_builder.build_graphdict_from_hcl(tfdata)
    
    # Now tfdata has graphdict, meta_data, node_list ready for downstream processing
"""

import copy
import re
from typing import Dict, List, Any, Tuple, Set

import modules.helpers as helpers
import modules.provider_detector as provider_detector
import modules.config_loader as config_loader


def build_graphdict_from_hcl(tfdata: Dict[str, Any]) -> Dict[str, Any]:
    """Build graphdict and metadata from HCL-parsed data.
    
    This is the main entry point that creates a complete graph structure
    from parsed Terraform files without needing terraform plan/graph.
    
    Args:
        tfdata: Dictionary populated by fileparser.read_tfsource() containing:
            - all_resource: Parsed resource blocks
            - all_data: Parsed data source blocks
            - all_module: Parsed module blocks
            - module_source_dict: Mapping of module names to source paths
    
    Returns:
        Updated tfdata dictionary with:
            - graphdict: {node_address: [connected_nodes]}
            - meta_data: {node_address: {attributes}}
            - node_list: [node_addresses]
            - hidden: [hidden_node_types]
            - annotations: {} (empty dict)
            - original_graphdict: Deep copy of graphdict
            - original_metadata: Deep copy of meta_data
    """
    # Initialize empty structures
    tfdata["graphdict"] = dict()
    tfdata["meta_data"] = dict()
    tfdata["node_list"] = list()
    tfdata["annotations"] = dict()
    
    # Ensure all_output exists (may already be set by fileparser)
    if "all_output" not in tfdata:
        tfdata["all_output"] = dict()
    
    # Detect provider and load hidden nodes configuration
    tfdata["hidden"] = _get_hidden_nodes(tfdata)
    
    # Extract all resource nodes
    _extract_resource_nodes(tfdata)
    
    # Extract all data source nodes
    _extract_data_source_nodes(tfdata)
    
    # Detect connections by scanning attribute values for references
    _build_connections(tfdata)
    
    # Store original state before downstream processing
    tfdata["original_graphdict"] = copy.deepcopy(tfdata["graphdict"])
    tfdata["original_metadata"] = copy.deepcopy(tfdata["meta_data"])
    
    return tfdata


def _get_hidden_nodes(tfdata: Dict[str, Any]) -> List[str]:
    """Detect provider and return hidden node types.
    
    Args:
        tfdata: Terraform data dictionary with all_resource
    
    Returns:
        List of resource types to hide from diagrams
    """
    try:
        # Detect provider(s) from resources
        detection = provider_detector.detect_providers(tfdata)
        
        if not detection or not detection.get("primary_provider"):
            return []
        
        provider = detection["primary_provider"]
        
        # Store detection result for downstream use
        tfdata["provider_detection"] = detection
        
        config = config_loader.load_config(provider)
        
        # Get provider-specific hidden nodes list
        provider_upper = provider.upper()
        attr_name = f"{provider_upper}_HIDE_NODES"
        
        return getattr(config, attr_name, [])
        
    except Exception:
        # If provider detection or config loading fails, return empty list
        return []


def _extract_resource_nodes(tfdata: Dict[str, Any]) -> None:
    """Extract all resource nodes from all_resource structure.
    
    Populates tfdata["graphdict"], tfdata["meta_data"], and tfdata["node_list"]
    with resource nodes.
    
    Args:
        tfdata: Terraform data dictionary (modified in place)
    """
    if "all_resource" not in tfdata:
        return
    
    module_source_dict = tfdata.get("module_source_dict", {})
    
    # Iterate over all resource files
    for filepath, resource_list in tfdata["all_resource"].items():
        # Determine if this resource is in a module
        module_name = _get_module_name_from_filepath(filepath, module_source_dict)
        
        # Process each resource entry
        for resource_entry in resource_list:
            # Resource entry is a dict like {"aws_vpc": {"main": {...}}}
            for resource_type, resource_instances in resource_entry.items():
                for resource_name, attributes in resource_instances.items():
                    # Build base resource address
                    base_address = f"{resource_type}.{resource_name}"
                    
                    # Add module prefix if applicable
                    if module_name and module_name != "main":
                        base_address = f"module.{module_name}.{base_address}"
                    
                    # Handle count/for_each to create indexed nodes
                    nodes = _expand_resource_nodes(
                        base_address, attributes, module_name or "main"
                    )
                    
                    # Add each node to graph structures
                    for node_address, node_meta in nodes:
                        tfdata["graphdict"][node_address] = []
                        tfdata["meta_data"][node_address] = node_meta
                        tfdata["node_list"].append(node_address)


def _extract_data_source_nodes(tfdata: Dict[str, Any]) -> None:
    """Extract all data source nodes from all_data structure.
    
    Populates tfdata["graphdict"], tfdata["meta_data"], and tfdata["node_list"]
    with data source nodes.
    
    Args:
        tfdata: Terraform data dictionary (modified in place)
    """
    if "all_data" not in tfdata:
        return
    
    module_source_dict = tfdata.get("module_source_dict", {})
    
    # Iterate over all data source files
    for filepath, data_list in tfdata["all_data"].items():
        # Determine if this data source is in a module
        module_name = _get_module_name_from_filepath(filepath, module_source_dict)
        
        # Process each data source entry
        for data_entry in data_list:
            # Data entry is a dict like {"aws_ami": {"latest": {...}}}
            for data_type, data_instances in data_entry.items():
                for data_name, attributes in data_instances.items():
                    # Build base data source address
                    base_address = f"data.{data_type}.{data_name}"
                    
                    # Add module prefix if applicable
                    if module_name and module_name != "main":
                        base_address = f"module.{module_name}.{base_address}"
                    
                    # Handle count/for_each to create indexed nodes
                    nodes = _expand_resource_nodes(
                        base_address, attributes, module_name or "main"
                    )
                    
                    # Add each node to graph structures
                    for node_address, node_meta in nodes:
                        tfdata["graphdict"][node_address] = []
                        tfdata["meta_data"][node_address] = node_meta
                        tfdata["node_list"].append(node_address)


def _get_module_name_from_filepath(
    filepath: str, module_source_dict: Dict[str, Any]
) -> str:
    """Determine module name from file path using module_source_dict.
    
    Args:
        filepath: Path to the Terraform file
        module_source_dict: Mapping of module names to source paths
    
    Returns:
        Module name if filepath is in a module, "main" otherwise
    """
    # Check if filepath matches any module source path
    for module_name, module_info in module_source_dict.items():
        # module_info can be a dict with 'cache_path' or just a string path
        if isinstance(module_info, dict):
            module_path = module_info.get("cache_path", "")
        else:
            module_path = module_info
        
        if module_path and module_path in filepath:
            return module_name
    
    return "main"


def _expand_resource_nodes(
    base_address: str, attributes: Dict[str, Any], module_name: str
) -> List[Tuple[str, Dict[str, Any]]]:
    """Expand resource into multiple nodes if count/for_each is present.
    
    Args:
        base_address: Base resource address (e.g., "aws_instance.web")
        attributes: Resource attributes dictionary
        module_name: Module name for metadata
    
    Returns:
        List of (node_address, metadata) tuples
    """
    nodes = []
    
    # Check for count attribute
    if "count" in attributes:
        count_value = attributes["count"]
        
        # If count is a literal integer, create that many nodes
        if isinstance(count_value, int):
            for i in range(count_value):
                node_address = f"{base_address}~{i + 1}"
                node_meta = _build_node_metadata(attributes, module_name)
                nodes.append((node_address, node_meta))
        else:
            # Dynamic count - create single node without suffix
            node_meta = _build_node_metadata(attributes, module_name)
            nodes.append((base_address, node_meta))
    
    # Check for for_each attribute
    elif "for_each" in attributes:
        for_each_value = attributes["for_each"]
        
        # If for_each is a literal dict/set, create nodes for each key
        if isinstance(for_each_value, dict):
            for key in for_each_value.keys():
                node_address = f"{base_address}[{key}]"
                node_meta = _build_node_metadata(attributes, module_name)
                nodes.append((node_address, node_meta))
        elif isinstance(for_each_value, list):
            for item in for_each_value:
                key = str(item)
                node_address = f"{base_address}[{key}]"
                node_meta = _build_node_metadata(attributes, module_name)
                nodes.append((node_address, node_meta))
        else:
            # Dynamic for_each - create single node without suffix
            node_meta = _build_node_metadata(attributes, module_name)
            nodes.append((base_address, node_meta))
    
    else:
        # No count/for_each - single node
        node_meta = _build_node_metadata(attributes, module_name)
        nodes.append((base_address, node_meta))
    
    return nodes


def _build_node_metadata(
    attributes: Dict[str, Any], module_name: str
) -> Dict[str, Any]:
    """Build metadata dictionary for a node.
    
    Args:
        attributes: Resource attributes from HCL
        module_name: Module name to add to metadata
    
    Returns:
        Metadata dictionary with module field added
    """
    # Create a copy of attributes to avoid mutating original
    metadata = dict(attributes)
    
    # Add module field
    metadata["module"] = module_name
    
    return metadata


def _build_connections(tfdata: Dict[str, Any]) -> None:
    """Build connections between nodes by scanning for resource references.
    
    Scans all node metadata for references to other nodes and populates
    the graphdict with discovered connections.
    
    Args:
        tfdata: Terraform data dictionary (modified in place)
    """
    nodes = tfdata["node_list"]
    hidden = tfdata["hidden"]
    
    # Scan each node for references to other nodes
    for node in nodes:
        if node not in tfdata["meta_data"]:
            continue
        
        metadata = tfdata["meta_data"][node]
        
        # Recursively scan all attribute values for references
        refs = _scan_for_references(metadata, nodes, node)
        
        # Add connections for each found reference
        for target in refs:
            # Skip hidden nodes
            if target in hidden or node in hidden:
                continue
            
            # Add connection if not already present
            if target not in tfdata["graphdict"][node]:
                tfdata["graphdict"][node].append(target)


def _scan_for_references(
    obj: Any, nodes: List[str], source_node: str
) -> Set[str]:
    """Recursively scan an object for Terraform resource references.
    
    Args:
        obj: Object to scan (can be dict, list, string, etc.)
        nodes: List of all known node addresses
        source_node: Node doing the referencing (for module scoping)
    
    Returns:
        Set of referenced node addresses
    """
    refs = set()
    
    if isinstance(obj, dict):
        # Scan all values in dictionary
        for value in obj.values():
            refs.update(_scan_for_references(value, nodes, source_node))
    
    elif isinstance(obj, list):
        # Scan all items in list
        for item in obj:
            refs.update(_scan_for_references(item, nodes, source_node))
    
    elif isinstance(obj, str):
        # Scan string for resource references
        refs.update(_find_references_in_string(obj, nodes, source_node))
    
    return refs


def _find_references_in_string(
    text: str, nodes: List[str], source_node: str
) -> Set[str]:
    """Find Terraform resource references in a string.
    
    Detects patterns like:
    - ${aws_vpc.main.id} or aws_vpc.main.id
    - ${data.aws_ami.latest.id}
    - ${module.vpc.vpc_id}
    - module.vpc.aws_subnet.public
    
    Args:
        text: String to scan for references
        source_node: Node doing the referencing (for module scoping)
        nodes: List of all known node addresses
    
    Returns:
        Set of referenced node addresses
    """
    refs = set()
    
    # Extract Terraform resource references using helper
    extracted = helpers.extract_terraform_resource(text)
    
    # Match extracted references to known nodes
    for ref in extracted:
        # Clean up any remaining interpolation syntax
        ref_clean = helpers.cleanup_curlies(ref)
        
        # Find matching nodes
        for node in nodes:
            if ref_clean in node or ref in node:
                refs.add(node)
    
    # Also look for data source references (data.type.name)
    data_pattern = r'data\.(\w+)\.(\w+)'
    data_matches = re.findall(data_pattern, text)
    for data_type, data_name in data_matches:
        data_ref = f"data.{data_type}.{data_name}"
        for node in nodes:
            if data_ref in node:
                refs.add(node)
    
    # Look for module references (module.name.output or module.name.resource)
    # This handles both module outputs and resources within modules
    module_pattern = r'module\.(\w+)\.(\w+)'
    module_matches = re.findall(module_pattern, text)
    for module_name, output_or_resource in module_matches:
        # Try to find matching module resource nodes
        module_prefix = f"module.{module_name}."
        for node in nodes:
            if node.startswith(module_prefix):
                # Check if the reference matches this node
                if output_or_resource in node:
                    refs.add(node)
    
    # Handle count.index references - normalize by removing the placeholder
    # e.g., ${aws_subnet.public[count.index].id} should match aws_subnet.public
    # Also handle bare count.index (without brackets) used in functions like
    # element(var.subnets, count.index) — very common in Terraform modules
    if "count.index" in text:
        # First strip bracketed form, then strip any remaining bare occurrences
        normalized = text.replace("[count.index]", "").replace("count.index", "0")
        # Guard against infinite recursion: only recurse if normalization changed the text
        if normalized != text:
            refs.update(_find_references_in_string(normalized, nodes, source_node))
    
    # Handle numbered/indexed references (e.g., resource[0], resource~1)
    # Extract base resource name and match against numbered nodes
    numbered_pattern = r'(\w+_\w+\.\w+)(?:\[(\d+)\]|~(\d+))'
    numbered_matches = re.findall(numbered_pattern, text)
    for base_ref, idx1, idx2 in numbered_matches:
        index = idx1 or idx2
        if index:
            # Try both bracket and tilde notation
            ref_bracket = f"{base_ref}[{index}]"
            ref_tilde = f"{base_ref}~{int(index) + 1}"
            for node in nodes:
                if ref_bracket in node or ref_tilde in node:
                    refs.add(node)
    
    return refs
