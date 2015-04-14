const jsonFile = "devices.json"
var devices = null;

// The JSON must be fully loaded before onload() happens for calling draw() on 'devices'  
$.ajaxSetup({
    async: false
});

// Reading the JSON file containing the devices' informations
$.getJSON(jsonFile, function(json) {
    devices = json;
});

// The objects used by vis
var network = null;
var nodes = []
var edges = []

// Arrays used to keep information in memory
var myVlans = []

// Objects colors (for further customization)
var linkDefaultColor = undefined
var vlanDiffusionColor = "#00D000"
var vlanIncoherenceColor = "#FF0000"

var nodeDefaultColor = "#2B7CE9"
var unaccessibleSwitchColor = "#C5000B"
var serverDefaultColor = "#00FFBF"
var vmDefaultColor = "#FF9900"

// General options
var showvms = false;

function draw() {

    if (devices == null) {
        errorMessage = "<font color='red'>Could not find '" + jsonFile + "'.</font>"
        document.getElementById('networkmap').innerHTML = errorMessage
    }

    createNodes();
    createEdges();

    var data = {
        nodes: nodes,
        edges: edges
    };

    var options = {
        stabilize: true,
        navigation: true,
        selectable: true,
        smoothCurves: false,
        physics: {
            barnesHut: {
                enabled: true,
                gravitationalConstant: -2500,
                centralGravity: 0.5,
                springLength: 150,
                springConstant: 0.1,
                damping: 1
            },
            repulsion: {
                centralGravity: 0.5,
                springLength: 150,
                springConstant: 0.1,
                nodeDistance: 75,
                damping: 1
            }
        }
    };

    var container = document.getElementById('networkmap');

    network = new vis.Network(container, data, options);
    network.freezeSimulation(true);

    addGeneralOptionsControls();
    addEventsListeners();
    createVlansList();
}

/**
 * Create the nodes used by vis.js
 */
function createNodes() {
    for (var i = 0; i < devices.length; i++) {
        var device = devices[i]

        var color = nodeDefaultColor;

        if (device.interfaces.length == 0) {
            color = unaccessibleSwitchColor;
        }

        nodes.push(
        {
            'id': device.mac_address,
            'label': device.system_name + "\n" + device.ip_address,
            'shape': 'square',
            'color': color,
            'title': undefined,
            'value': device.interfaces.length + 1,
            'mass': device.interfaces.length + 1
        });

        if (device.virtual_machines.length > 0 && showvms) {
            createVmsNodes(device)
        }
        
    }
}

/**
 * Add nodes and links for the virtual machines
 */
function createVmsNodes(device) {
    for (var j = 0; j < device.virtual_machines.length; j++) {
        var vm = device.virtual_machines[j];
        nodes.push(
        {
            'id': device.mac_address + "/" + vm.name,
            'label': vm.name,
            'shape': 'square',
            'color': vmDefaultColor,
            'title': undefined,
            'value': 1,
            'mass': 1
        });

        edges.push(
        {
            'from': device.mac_address,
            'to': device.mac_address + "/" + vm.name,
            'style': 'line',
            'color': vmDefaultColor,
            'width': 2,
            'length': undefined,
            'value': undefined,
            'title': undefined,
            'label': undefined
        });
    }
}

/**
 * Create the edges used by vis.js
 */
function createEdges() {
    for (var i = 0; i < devices.length; i++) {
        device = devices[i]

        for (var j = 0; j < device.interfaces.length; j++) {
            var int = device.interfaces[j]
            var link = [device.mac_address, int.remote_mac_address]

            if (nodeExists(int.remote_mac_address) && !edgeExists(link)) {
                edges.push(
                    {
                        'from': link[0],
                        'to': link[1],
                        'style': 'line',
                        'color': undefined,
                        'width': 2,
                        'length': undefined,
                        'value': undefined,
                        'title': undefined,
                        'labelFrom': int.local_port,
                        'labelTo': int.remote_port
                    });
            }

            for (var k = 0; k < int.vlans.length; k++) {
                var vlan = int.vlans[k]
                if (!vlanExists(vlan)) {
                    myVlans.push(vlan)
                }
            }
        }
    }
    myVlans.sort(function(a, b){return parseInt(a.identifier) > parseInt(b.identifier)})
}

