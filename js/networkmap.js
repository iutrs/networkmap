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

// Arrays used by vis to generate the network graph
var visNodes = []
var visEdges = []

// Arrays used to keep information in memory
var myVlans = []

var network = null;

function draw() {
    createNodes();
    createEdges();

    var container = document.getElementById('networkmap');

    var data = {
        nodes: visNodes,
        edges: visEdges
    };

    var options = {
        stabilize: true,
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

    network = new vis.Network(container, data, options);
    network.freezeSimulation(true)

    addEventsListeners()
    createVlansList()
}

/**
 * Adding the events listeners
 */
function addEventsListeners() {
    network.on('select', function (properties) {
        var content = "<b>No selection</b>"

        if (properties.nodes.length > 0) {
            device = getDevice(properties.nodes)
            content = buildNodeDescription(device)
        }

        document.getElementById('deviceInfo').innerHTML = content + "<hr>";
    });
}

/**
 * Create the nodes used by vis.js
 */
function createNodes() {
    for (var i = 0; i < devices.length; i++) {
        device = devices[i]

        color = '#2B7CE9';
        if (device.interfaces.length == 0) {
            color = '#C5000B';
        }

        visNodes.push(
        {
            'id': device.mac_address,
            'label': device.system_name + "\n" + device.ip_address,
            'shape': 'square',
            'color': color,
            'title': undefined,
            'value': device.interfaces.length + 1,
            'mass': device.interfaces.length + 1
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
            int = device.interfaces[j]
            link = [device.mac_address, int.remote_mac_address]

            if (nodeExists(int.remote_mac_address) && !linkExists(link)) {
                visEdges.push(
                    {
                        'from': link[0],
                        'to': link[1],
                        'style': 'line',
                        'color': undefined,
                        'width': undefined,
                        'length': undefined,
                        'value': undefined,
                        'title': undefined,
                        'label': int.remote_port + " -> " + int.local_port,
                        'labelAlignment' : 'line-center'
                    });
            }
            
            for (var k = 0; k < int.vlans.length; k++) {
                vlan = int.vlans[k]
                if (!vlanExists(vlan)) {
                    myVlans.push(vlan)
                }
            }
            myVlans.sort(function(a, b){return parseInt(a.identifier) > parseInt(b.identifier)})
        }
    }

}

/**
 * Generates a dropdown list containing all the vlans identifier
 */
function createVlansList() {
    var options = "<b>Vlan:</b> <select id='vlansDropDown' onchange='displayVlanInfo()'>"
    for (var i = 0; i < myVlans.length; i++) {
        options += "<option value='" + myVlans[i].identifier + "'>" + myVlans[i].identifier + "</option>";
    }
    options += "</select></br>";
    document.getElementById("vlanInfo").innerHTML += options;
    
    displayVlanInfo();
}

/**
 * Displays the information of the selected vlan
 */
function displayVlanInfo() {
    var vlans = document.getElementById("vlansDropDown");
    vlan = getVlan(vlans.options[vlans.selectedIndex].value);

    info = "<b>Name:</b> " + vlan.name + "</br>";
    info += "<b>Mode:</b> " + vlan.mode + "</br>";
    info += "<b>Status:</b> " + vlan.status + "<hr>";

    document.getElementById("vlanInfo").innerHTML += info;
}

/**
 * Return the vlan associated to the id
 */
function getVlan(id) {
    for (var i = 0; i < myVlans.length; i++) {
        if (myVlans[i].identifier == id) {
            return myVlans[i]
        }
    }
}

// Create the nodes used by vis.js
function getDevice(mac) {
    for (var i = 0; i < devices.length; i++) {
        if (devices[i].mac_address == mac) {
            return devices[i]
        }
    }
}

/**
 * Verifies whether a node already exist or not
 */
function nodeExists(id) {
    for (var i = 0; i < visNodes.length; i++) {
        if (visNodes[i].id == id) {
            return true
        }
    }
}

/**
 * Verifies whether a link already exist or not
 */
function linkExists(link) {
    for (var i = 0; i < visEdges.length; i++) {
        from = visEdges[i].from
        to = visEdges[i].to
        if ((from == link[0] && to == link[1]) ||
            (from == link[1] && to == link[0])) {
            return true
        }
    }
}

/**
 * Verifies whether a vlan already exist or not
 */
function vlanExists(vlan) {
    for (var i = 0; i < myVlans.length; i++) {
        if (myVlans[i].identifier == vlan.identifier) {
            return true
        }
    }
}

/**
 * Builds node description when hovering
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
        "<b>Connected ports:</b></br>" + buildConnectedPortsList(device)
    )
}

/**
 * Builds device's connected ports list
 */
function buildConnectedPortsList(device) {

    var connectedPorts = "";
    var otherCount = 0

    for (var i = 0; i < device.interfaces.length; i++) {
        var int = device.interfaces[i];
        
        if (int.remote_system_name == "") {
            otherCount++;
        }
        else {
            var line = int.local_port + " --> " + 
                int.remote_port + " (" +
                int.remote_system_name + ")</br>";
                
            connectedPorts += line;
        }
    }

    if (otherCount > 0) {
        connectedPorts += "<b>Other connections:</b> " + otherCount
    }

    return connectedPorts != "" ? connectedPorts : ""; 
}
