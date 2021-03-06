const jsonFile = "devices.json";
var devices = null;
var generationDate = null;

// The JSON must be fully loaded before onload() happens for calling draw() on 'devices'
$.ajaxSetup({
    async: false
});

// Reading the JSON file containing the devices' informations
$.getJSON(jsonFile, function(json) {
    devices = json.devices;
    generationDate = json.date;
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

// Images/icons constants
const ICONS_DIR = "./css/img/hardware/";
const ICONS_EXT = ".png";
const SWITCH = "switch"
const SERVER = "server"
const WARNING = "_warning";
const UNREACHABLE = "_unreachable";

const NO_INTERFACES_FOUND = "No interfaces found.";

// General options
// If variable from local storage != null, assign it, otherwise set it's default value.
var showvms = get("showvms", true) != null ? get("showvms", true) : false;
var freezeSimulation = get("freezeSimulation", true) != null ? get("freezeSimulation", true) : true;
var selectedVlanId = get("selectedVlanId", false) != null ? get("selectedVlanId", false) : "noVlanSelection";

var focusedOnNode = false; //TODO Save to localStorage?

// Loading the nodes' position
var nodesPosition = getPositions();

function draw() {
    if (devices == null) {
        errorMessage = "<font color='red'>Could not find '" + jsonFile + "'.</font>";
        $("#networkmap").html(errorMessage);
    }

    if (generationDate != null) {
        $("#generationDate").html("Generated on " + generationDate);
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
    var container = document.getElementById("networkmap");

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

        var title = undefined;
        var img = SWITCH;

        if (device.system_description && device.system_description.indexOf("Linux") > -1) {
            img = SERVER;
        }

        if (device.status != null) {
            title = device.status;
            img += UNREACHABLE;
        }
        else if (Object.keys(device.interfaces).length == 0) {
            title = NO_INTERFACES_FOUND;
            img += WARNING;
        }

        img = ICONS_DIR + img + ICONS_EXT;

        var interfacesLength = Object.keys(device.interfaces).length

        var storedPos = getPosition(device.mac_address);

        var posX = storedPos ? storedPos[0] : undefined;
        var posY = storedPos ? storedPos[1] : undefined;

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
                    myVlans[index] = int.vlans[index];
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

    return [labelFrom, labelTo];
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
            stringfiedTrunk += port + " ";
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
function buildDeviceDescription(device) {
    var ip = "?";
    var ip_type = "IP";

    if (device.ip_address) {
        ip = device.ip_address;
    }
    if (device.ip_address_type) {
        ip_type = device.ip_address_type.toUpperCase();
    }

    var problems = "";

    if (device.status != null) {
        problems = "<p class=text-danger>Error: " + device.status + "</p>";
    }
    else if (Object.keys(device.interfaces).length <= 0) {
        problems = "<p class=text-danger>Error: " + NO_INTERFACES_FOUND + "</p>";
    }

    var html =
        problems +
        "<label>Name:</label> " + device.system_name + "</br>" +
        "<label>Description:</label> " + device.system_description + "</br>" +
        "<label>" + ip_type + ":</label> " + ip + "</br>" +
        "<label>MAC:</label> " + device.mac_address + "</br>" +
        "<label>Capabilities:</label> " + device.enabled_capabilities + "</br>" +
        buildConnectedPortsList(device) +
        buildVirtualMachinesList(device);

    return html;
}

/**
 * Builds device's connected ports list
 */
function buildConnectedPortsList(device) {

    // TODO Include DataTables for sorting and search?
    var html = "<label>Connected interfaces:</label></br>";
    html += "<div class='table-responsive'><table class='table table-striped table-condensed'>";
    html += "<thead><tr><th>Local</th><th>Remote</th><th>Device</th></tr></thead><tbody>";

    var otherCount = 0;
    var interfaces = Object.keys(device.interfaces).map(function(key){return device.interfaces[key];});
    interfaces.sort(function(a, b){return naturalCompare(a.local_port, b.local_port)});

    for (var i = 0; i < interfaces.length; i++) {
        var int = interfaces[i];
        if (int.remote_system_name == "") {
            otherCount++;
            continue;
        }
        html += "<tr><td>" + int.local_port + "</td>";
        html += "<td>" + int.remote_port + "</td>";
        html += "<td>" + int.remote_system_name + "</td></tr>";
    }
    html += "</tbody></table></div>";

    if (otherCount > 0) {
        html += "<label>Other connections:</label> " + otherCount + "</br>";
    }

    return Object.keys(device.interfaces).length > 0 ? html : "";
}

/**
 * Builds device's virtual machines list
 */
function buildVirtualMachinesList(device) {

    // TODO Include DataTables for sorting and search?
    var html = "<label>Virtual machines:</label></br>";
    html += "<div class='table-responsive'><table class='table table-striped table-condensed'>";
    html += "<thead><tr> \
            <th class=''>ID</th> \
            <th class=''>Name</th> \
            <th class=''>State</th> \
            </tr></thead><tbody>";

    device.virtual_machines.sort(function(a, b){return naturalCompare(a.name, b.name)});
    for (var i = 0; i < device.virtual_machines.length; i++) {
        var vm = device.virtual_machines[i];

        html += "<tr><td class=''>" + vm.identifier + "</td>";
        html += "<td class=''>" + vm.name + "</td>";
        html += "<td class=''>" +  vm.state + "</td></tr>";
        // TODO Put icon for the vm state instead of string? Or maybe a color?
    }

    return device.virtual_machines.length > 0 ? html : "";
}

/**
 * Buils edge description
 */
function buildEdgeDescription(edge) {
    var html = "";

    var deviceFrom = getDevice(edge.from);
    var deviceTo = getDevice(edge.to);

    if (!(deviceFrom && deviceTo)) {
        return "<p class='text-info'>Links between servers and virtual \
            machines are not implemented yet.</p>";
    }

    var incoherences = checkForIncoherencesBetween(deviceFrom, deviceTo);

    // We need tuples to compare vlans on same link
    var tuples = getInterfaceTuples(deviceFrom, deviceTo);

    if (incoherences.length > 0) {
        for (var i = 0; i < incoherences.length; i++) {
            html += "<p class='text-danger'>" + incoherences[i] + "</p>";
        }
    }

    html += "<div class='table-responsive'><table class='table table-hover'>";
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
                tuples.push([intFrom, intTo]);
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
    var vlanDifferences = vlansIdsTo.diff(vlansIdsFrom);

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

        var color = "black";

        if (differences.indexOf(vlan.identifier) >= 0) {
            color = vlanIncoherenceColor;
        }
        else if (vlan.identifier == selectedVlanId) {
            color = vlanDiffusionColor;
        }

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
    info += " data-content='" + tooltip + "' title='" + tooltip + "' ><font color='" + color + "'>";
    info += (vlan.identifier == selectedVlanId) ? "<strong>" + vlan.identifier + "</strong>" : vlan.identifier;
    info += "</font></a>";
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

        var deviceFrom = getDevice(edge.from);
        var deviceTo = getDevice(edge.to);

        // We need tuples to compare vlans on same link
        var tuples = getInterfaceTuples(deviceFrom, deviceTo);

        for (var j = 0; j < tuples.length; j++) {
            var intFrom = tuples[j][0];
            var intTo = tuples[j][1];

            var vlansFrom = Object.keys(intFrom.vlans);
            var vlansTo = Object.keys(intTo.vlans);

            var coherent = vlansFrom.indexOf(id) != -1 && vlansTo.indexOf(id) != -1;
            var applicable = vlansFrom.indexOf(id) != -1 || vlansTo.indexOf(id) != -1;

            if (coherent) {
                edge.width = 8;
                edge.color = vlanDiffusionColor;
            }
            else if (applicable) {
                edge.width = 8;
                edge.color = vlanIncoherenceColor;
                break; // Override other colors when there is at least one incoherence
            }
            else {
                edge.width = 2;
                edge.color = linkDefaultColor;
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

    $("#vlans-feedback").flash_message({
        text: "Color settings saved.",
        how: "append",
        class_name: "text-success"
    });

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

    $("#deviceSearch").keypress(function(event) {
        const ENTER_KEY_CODE = 13;
        if (event.which == ENTER_KEY_CODE) {
            selectNode(undefined, zoom=true);
        }
    });
}

/**
 * Adding the general options
 */
function setGeneralOptionsAttributes() {
    this.showvms ? $("#chkShowvms").prop("checked", "checked") : $("#chkShowvms").removeProp("checked");

    this.freezeSimulation ? $("#chkFreezeSimulation").prop("checked", "checked") : $("#chkFreezeSimulation").removeProp("checked");
}


/**
 * Handle checkbox clicking to show virtual machines nodes or not.
 */
function showVmsNodes() {
    this.showvms = !this.showvms;
    store("showvms", this.showvms, true);

    draw(); //TODO Find a way to make it load faster
}

/**
 * Handle checkbox clicking to freeze the simulation or not.
 */
function freezeNetworkSimulation() {
    this.freezeSimulation = !this.freezeSimulation;
    store("freezeSimulation", this.freezeSimulation, true);

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

    var htmlContent = "";

    if (device) {
        htmlContent = buildDeviceDescription(device);
        $("#deviceSearch").val(device.system_name);
    }
    else {
        htmlContent = "<p class='text-info'>Virtual machines information is not implemented yet.</p>"
    }

    $("#selectionInfo").html(htmlContent);

    network.selectNodes([nodeId]);
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
        focusedOnNode = false;
    }
    else {
        selectNode(undefined, zoom=true);
    }
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
                focusedOnNode = true;
            }
            break;
        }
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

    return [vlansIds, vlans];
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

/** ----- **/

/** **/
/** localStorage Section **/

/**
 * Saves the position of all nodes in local storage.
 */
function storePositions() {
    store("nodesPosition", network.getPositions(), true);

    $("#options-feedback").flash_message({
        text: "Positions stored in local storage.",
        how: "append",
        class_name: "text-success"
    });
}

/**
 * Clears the nodes position in the local storage
 */
function clearPositions() {
    if (getPositions()) {
        clear("nodesPosition");
        draw();

        $("#options-feedback").flash_message({
            text: "Positions cleared from local storage.",
            how: "append",
            class_name: "text-success"
        });
    }
    else {
        $("#options-feedback").flash_message({
            text: "Positions already cleared.",
            how: "append",
            class_name: "text-danger"
        });
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
/** /.localStorage Section **/
/** **/

/** ----- **/

/** **/
/** Utilities Section **/

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

/**
 * Flash messages jQuery function from http://jsfiddle.net/vwvAd/446/
 */
(function($) {
    $.fn.flash_message = function(options) {
        options = $.extend({
            text: 'Done',
            time: 1500,
            how: 'before',
            class_name: ''
        }, options);

        return $(this).each(function() {
            if( $(this).parent().find('.flash_message').get(0) )
                return;

            var message = $('<span />', {
                'class': 'flash_message ' + options.class_name,
                text: options.text
            }).hide().fadeIn('fast');

            $(this)[options.how](message);

            message.delay(options.time).fadeOut('normal', function() {
                $(this).remove();
            });
        });
    };
})(jQuery);

/** /.Utilities Section **/
/** **/