/**
 * Adding the general options
 */
function addGeneralOptionsControls() {
    var content = "<input type='checkbox' name='showvms' value='showvms' "
    content += showvms ? "checked " : " "
    content += "onchange='toggleCheckbox(this);'> Show virtual machines <br>"

    document.getElementById('general').innerHTML = content + "<hr>";
}

/**
 * Handling checkbox clicking
 */
function toggleCheckbox(element)
{
    //TODO Find a way to make it load faster
    if (element.name == "showvms") {
        showvms = element.checked;
        nodes = [];
        edges = [];
        draw();
    }
}

/**
 * Adding the events listeners
 */
function addEventsListeners() {
    network.on('select', onSelect);
}

/*
 * Manage the event when an object is selected
 */
function onSelect(properties) {
    var content = "<b>No selection</b>"

    if (properties.nodes.length > 0) {
        content = onNodeSelect(properties.nodes);
    }
    else if (properties.edges.length > 0) {
        content = onEdgeSelect(properties.edges);
    }

    document.getElementById('selectionInfo').innerHTML = content + "<hr>";
}

/*
 * Manage the event when a node is selected
 */
function onNodeSelect(node) {
    var device = getDevice(node);
    return buildNodeDescription(device);
}

/*
 * Manage the event when an edge is selected
 */
function onEdgeSelect(edge) {
    var edge = getEdge(edge);
    return buildEdgeDescription(edge);
}

/**
 * Builds node description
 */
function buildNodeDescription(device) {
    ip = "?"
    ip_type = "IP"

    if (device.ip_address) {
        ip = device.ip_address
    }
    if (device.ip_address_type) {
        ip_type = device.ip_address_type.toUpperCase()
    }

    return (
        "<b>Name:</b> " + device.system_name + "</br>" +
        "<b>Description:</b> " + device.system_description + "</br>" +
        "<b>" + ip_type + ":</b> " + ip + "</br>" +
        "<b>MAC:</b> " + device.mac_address + "</br>" +
        "<b>Capabilities:</b> " + device.enabled_capabilities + "</br>" +
        buildConnectedPortsList(device) + 
        buildVirtualMachinesList(device)
    )
}

/**
 * Builds device's connected ports list
 */
function buildConnectedPortsList(device) {

    var connectedPorts = "<b>Connected interfaces:</b></br>";
    var otherCount = 0

    for (var i = 0; i < device.interfaces.length; i++) {
        var int = device.interfaces[i];

        if (int.remote_system_name == "") {
            otherCount++;
        }
        else {
            var line = int.local_port + " --> ";
            line += int.remote_port + " (";
            line += int.remote_system_name + ")</br>";
            connectedPorts += line;
        }
    }

    if (otherCount > 0) {
        connectedPorts += "<b>Other connections:</b> " + otherCount + "</br>"
    }

    return device.interfaces.length > 0 ? connectedPorts : ""; 
}

/**
 * Builds device's virtual machines list
 */
function buildVirtualMachinesList(device) {

    var output = "<b>Virtual machines:</b></br>";

    for (var i = 0; i < device.virtual_machines.length; i++) {
        var vm = device.virtual_machines[i];

        var line = vm.identifier + " | <b>" + vm.name + "</b> (" + vm.state + ")";
        output += line + "</br>";
    }

    return device.virtual_machines.length > 0 ? output : ""; 
}

/**
 * Buils edge description
 */
