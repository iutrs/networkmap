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

// Links colors
var linkDefaultColor = undefined;
var vlanDiffusionColor = get("vlanDiffusionColor") || "#00D000";
var vlanIncoherenceColor = get("vlanIncoherenceColor") || "#FF0000";

//var nodeDefaultColor = "#2B7CE9";
//var unaccessibleSwitchColor = "#C5000B";
//var serverDefaultColor = "#00FFBF";
//var vmDefaultColor = "#FF9900";

// Images path
const ICONS_DIR = "./css/img/hardware/";
const SWITCH_IMG = ICONS_DIR + "switch.png"
const SERVER_IMG = ICONS_DIR + "server.png"
const SWITCH_WARNING_IMG = ICONS_DIR + "switch_warning.png"
const SERVER_WARNING_IMG = ICONS_DIR + "server_warning.png"
const SWITCH_UNREACHABLE_IMG = ICONS_DIR + "switch_unreachable.png"
const SERVER_UNREACHABLE_IMG = ICONS_DIR + "server_unreachable.png"

// Title for images
const SWITCH_TITLE = undefined;
const SERVER_TITLE = undefined;
const SWITCH_WARNING_TITLE = "Incoherences found."
const SERVER_WARNING_TITLE = "Incoherences found."
const SWITCH_UNREACHABLE_TITLE = "Switch unreachable."
const SERVER_UNREACHABLE_TITLE = "Server unreachable."

// General options
//TODO Save to localStorage
var showvms = false;
var freezeSimulation = true;

var focusedOnNode = false;

var selectedVlanId = get("selectedVlanId") || "noVlanSelection";

// Loading the nodes' position
var nodesPosition = getPositions();

function draw() {
    if (devices == null) {
        errorMessage = "<font color='red'>Could not find '" + jsonFile + "'.</font>";
        $("#networkmap").html(errorMessage);
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
        },
        nodes: {
            widthMin: 48,
            widthMax: 72
          },
    };

    // Using jQuery to get the element does not work with vis.js library
    var container = document.getElementById("networkmap")

    network = new vis.Network(container, data, options);
    network.freezeSimulation(this.freezeSimulation);
    nodesPosition = network.getPositions();

    prepareSearchEngine();
    setGeneralOptionsAttributes();

    addEventsListeners();

    createVlansList();
}

/**
 * Create the nodes used by vis.js
 */
