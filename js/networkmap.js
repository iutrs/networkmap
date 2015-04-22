const jsonFile = "devices.json";
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
var nodes = [];
var edges = [];

// Arrays used to keep information in memory
var myVlans = {};

// Objects colors (for further customization)
var linkDefaultColor = undefined;
var vlanDiffusionColor = get("vlanDiffusionColor") || "#00D000";
var vlanIncoherenceColor = get("vlanIncoherenceColor") || "#FF0000";

var nodeDefaultColor = "#2B7CE9";
var unaccessibleSwitchColor = "#C5000B";
var serverDefaultColor = "#00FFBF";
var vmDefaultColor = "#FF9900";

// General options
var showvms = false;
var freezeSimulation = true;

var focusedOnNode = false;

var selectedVlanId = get("selectedVlanId") || "noVlanSelection";

// Loading the nodes' position
var nodesPosition = getPositions();

function draw() {
    if (devices == null) {
        errorMessage = "<font color='red'>Could not find '" + jsonFile + "'.</font>";
        document.getElementById('networkmap').innerHTML = errorMessage;
    }

    nodes = [];
    edges = [];
    nodesPosition = getPositions();

    var data = {
        nodes: createNodes(),
        edges: createEdges()
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
    nodesPosition = network.getPositions();

    addSearchOptions();
    addGeneralOptions();

    addEventsListeners();

    createVlansList();
}

/**
 * Create the nodes used by vis.js
 */
function createNodes() {
    for (var i = 0; i < devices.length; i++) {
        var device = devices[i];

        var color = nodeDefaultColor;

        var interfacesLength = Object.keys(device.interfaces).length
        if (interfacesLength == 0) {
            color = unaccessibleSwitchColor;
        }
        else if (device.system_description.contains("Linux")) {
            color = serverDefaultColor;
        }

        posX = undefined;
        posY = undefined;

        storedPos = getPosition(device.mac_address);
        if (storedPos) {
            posX = storedPos[0];
            posY = storedPos[1];
        }

        nodes.push(
        {
            'id': device.mac_address,
            'label': device.system_name + "\n" + device.ip_address,
            'shape': 'square',
            'color': color,
            'value': interfacesLength + 1,
            'mass': interfacesLength + 1,
            'x': posX,
            'y': posY,
            'allowedToMoveX': posX == undefined,
            'allowedToMoveY': posX == undefined
        });

        if (device.virtual_machines.length > 0 && this.showvms) {
            createVmsNodes(device);
        }
    }
    return nodes;
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
        });
    }
    return nodes;
}

/**
 * Create the edges used by vis.js
 */
function createEdges() {
    for (var i = 0; i < devices.length; i++) {
        device = devices[i];

        for (var index in device.interfaces) {
            var int = device.interfaces[index];
            var link = [device.mac_address, int.remote_mac_address];

            if (nodeExists(int.remote_mac_address) && !edgeExists(link)) {
                edges.push(
                    {
                        'from': link[0],
                        'to': link[1],
                        'style': 'line',
                        'width': 2,
                        'labelFrom': int.local_port,
                        'labelTo': int.remote_port
                    });
            }

            for (var index in int.vlans) {
                if (!(index in myVlans)) {
                    myVlans[index] = int.vlans[index]
                }
            }
        }
    }

    return edges;
}

/*
 * Add the html controls to search and focus on a specific device/node
 */
function addSearchOptions() {

    var txtSearch = "<input id='txtSearch' class='typeahead' type='text'";
    txtSearch += " placeholder='Find a device' onchange='selectNode(undefined, false)'>";
    var btnFocus = "<button id='btnFocus' onclick='toggleFocusOnNode()'>Focus</button>";

    var content = txtSearch + btnFocus;

    document.getElementById('deviceSearch').innerHTML = content + "<hr>";

    prepareSearchEngine();
}

/*
 * Select the node associated the specified system name.
 * If no argument is given (or undefined), it will try to select the node
 * with the system name entered in the search box.
 */
function toggleFocusOnNode() {
    if (focusedOnNode) {
        network.zoomExtent({duration:0});
    }
    else {
        selectNode(undefined, true);
    }

    focusedOnNode = !focusedOnNode;
}

/*
 * Select the node associated the specified system name.
 * If no argument is given (or undefined), it will try to select the node
 * with the system name entered in the search box.
 */