function buildEdgeDescription(edge) {
    var macAdressFrom = edge.from;
    var macAdressTo = edge.to;

    var deviceFrom = getDevice(macAdressFrom);
    var deviceTo = getDevice(macAdressTo);

    var interfaceFrom = getInterfaceConnectedTo(deviceFrom, macAdressTo);
    var interfaceTo = getInterfaceConnectedTo(deviceTo, macAdressFrom);

    var vlansFrom = (interfaceFrom != null) ? interfaceFrom.vlans : [];
    var vlansTo = (interfaceTo != null) ? interfaceTo.vlans : [];

    var contentFrom = "<b>" + deviceFrom.system_name + "</b></br>";
    var contentTo = "<b>" + deviceTo.system_name + "</b></br>";

    contentFrom += (interfaceFrom != null) ? "" : "No vlans could be found.";
    contentTo += (interfaceTo != null) ? "" : "No vlans could be found.";

    var differences = vlansIdentifiers(vlansTo).diff(vlansIdentifiers(vlansFrom))

    if (vlansFrom.length > 0) {
        contentFrom += "Vlans on <b>" + interfaceFrom.local_port + "</b>&nbsp:</br>"
        contentFrom += vlansToString(vlansFrom, macAdressFrom, differences);
    }

    if (vlansTo.length > 0) {
        contentTo += "Vlans on <b>" + interfaceTo.local_port + "</b>&nbsp:</br>"
        contentTo += vlansToString(vlansTo, macAdressTo, differences);
    }

    var content = contentFrom + "</br>" + contentTo + "</br>"

    return content;
}

/*
 * Make an array of the vlans identifiers only
 */
function vlansIdentifiers(vlans) {
    var identifiers = []
    for (var i = 0; i < vlans.length; i++) {
        identifiers.push(vlans[i].identifier);
    }
    return identifiers;
}

/*
 * Stringify a list of vlans with their identifiers only
 */
function vlansToString(vlans, str, differences) {
    var string = ""
    for (var i = 0; i < vlans.length; i++) {
        var vlan = vlans[i]

        var color = (differences.indexOf(vlan.identifier) >= 0) ? vlanIncoherenceColor : "black"

        var ref = str + "/vlan" + vlan.identifier
        string += vlansInfo(vlan, ref, color)
        string += (i < vlans.length -1) ? ", " : ""
    }
    return string;
}

/*
 * Generate vlan info (tooltip + div)
 */
function vlansInfo(vlan, ref, color) {
    // tooltip
    var string = "<a href='#" + ref + "' title='"
    string += "Name: " + vlan.name + "\n";
    string += "Mode: " + vlan.mode + "\n";
    string += "Status: " + vlan.status + "'";

    // <div> toggle
    string += " onclick=\"toggle('" + ref + "');\">"
    string += "<font color='" + color + "'>" + vlan.identifier + "</font></a>"
    string += "<small><div id='" + ref + "' style='display: none;'> "
    string += "<font color='" + color + "'>"
    string += "(<b>Name:</b> " + vlan.name + ", ";
    string += "<b>Mode:</b> " + vlan.mode + ", ";
    string += "<b>Status:</b> " + vlan.status + ")</font></div></small>";

    return string;
}

/*
 * Show or hide a div by its id
 */
function toggle(divId) {
   if (document.getElementById(divId)) {
      if (document.getElementById(divId).style.display == 'none') {
         document.getElementById(divId).style.display = 'inline';
      }
      else {
         document.getElementById(divId).style.display = 'none';
      }
   }
}

/**
 * Generates a dropdown list containing all the vlans identifier
 */
function createVlansList() {
    var options = "<b>Vlan:</b> <select id='vlansDropDown' onchange='displayVlanInfo()'>"
    options += "<option value='noVlanSelection'></option>" 

    for (var i = 0; i < myVlans.length; i++) {
        options += "<option value='" + myVlans[i].identifier + "'>";
        options += myVlans[i].identifier + "</option>";
    }
    options += "</select></br>";
    document.getElementById("vlanSelect").innerHTML = options;

    displayVlanInfo();
}

/**
 * Display the information of the selected vlan
 */
function displayVlanInfo() {
    var vlans = document.getElementById("vlansDropDown");
    var vlan = getVlan(vlans.options[vlans.selectedIndex].value);

    var id = -1;
    var info = "";

    if (vlan != null) {
        id = vlan.identifier;
        info += "<span><b>Name:</b> " + vlan.name + "</span><br>";
        info += "<rect style='background:" + vlanDiffusionColor + ";'></rect>";
        info += "<span><b>&nbspDiffusion</b></span></br>";
        info += "<rect style='background:" + vlanIncoherenceColor + ";'></rect>";
        info += "<span><b>&nbspIncoherences</b></span>"
    }

    document.getElementById("vlanInfo").innerHTML = info + "<hr>";

    highlightVlanDiffusion(id);
}