function createNodes() {
    for (var i = 0; i < devices.length; i++) {
        var device = devices[i];

        var img = SWITCH_IMG;
        var title = SWITCH_TITLE;

        var interfacesLength = Object.keys(device.interfaces).length
        if (interfacesLength == 0) {
            img = SWITCH_UNREACHABLE_IMG;
            title = SWITCH_UNREACHABLE_TITLE;
        }
        else if (device.system_description && device.system_description.indexOf("Linux") > -1) {
            img = SERVER_IMG;
            title = SERVER_TITLE;
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
            'shape': 'image',
            'color': undefined,
            'image': img,
            'title': title,
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
            'shape': "square",
            'color': undefined,
            'title': undefined,
            'value': 1,
            'mass': 1
        });

        edges.push(
        {
            'from': device.mac_address,
            'to': device.mac_address + "/" + vm.name,
            'style': "line",
            'color': undefined,
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

            var deviceTo = getDevice(int.remote_mac_address);

            if (deviceTo && !edgeExists(link)) {
                var labels = buildEdgeLabels(device, deviceTo, int);
                var labelFrom = labels[0];
                var labelTo = labels[1];

                edges.push(
                    {
                        'from': link[0],
                        'to': link[1],
                        'style': "line",
                        'color': undefined,
                        'width': 2,
                        'labelFrom': labelFrom,
                        'labelTo': labelTo
                    });
            }
            else if (!edgeExists(link) && int.remote_system_name != ""){
                // TODO Should we display these nodes?
                console.log("Unexisting node : " + int.remote_system_name)
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

/**
 * Build the edge labels depending if the link is trunked or not.
 */
 function buildEdgeLabels(deviceFrom, deviceTo, int) {

    var labelFrom = int.local_port;

    var stringifiedTrunk = getStringifiedTrunk(int.local_port, deviceFrom);
    if (stringifiedTrunk) {
        labelFrom = stringifiedTrunk;
    }
    else {
        var interfacesFrom = getInterfacesConnectedTo(deviceFrom, deviceTo);
        labelFrom = getStringifiedInterface(interfacesFrom) || labelFrom;
    }


    var labelTo = int.remote_port;

    var stringifiedTrunk = getStringifiedTrunk(int.remote_port, deviceTo);
    if (stringifiedTrunk) {
        labelTo = stringifiedTrunk;
    }
    else {
        var interfacesTo = getInterfacesConnectedTo(deviceTo, deviceFrom);
        labelTo = getStringifiedInterface(interfacesTo) || labelTo;
    }

    return [labelFrom, labelTo]
 }

/**
 * Returns the stringified version of the trunk associated to an interface if it exists.
 */
function getStringifiedTrunk(int_port, device) {
    for (var trunkId in device.trunks) {
        var trunk = device.trunks[trunkId];

        var stringfiedTrunk = trunk.group + "\n(";
        var interfaceIsTrunked = false;

        for (var p = 0; p < trunk.ports.length; p++) {
            var port = trunk.ports[p];
            if (int_port == port) {
                interfaceIsTrunked = true;
            }
            stringfiedTrunk += port + " "
        }

        if (interfaceIsTrunked) {
            return stringfiedTrunk.slice(0, -1) + ")";
        }
    }
}

/**
 * Returns the stringified version of an interface.
 */
function getStringifiedInterface(interfaces) {
    if (interfaces == null || interfaces.length <= 1) {
        return null;
    }

    var stringifiedInterface = "(";
    for (var i = 0; i < interfaces.length; i++) {
        stringifiedInterface += interfaces[i].local_port + " ";
    }

    return stringifiedInterface = stringifiedInterface.slice(0, -1) + ")";
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

    var interfaces = Object.keys(device.interfaces).map(function(key){return device.interfaces[key];});
    interfaces.sort(function(a, b){return naturalCompare(a.local_port, b.local_port)});

    for (var i = 0; i < interfaces.length; i++) {
        var int = interfaces[i];
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
    var html = "";

    var deviceFrom = getDevice(edge.from);
    var deviceTo = getDevice(edge.to);

    var incoherences = checkForIncoherencesBetween(deviceFrom, deviceTo);

    // We need tuples to compare vlans on same link
    var tuples = getInterfaceTuples(deviceFrom, deviceTo);

    if (incoherences.length > 0) {
        for (var i = 0; i < incoherences.length; i++) {
            html += "<p class='text-danger'>" + incoherences[i] + "</p>";
        }
    }

    var html = "<div class='table-responsive'><table class='table table-hover'>";
    html += "<thead><tr><th class='col-md-6'>" + deviceFrom.system_name + "</th>";
    html += "<th class='col-md-6'>" + deviceTo.system_name + "</th></tr></thead><tbody>";

    for (var i = 0; i < tuples.length; i++) {
        var intFrom = tuples[i][0];
        var intTo = tuples[i][1];

        var strings = stringifyInterfaceTuple(intFrom, intTo);

        var stringFrom = strings[0];
        var stringTo = strings[1];

        html += "<tr><td class='col-md-6'>" + stringFrom + "</td>";
        html += "<td class='col-md-6'>" + stringTo + "</td></tr>";
    }

    if (tuples.length <= 0) {
        // Showing vlans information of interfaces even if no tuples found
        var interfacesFrom = getInterfacesConnectedTo(deviceFrom, deviceTo);
        var interfacesTo = getInterfacesConnectedTo(deviceTo, deviceFrom);

        var mostInterfaces = (interfacesFrom.length >= interfacesTo.length) ? interfacesFrom : interfacesTo;

        for (var i = 0; i < mostInterfaces.length; i++) {
            var intFrom = mostInterfaces[i];
            var intTo = undefined;

            var strings = stringifyInterfaceTuple(intFrom, intTo);

            var stringFrom = strings[0];
            var stringTo = strings[1];

            html += "<tr><td class='col-md-6'>" + stringFrom + "</td>";
            html += "<td class='col-md-6'>" + stringTo + "</td></tr>";
        }
    }

    html += "</tbody></table></div>";

    return html;
}

/**
 * Check for incoherences between two connected devices
 */
function checkForIncoherencesBetween(deviceFrom, deviceTo) {
    var incoherences = [];

    var deviceFromUnaccessible = Object.keys(deviceFrom.interfaces).length <= 0;
    var deviceToUnaccessible = Object.keys(deviceTo.interfaces).length <= 0;

    if (deviceFromUnaccessible) {
        var incoherence = deviceFrom.system_name + " is unaccessible.";
        incoherences.push(incoherence);
    }

    if (deviceToUnaccessible) {
        var incoherence = deviceTo.system_name + " is unaccessible.";
        incoherences.push(incoherence);
    }

    if (deviceFromUnaccessible || deviceToUnaccessible) {
        return incoherences;
    }

    var interfacesFrom = getInterfacesConnectedTo(deviceFrom, deviceTo);
    var interfacesTo = getInterfacesConnectedTo(deviceTo, deviceFrom);

    if (interfacesFrom.length <= 0) {
        if (interfacesTo.length <= 0) {
            var incoherence = "Cannot find any valid link between these 2 devices.";
            incoherences.push(incoherence);
        }
        else {
            var incoherence = deviceFrom.system_name + " does not recognize " + deviceTo.system_name;
            incoherences.push(incoherence);
        }
    }
    else if (interfacesTo.length <= 0) {
        var incoherence = deviceTo.system_name + " does not recognize " + deviceFrom.system_name;
        incoherences.push(incoherence);
    }

    return incoherences;
}

/**
 * Join corresponding interfaces of two connected devices as tuples.
 */
function getInterfaceTuples(deviceFrom, deviceTo) {
    var tuples = [];

    var interfacesFrom = getInterfacesConnectedTo(deviceFrom, deviceTo);
    var interfacesTo = getInterfacesConnectedTo(deviceTo, deviceFrom);

    for (var i = 0; i < interfacesFrom.length; i++) {
        var intFrom = interfacesFrom[i];

        for (var j = 0; j < interfacesTo.length; j++) {
            var intTo = interfacesTo[j];

            // Remote port and local port on both ends must correspond
            var fromRecognizesTo = comparePortNames(intFrom.remote_port, intTo.local_port);
            var toRecognizesFrom = comparePortNames(intTo.remote_port, intFrom.local_port);

            if (fromRecognizesTo && toRecognizesFrom) {
                tuples.push([intFrom, intTo])
            }
        }
    }
    return tuples;
}

/**
 * Returns the stringified version of both interfaces as if they were connecteds.
 * We need two interfaces in order to find the vlan incoherences.
 */
function stringifyInterfaceTuple(intFrom, intTo) {
    // Interface from
    var vlansOnInterface = getVlansOnInterface(intFrom);
    var vlansIdsFrom = vlansOnInterface[0];
    var vlansFrom = vlansOnInterface[1];

    // Interface to
    vlansOnInterface = getVlansOnInterface(intTo);
    var vlansIdsTo = vlansOnInterface[0];
    var vlansTo = vlansOnInterface[1];

    // Vlan differences
    var vlanDifferences = vlansIdsTo.diff(vlansIdsFrom)

    var stringFrom = intFrom ? "Vlans on <b>" + intFrom.local_port + "</b>&nbsp:</br>" : "-";

    if (vlansFrom.length > 0) {
        stringFrom += vlansToString(vlansFrom, intFrom.mac_address, vlanDifferences);
    }
    else if (intFrom) {
        stringFrom += "<b>No vlans</b>";
    }

    var stringTo = intTo ? "Vlans on <b>" + intTo.local_port + "</b>&nbsp:</br>" : "-";

    if (vlansTo.length > 0) {
        stringTo += vlansToString(vlansTo, intTo.mac_address, vlanDifferences);
    }
    else if (intTo) {
        stringTo += "<b>No vlans</b>";
    }

    return [stringFrom, stringTo];
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
 * Generate vlan info (tooltip when hovering)
 */
function vlansInfo(vlan, ref, color) {
    var tooltip = "Name: " + vlan.name + "\n";
    tooltip += "Mode: " + vlan.mode + "\n";
    tooltip += "Status: " + vlan.status;

    var info = "<a data-container='body' data-toggle='popover' data-placement='top'";
    info += " data-content='" + tooltip + "' title='" + tooltip + "' >";
    info += "<font color='" + color + "'>" + vlan.identifier + "</font></a>";

    return info;
}

/**
 * Generates a dropdown list containing all the vlans identifier
 */
function createVlansList() {
    $("#vlansDropDown").append("<option value='noVlanSelection'></option>");

    for (var i in myVlans) {
        var option = "<option value='" + myVlans[i].identifier + "'>";
        option += myVlans[i].identifier + "</option>";

        $("#vlansDropDown").append(option);
    }

    $("#vlansDropDown").val(selectedVlanId);

    displayVlanInfo();
}

/**
 * Display the information of the selected vlan
 */
function displayVlanInfo() {

    selectedVlanId = $('#vlansDropDown>option:selected').text();

    store("selectedVlanId", selectedVlanId, false);

    var vlanInfo = "<label>No vlan selected.</label>";

    var vlan = myVlans[selectedVlanId];

    if (vlan != undefined) {
        vlanInfo = "<label>Name:</label>&nbsp" + vlan.name;
    }

    $("#vlanInfo").html(vlanInfo);

    highlightVlanDiffusion(selectedVlanId);
}

/**
 * Highlights the diffusion of the selected vlan
 */
function highlightVlanDiffusion(id) {

    $("#vlanDiffusionColorPicker").val(vlanDiffusionColor);
    $("#vlanIncoherenceColorPicker").val(vlanIncoherenceColor);

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
 * Updates the color preference
 */
function updateColor(color, variable) {
    window[variable] = color;

    store(variable, color, false);

    highlightVlanDiffusion(selectedVlanId);
}

/**
 * Preparing the autocompletion search engine for the devices
 * TODO Upgrade the search with regex
 */
function prepareSearchEngine() {
    var engine = new Bloodhound({
        datumTokenizer: Bloodhound.tokenizers.obj.whitespace("system_name", "ip_address"),
        queryTokenizer: Bloodhound.tokenizers.whitespace,
        local: this.devices
    });

    engine.initialize();

    $("#deviceSearch").typeahead({
        hint: true,
        highlight: true,
        minLength: 1
    },
    {
        displayKey: "system_name",
        source: engine.ttAdapter()
    });
}

/**
 * Adding the general options
 */
function setGeneralOptionsAttributes() {
    this.showvms ? $("#chkShowvms").attr("checked", "checked") : $("#chkShowvms").removeAttr("checked");

    this.freezeSimulation ? $("#chkFreezeSimulation").attr("checked", "checked") : $("#chkFreezeSimulation").removeAttr("checked");
}


/**
 * Handle checkbox clicking to show virtual machines nodes or not.
 */
function showVmsNodes() {
    this.showvms = !this.showvms;
    draw(); //TODO Find a way to make it load faster
}

/**
 * Handle checkbox clicking to freeze the simulation or not.
 */
function freezeNetworkSimulation() {
    this.freezeSimulation = !this.freezeSimulation;
    network.freezeSimulation(this.freezeSimulation);
}

/**
 * Manage the key presses events
 */
function onKeyPress(event){
    var charCode = ("charCode" in event) ? event.charCode : event.keyCode;
    console.log("Unicode '" + charCode + "' was pressed.");
}

/**
 * Adding the events listeners
 */
function addEventsListeners() {
    network.on("doubleClick", onDoubleClick);
    network.on("dragEnd", onDragEnd);
    network.on("select", onSelect);
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
    $("#selectionInfo").html(content);

    $("#deviceSearch").val(device.system_name);
    network.selectNodes([nodeId]);
    focusedOnNode = false;
}

/**
 * Manage the event when an edge is selected
 */
function onEdgeSelect(edge) {
    var edge = getEdge(edge);

    var content = buildEdgeDescription(edge);
    $("#selectionInfo").html(content);
}


/**
 * Select the node associated the specified system name.
 * If no argument is given (or undefined), it will try to select the node
 * with the system name entered in the search box.
 */
function toggleFocusOnNode() {
    if (focusedOnNode) {
        network.zoomExtent({duration:0});
    }
    else {
        selectNode(undefined, zoom=true);
    }

    focusedOnNode = !focusedOnNode;
}

/**
 * Select the node associated the specified system name.
 * If no argument is given (or undefined), it will try to select the node
 * with the system name entered in the search box.
 */
function selectNode(sysName, zoom) {
    if (sysName == undefined) {
        sysName = $("#deviceSearch").val();
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
 * Returns a list of all the interfaces connected from a device to another.
 */
function getInterfacesConnectedTo(deviceFrom, deviceTo) {

    if (!(deviceFrom && deviceTo)) {
        return [];
    }

    var connectedInterfaces = [];

    for (var index in deviceFrom.interfaces) {
        var int = deviceFrom.interfaces[index];
        if (int.remote_mac_address == deviceTo.mac_address) {
            connectedInterfaces.push(int);
        }
    }
    connectedInterfaces.sort(function(a, b){return naturalCompare(a.local_port, b.local_port)});

    return connectedInterfaces;
}

/**
 * Returns a list of all the vlan identifiers and the vlan themselves
 */
function getVlansOnInterface(int) {
    vlansIds = [];
    vlans = [];

    if (int != null) {
        for (var index in int.vlans) {
            vlansIds.push(index);
            vlans.push(int.vlans[index]);
        }
        vlansIds.sort();
        vlans.sort(function(a, b){return parseInt(a.identifier) > parseInt(b.identifier)});
    }

    return [vlansIds, vlans]
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
 * Saves the position of all nodes in local storage.
 */
function storePositions() {
    store("nodesPosition", network.getPositions(), true);
}

/**
 * Clears the nodes position in the local storage
 */
function clearPositions() {
    if (getPositions()) {
        clear("nodesPosition");
        draw();
    }
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

/**
 * Compare strings with numbers more "naturallly".
 * http://stackoverflow.com/questions/15478954/sort-array-elements-string-with-numbers-natural-sort/15479354#15479354
 */
function naturalCompare(a, b) {
    var ax = [], bx = [];

    a.replace(/(\d+)|(\D+)/g, function(_, $1, $2) { ax.push([$1 || Infinity, $2 || ""]) });
    b.replace(/(\d+)|(\D+)/g, function(_, $1, $2) { bx.push([$1 || Infinity, $2 || ""]) });

    while(ax.length && bx.length) {
        var an = ax.shift();
        var bn = bx.shift();
        var nn = (an[0] - bn[0]) || an[1].localeCompare(bn[1]);
        if(nn) return nn;
    }

    return ax.length - bx.length;
}

/**
 * Compares two ports names (strings) and returns 'true' if they are considered equal.
 * This function is needed because some devices trunkate the port names of their neighbours
 * with ".." and a simple comparison would fail.
 * (Ex.: comparing "ge-1/0.." to "ge-1/0/46.0" would return 'true')
 */
function comparePortNames(a, b) {
    if (a == b) {
        return true;
    }

    if (a.indexOf("..") > 0 && b.indexOf(a.substring(0, a.indexOf(".."))) > -1) {
        return true;
    }

    if (b.indexOf("..") > 0 && a.indexOf(b.substring(0, b.indexOf(".."))) > -1) {
        return true;
    }
}