function selectNode(sysName, zoom) {
    if (sysName == undefined) {
        sysName = document.getElementById('txtSearch').value;
    }

    if (sysName == "") {
        return;
    }

    for (var i = 0; i < devices.length; i++) {
        var device = devices[i];
        if (device.system_name == sysName) {
            onNodeSelect([device.mac_address]);
            if (zoom) {
                network.focusOnNode(device.mac_address, {scale:1});
            }
            break;
        }
    }
}

/*
 * Preparing the autocompletion search engine for the devices
 * TODO Upgrade the search with regex
 */
function prepareSearchEngine() {
    var engine = new Bloodhound({
        datumTokenizer: Bloodhound.tokenizers.obj.whitespace('system_name', 'ip_address'),
        queryTokenizer: Bloodhound.tokenizers.whitespace,
        local: this.devices
    });

    engine.initialize();

    $('#deviceSearch .typeahead').typeahead({
        hint: true,
        highlight: true,
        minLength: 1
    },
    {
        displayKey: 'system_name',
        source: engine.ttAdapter()
    });
}

/**
 * Adding the general options
 */
function addGeneralOptions() {
    var content = "<b>General settings:</b></br>";

    var chkShowVms = "<input type='checkbox' name='showvms'";
    chkShowVms += this.showvms ? "checked " : " ";
    chkShowVms += "onchange='toggleCheckbox(this);'> Show virtual machines <br>";

    var chkFreezeSimulation = "<input type='checkbox' id='chkFreezeSimulation' ";
    chkFreezeSimulation += this.freezeSimulation ? "checked " : " ";
    chkFreezeSimulation += "onchange='toggleCheckbox(this);'> Freeze simulation <br>";

    var btnStorePositions = "<button type='button' id='btnStorePositions' ";
    btnStorePositions += "onclick='storePositions();'> Store positions </button><br>";

    var btnClearPositions = "<button type='button' id='btnClearPositions' ";
    btnClearPositions += "onclick='clearPositions();'> Clear positions </button><br>";

    content += chkShowVms + chkFreezeSimulation + btnStorePositions + btnClearPositions;
    document.getElementById('general').innerHTML = content + "<hr>";
}

/**
 * Handling checkbox clicking
 */
function toggleCheckbox(element)
{
    if (element.name == "showvms") {
        this.showvms = element.checked;
        draw(); //TODO Find a way to make it load faster
    }
    else if (element.name == "freezeSimulation") {
        this.freezeSimulation = element.checked;
        network.freezeSimulation(this.freezeSimulation);
    }
}

/**
 * Manage the key presses events
 */
function onKeyPress(event){
    var charCode = ('charCode' in event) ? event.charCode : event.keyCode;
    console.log("Unicode '" + charCode + "' was pressed.");
}

/**
 * Adding the events listeners
 */
function addEventsListeners() {
    network.on('doubleClick', onDoubleClick);
    network.on('dragEnd', onDragEnd);
    network.on('select', onSelect);
}

/**
 * Manage the event when an object is double-clicked
 */
function onDoubleClick(properties) {
    for (var i = 0; i < properties.nodes.length; i++) {
        network.focusOnNode(properties.nodes[i], {scale:1});
    }
    onNodeSelect(properties.nodes);
}

/**
 * Manage the event when an object is released when dragged
 */
function onDragEnd(properties) {
    if (nodesPosition == undefined) {
        nodesPosition = network.getPositions();
    }

    for (var i = 0; i < properties.nodeIds.length; i++) {
        var id = properties.nodeIds[i];

        var newPos = network.getPositions([id])[id];
        var node = getNode(id);
        node.x = newPos.x;
        node.y = newPos.y;
        nodesPosition[id].x = newPos.x;
        nodesPosition[id].y = newPos.y;
    }
}

/**
 * Manage the event when an object is selected
 */
function onSelect(properties) {
    var content = "<b>No selection</b>"

    if (properties.nodes.length > 0) {
        onNodeSelect(properties.nodes);
    }
    else if (properties.edges.length > 0) {
        onEdgeSelect(properties.edges);
    }
}

/**
 * Manage the event when a node is selected
 */