/**
 * Highlights the diffusion of the selected vlan
 */
function highlightVlanDiffusion(id) {

    for (var i = 0; i < edges.length; i++) {
        var edge = edges[i];

        var macAdressFrom = edge.from;
        var macAdressTo = edge.to;

        var deviceFrom = getDevice(macAdressFrom);
        var deviceTo = getDevice(macAdressTo);

        var interfaceFrom = getInterfaceConnectedTo(deviceFrom, macAdressTo);
        var interfaceTo = getInterfaceConnectedTo(deviceTo, macAdressFrom);

        if (interfaceFrom != null && interfaceTo != null) {
            vlansFrom = vlansIdentifiers(interfaceFrom.vlans);
            vlansTo = vlansIdentifiers(interfaceTo.vlans);

            var coherent = vlansFrom.indexOf(id) != -1 && vlansTo.indexOf(id) != -1
            var notApplicable = vlansFrom.indexOf(id) == -1 && vlansTo.indexOf(id) == -1

            if (coherent) {
                edge.width = 8;
                edge.color = vlanDiffusionColor;
            }
            else if (notApplicable) {
                edge.width = 2;
                edge.color = linkDefaultColor; 
            }
            else {
                edge.width = 8;
                edge.color = vlanIncoherenceColor;
            }
        }
    }

    resetData();
}

/*
 * Get the interface connected from a device to another known mac address
 */
function getInterfaceConnectedTo(device, macAdress) {
    if (device == undefined) {
        return null
    }

    for (var i = 0; i < device.interfaces.length; i++) {
        var int = device.interfaces[i]
        if (int.remote_mac_address == macAdress) {
            return int;
        }
    }
}

/**
 * Get a device from its mac address
 */
function getDevice(mac) {
    for (var i = 0; i < devices.length; i++) {
        if (devices[i].mac_address == mac) {
            return devices[i];
        }
    }
}

/**
 * Get a vlan from its id
 */
function getVlan(id) {
    for (var i = 0; i < myVlans.length; i++) {
        if (myVlans[i].identifier == id) {
            return myVlans[i];
        }
    }
}


/**
 * Get a node from its id
 */
function getNode(id) {
    for (var i = 0; i < nodes.length; i++) {
        if (nodes[i].id == id) {
            return nodes[i];
        }
    }
}

/**
 * Get an edge from its id
 */
function getEdge(id) {
    for (var i = 0; i < edges.length; i++) {
        if (edges[i].id == id) {
            return edges[i];
        }
    }
}

/**
 * Verifies whether a vlan already exist or not
 */
function vlanExists(vlan) {
    return getVlan(vlan.identifier) != null;
}

/**
 * Verifies whether a node already exist or not
 */
function nodeExists(id) {
    return getNode(id) != null;
}

/**
 * Verifies whether a link already exist or not
 */
function edgeExists(link) {
    for (var i = 0; i < edges.length; i++) {
        from = edges[i].from
        to = edges[i].to
        if ((from == link[0] && to == link[1]) ||
            (from == link[1] && to == link[0])) {
            return true;
        }
    }
}

function resetData() {
    network.freezeSimulation(false);
    network.setData({nodes: nodes, edges: edges});
    network.freezeSimulation(true);
}
/*
 * Returns the differences between two arrays
 */
Array.prototype.diff = function(other) {
    diff = []
    for (var i = 0; i < this.length; i++) {
        obj = this[i]
        if (other.indexOf(obj) == -1) {
            diff.push(obj)
        }
    }
    for (var i = 0; i < other.length; i++) {
        obj = other[i]
        if (this.indexOf(obj) == -1 && diff.indexOf(obj) == -1) {
            diff.push(obj)
        }
    }
    return diff;
};
