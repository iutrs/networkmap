# networkmap #

A python-javascript platform that generates documentation for the topology of a computing network by exploring every accessible equipment using the ssh protocol.

## Running the network exploration ##

### Prerequisites ###
The network exploration module of networkmap is written using [Python 2.7](http://www.python.org/). It relies on the [paramiko](https://github.com/paramiko/paramiko) library in order to establish the ssh connections with the network devices.

### Usage ###

*Currently supports the **LLDP** protocol only.*

The **explorer** package contains the python scripts used to explore a network. Simply run **main.py** using the command line and supply the previously filled configuration file. Example :

    python explorer/main.py path/to/config/file.txt

Once the exploration is done (when no more device is to be explored), it will generate the file *devices.json* which contains all the informations gathered during the exploration. If there is any error during the exploration, relevant error messages will indicate the source(s) of the problem(s).

### Functionalities ###
* Type of devices supported:
    * Hewlett-Packard switches
    * Juniper switches
    * Linux servers
* Explore devices using the LLDP protocol
* Informations gathered:
    * Global informations provided by LLDP (MAC and IP Address, system description, etc.)
    * LLDP connected interfaces
    * Virtual machines informations (Linux servers only)
* Multiprocessing for faster discovery (each device is explored in a new process)
* Specify the authentication method for individual or groups of devices

## Visualizing the generated network topology ##

### Prerequisites ###
networkmap is based on the [vis.js](https://github.com/almende/vis) visualization library. It requires [jQuery](https://jquery.com) and uses [typeahead](https://github.com/twitter/typeahead.js/) to easily find and focus on a device in the network graph.

### Usage ###
Simply open **networkmap.html** in your browser! If it fails to load the *devices.json* file, make sure both files are located in the same directory.

### Functionalities ###
* Autocompletion helps you search devices using their system name or their ip address
* Select a node (device) to get its informations
* Select an edge (link) to get the vlans informations
* Select a vlan to show its diffusion on the network and spot incoherences
    * Personalize the colors used in the layout
* Move the nodes as you wish
    * Freeze the simulation to move devices one by one (Unfreeze to resimulate)
    * Store and clear the nodes' positions to keep your layout
* Show virtual machines nodes for Linux servers [BETA]

## Dependencies (To be completed) ##

* **paramiko** https://github.com/paramiko/paramiko
* **vis.js** https://github.com/almende/vis
* **jQuery** https://jquery.com
* **typeahead** (Optional) https://github.com/twitter/typeahead.js/

## License ##

networkmap is licensed under the GNU GENERAL PUBLIC LICENSE https://www.gnu.org/licenses/gpl-3.0.en.html
