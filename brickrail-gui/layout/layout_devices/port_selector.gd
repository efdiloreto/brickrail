extends VBoxContainer

signal device_selected(device)

var controllername
var port
var device_type

func setup(p_device, p_device_type, label):
	device_type = p_device_type
	$VBoxContainer/Label.text = label
	select(p_device)
	var _err = Devices.connect("layout_controllers_changed", self, "_on_devices_layout_controllers_changed")
	update_storage_controls()
	$ConfirmOverride.set_label("[unspecified]")
	$ConfirmOverride.add_action_button("cancel", "Cancel")
	$ConfirmOverride.add_action_button("override", "Override")

func update_storage_controls():
	var storage_node = $VBoxContainer/Storage
	for child in storage_node.get_children():
		storage_node.remove_child(child)
		child.queue_free()
	if controllername == null:
		return
	if port == null:
		return
	var controller: LayoutController = Devices.layout_controllers[controllername]
	if controller.devices[port] == null:
		return
	var device = controller.devices[port]
	var labels = device.storage_labels
	var max_limits = device.max_limits
	var order = device.storage_gui_order
	for i in order:
		var label = Label.new()
		label.text = labels[i]
		storage_node.add_child(label)
		if max_limits[i] == -1:
			var checkbox = CheckBox.new()
			var _err = checkbox.connect("toggled", self, "_on_storage_val_edited", [i, "bool"])
			checkbox.pressed = device.get_stored_value(i)
			storage_node.add_child(checkbox)
		else:
			var edit = SpinBox.new()
			var _err = edit.connect("value_changed", self, "_on_storage_val_edited", [i, "int"])
			edit.max_value = max_limits[i]
			edit.value = device.get_stored_value(i)
			storage_node.add_child(edit)

func _on_storage_val_edited(value, index, type):
	var controller: LayoutController = Devices.layout_controllers[controllername]
	var device = controller.devices[port]
	if type == "int":
		device.store_value(index, int(value))
	if type == "bool":
		device.store_value(index, int(value))
	LayoutInfo.set_layout_changed(true)

func select(p_device):
	if p_device == null:
		controllername = null
		port = null
	else:
		controllername = p_device.controllername
		port = p_device.port
	
	setup_options()
	update_storage_controls()


func _on_devices_layout_controllers_changed():
	setup_options()

func setup_options():
	var controller_option: Selector = $VBoxContainer/GridContainer/ControllerOption
	controller_option.set_items(Devices.layout_controllers.keys(), Devices.layout_controllers.keys())

	var port_option: Selector = $VBoxContainer/GridContainer/PortOption
	controller_option.select_meta(controllername)
	if controllername == null:
		port_option.set_items([], [])
		return
	
		
	var controller: LayoutController = Devices.layout_controllers[controllername]
	var num_ports = len(controller.devices)
	var portlabels = ["A", "B", "C", "D", "E", "F"].slice(0, num_ports-1)
	var portindices = range(num_ports)
	port_option.set_items(portlabels, portindices)
	port_option.select_meta(port)

func set_device(prev_port):
	if port == null or controllername == null:
		emit_signal("device_selected", null)
		return
	var controller: LayoutController = Devices.layout_controllers[controllername]
	if controller.devices[port] == null:
		controller.set_device(port, device_type)
	var device = controller.devices[port]
	if device.device_type != device_type:
		var action = "override"
		if device.ref_count > 0:
			var portname = ["A", "B", "C", "D", "E", "F"][port]
			var label = "Port "+portname+" on controller '"+controllername+"' already assigned to "+str(device.ref_count)+" other device(s)! Override?\n"
			label += "WARNING: This will remove the port from its previously assigned device(s)!"
			$ConfirmOverride.set_label(label)
			action = yield($ConfirmOverride.get_user_action_coroutine(), "completed")
		if action == "cancel":
			port = prev_port
			setup_options()
			update_storage_controls()
			return
		else:
			controller.set_device(port, device_type)
			device = controller.devices[port]
	update_storage_controls()
	emit_signal("device_selected", device)

func _on_PortOption_meta_selected(meta):
	var prev_port = port
	port = meta
	set_device(prev_port)

func _on_ControllerOption_meta_selected(meta):
	controllername = meta
	port = null
	setup_options()
	set_device(null)