function onNodeSelect(nodeId) {
    var device = getDevice(nodeId);

    var content = buildNodeDescription(device);

    document.getElementById('selectionInfo').innerHTML = content + "<hr>";

    document.getElementById('txtSearch').value = device.system_name;
    network.selectNodes([nodeId]);
    focusedOnNode = false;
}

/**
 * Manage the event when an edge is selected
 */
function onEdgeSelect(edge) {
    var edge = getEdge(edge);

    var content = buildEdgeDescription(edge);

    document.getElementById('selectionInfo').innerHTML = content + "<hr>";
}

/**
 * Builds node description
 */
function buildNodeDescription(device) {
    var ip = "?";
    var ip_type = "IP";

    if (device.ip_address) {
        ip = device.ip_address;
    }
    if (device.ip_address_type) {
        ip_type = device.ip_address_type.toUpperCase();
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
    var otherCount = 0;

    for (var index in device.interfaces) {
        var int = device.interfaces[index];
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
        connectedPorts += "<b>Other connections:</b> " + otherCount + "</br>";
    }

    return Object.keys(device.interfaces).length > 0 ? connectedPorts : "";
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

    var vlansIdsFrom = [];
    var vlansFrom = [];
    if (interfaceFrom != null) {
        for (var index in interfaceFrom.vlans) {
            vlansIdsFrom.push(index);
            vlansFrom.push(interfaceFrom.vlans[index]);
        }
    }

    var vlansIdsTo = [];
    var vlansTo = [];
    if (interfaceTo != null) {
        for (var index in interfaceTo.vlans) {
            vlansIdsTo.push(index);
            vlansTo.push(interfaceTo.vlans[index]);
        }
    }

    var contentFrom = "<b>" + deviceFrom.system_name + "</b></br>";
    var contentTo = "<b>" + deviceTo.system_name + "</b></br>";

    // TODO Specify the error message
    contentFrom += (interfaceFrom != null) ? "" : "No vlans could be found.";
    contentTo += (interfaceTo != null) ? "" : "No vlans could be found.";

    var differences = vlansIdsTo.diff(vlansIdsFrom)

    if (vlansFrom.length > 0) {
        contentFrom += "Vlans on <b>" + interfaceFrom.local_port + "</b>&nbsp:</br>";
        contentFrom += vlansToString(vlansFrom, macAdressFrom, differences);
    }

    if (vlansTo.length > 0) {
        contentTo += "Vlans on <b>" + interfaceTo.local_port + "</b>&nbsp:</br>";
        contentTo += vlansToString(vlansTo, macAdressTo, differences);
    }

    var content = contentFrom + "</br>" + contentTo + "</br>";

    return content;
}

/**
 * Stringify a list of vlans with their identifiers only
 */
function vlansToString(vlans, str, differences) {
    var string = "";
    for (var i = 0; i < vlans.length; i++) {
        var vlan = vlans[i];

        var color = (differences.indexOf(vlan.identifier) >= 0) ? vlanIncoherenceColor : "black";

        var ref = str + "/vlan" + vlan.identifier;
        string += vlansInfo(vlan, ref, color);
        string += (i < vlans.length -1) ? ", " : "";
    }
    return string;
}

/**
 * Generate vlan info (tooltip + div)
 */
function vlansInfo(vlan, ref, color) {
    // tooltip
    var string = "<a href='#" + ref + "' title='";
    string += "Name: " + vlan.name + "\n";
    string += "Mode: " + vlan.mode + "\n";
    string += "Status: " + vlan.status + "'";

    // <div> toggle
    string += " onclick=\"toggle('" + ref + "');\">";
    string += "<font color='" + color + "'>" + vlan.identifier + "</font></a>";
    string += "<small><div id='" + ref + "' style='display: none;'> ";
    string += "<font color='" + color + "'>";
    string += "(<b>Name:</b> " + vlan.name + ", ";
    string += "<b>Mode:</b> " + vlan.mode + ", ";
    string += "<b>Status:</b> " + vlan.status + ")</font></div></small>";

    return string;
}

/**
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
    var options = "<b>Vlan:</b> <select id='vlansDropDown' onchange='displayVlanInfo()'>";
    options += "<option value='noVlanSelection'></option>" ;

    for (var i in myVlans) {
        options += "<option value='" + myVlans[i].identifier + "'>";
        options += myVlans[i].identifier + "</option>";
    }
    options += "</select></br>";

    document.getElementById("vlanSelect").innerHTML = options;
    document.getElementById("vlansDropDown").value = selectedVlanId;
    displayVlanInfo();
}

/**
 * Display the information of the selected vlan
 */
function displayVlanInfo() {
    var vlans = document.getElementById("vlansDropDown");
    selectedVlanId = vlans.options[vlans.selectedIndex].value

    var vlan = myVlans[selectedVlanId];

    var info = "";

    if (vlan != undefined) {
        info += "<span><b>Name:</b> " + vlan.name + "</span><br>";

        var colorPicker = "<input id='vlanDiffusionColorPicker' type='color'";
        colorPicker += "onchange='updateColor(vlanDiffusionColorPicker.value, \"vlanDiffusionColor\")'";
        colorPicker += "value='" + vlanDiffusionColor + "'>";

        info += colorPicker + "<span><b>&nbspDiffusion</b></span></br>";

        var colorPicker = "<input id='vlanIncoherenceColorPicker' type='color'";
        colorPicker += "onchange='updateColor(vlanIncoherenceColorPicker.value, \"vlanIncoherenceColor\")'";
        colorPicker += "value='" + vlanIncoherenceColor + "'>";

        info += colorPicker + "<span><b>&nbspIncoherences</b></span>";
    }

    document.getElementById("vlanInfo").innerHTML = info + "<hr>";

    highlightVlanDiffusion(selectedVlanId);
    store("selectedVlanId", selectedVlanId, false);
}

/**
 * Updates the color preference
 */
function updateColor(color, variable) {
    window[variable] = color;

    store(variable, color, false);

    highlightVlanDiffusion(selectedVlanId);
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
            var vlansFrom = Object.keys(interfaceFrom.vlans);
            var vlansTo = Object.keys(interfaceTo.vlans);

            var coherent = vlansFrom.indexOf(id) != -1 && vlansTo.indexOf(id) != -1;
            var notApplicable = vlansFrom.indexOf(id) == -1 && vlansTo.indexOf(id) == -1;

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

/**
 * Get the interface connected from a device to another known mac address
 */
function getInterfaceConnectedTo(device, macAdress) {
    if (device == undefined) {
        return null;
    }

    for (var index in device.interfaces) {
        var int = device.interfaces[index];
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
        var from = edges[i].from;
        var to = edges[i].to;
        if ((from == link[0] && to == link[1]) ||
            (from == link[1] && to == link[0])) {
            return true;
        }
    }
}

/**
 * Store the value in the local storage
 */
function store(key, content, json) {
    localStorage[key] = json ? JSON.stringify(content) : content;
};

/**
 * Get the value from the local storage
 */
function get(key, json) {
    if (localStorage[key]) {
        return json ? JSON.parse(localStorage[key]) : localStorage[key];
    }
};

/**
 * Clears the value in the local storage
 */
function clear(key) {
    if (localStorage[key]) {
        delete localStorage[key];
    }
};

/**
 * Saves the position of all nodes in local storage.
 */
function storePositions() {
    store("nodesPosition", network.getPositions(), true);
    draw();
}

/**
 * Clears the nodes position in the local storage
 */
function clearPositions() {
    clear("nodesPosition");
    draw();
}

/**
 * Retrieves the position of all nodes in local storage.
 */
function getPositions() {
    return get("nodesPosition", true);
}

/**
 * Get the position of a node from the local storage.
 */
function getPosition(nodeID) {
    if (nodesPosition && nodesPosition[nodeID]) {
        var x = nodesPosition[nodeID].x;
        var y = nodesPosition[nodeID].y;
        return [x, y];
    }
}

/**
 * Resets the nodes and the edges in the network
 */
function resetData() {
    network.freezeSimulation(false);
    network.setData({nodes: nodes, edges: edges});
    network.freezeSimulation(this.freezeSimulation);
}

/**
 * Returns the differences between two arrays
 */
Array.prototype.diff = function(other) {
    var diff = [];
    for (var i = 0; i < this.length; i++) {
        var obj = this[i];
        if (other.indexOf(obj) == -1) {
            diff.push(obj);
        }
    }
    for (var i = 0; i < other.length; i++) {
        var obj = other[i];
        if (this.indexOf(obj) == -1 && diff.indexOf(obj) == -1) {
            diff.push(obj);
        }
    }
    return diff;
};
