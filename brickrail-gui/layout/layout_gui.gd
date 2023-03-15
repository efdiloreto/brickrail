extends HSplitContainer

export(NodePath) var input_control_button
export(NodePath) var input_select_button
export(NodePath) var input_draw_button

export(NodePath) var inspector_container
export(NodePath) var layer_container
export(NodePath) var layer_index_edit

func _ready():
	var _err = LayoutInfo.connect("layout_mode_changed", self, "_on_layout_mode_changed")
	_err = LayoutInfo.connect("selected", self, "_on_selected")
	_err = LayoutInfo.connect("layers_changed", self, "_on_layers_changed")
	_err = LayoutInfo.connect("active_layer_changed", self, "_on_active_layer_changed")
	_err = LayoutInfo.connect("trains_running", self, "_on_layout_trains_running")
	_err = LayoutInfo.connect("random_targets_set", self, "_on_layout_random_targets_set")
	_err = LayoutInfo.connect("control_devices_changed", self, "_on_layout_control_devices_changed")
	_err = get_node(layer_container).connect("item_selected", self, "_on_layer_container_item_selected")
	_on_layers_changed()
	_on_layout_mode_changed(LayoutInfo.layout_mode)
	$SaveLayoutDialog.current_path = Settings.layout_path
	$OpenLayoutDialog.current_path = Settings.layout_path

func _on_layout_random_targets_set(set):
	$LayoutSplit/LayoutModeTabs/run/AutoTarget.pressed = set

func _on_layout_trains_running(running):
	if running:
		$LayoutSplit/LayoutModeTabs.set_tab_disabled(0, true)
		$LayoutSplit/LayoutModeTabs/run/ControlDevicesToggle.disabled = true
	else:
		$LayoutSplit/LayoutModeTabs.set_tab_disabled(0, false)
		$LayoutSplit/LayoutModeTabs/run/ControlDevicesToggle.disabled = false

func _on_layers_changed():
	var layers = get_node(layer_container)
	layers.clear()
	for layer in LayoutInfo.cells:
		layers.add_item("layer "+str(layer))
	
	var edit = get_node(layer_index_edit)
	edit.value = len(LayoutInfo.cells)

func _on_active_layer_changed(l):
	if l==null:
		get_node(layer_container).unselect_all()
		return
	var index = LayoutInfo.cells.keys().find(l)
	get_node(layer_container).select(index)

func _on_layer_container_item_selected(index):
	var l = LayoutInfo.cells.keys()[index]
	LayoutInfo.set_active_layer(l)

func _on_layout_mode_changed(mode):
	var index = ["edit", "control"].find(mode)
	if index < 0:
		return
	$LayoutSplit/LayoutModeTabs.current_tab = index

func _on_selected(obj):
	get_node(inspector_container).add_child(obj.get_inspector())

func _on_LayoutSave_pressed():
	$SaveLayoutDialog.popup()

func _on_SaveLayoutDialog_file_selected(path):
	var struct = {}
	struct["devices"] = Devices.serialize()
	struct["layout"] = LayoutInfo.serialize()
	var serial = JSON.print(struct, "\t")
	var dir = Directory.new()
	if dir.file_exists(path):
		dir.remove(path)
	var file = File.new()
	file.open(path, 2)
	file.store_string(serial)
	file.close()
	Settings.layout_path = $OpenLayoutDialog.current_path

func _on_LayoutOpen_pressed():
	$OpenLayoutDialog.popup()

func _on_OpenLayoutDialog_file_selected(path):
	Devices.clear()
	LayoutInfo.clear()
	
	var file = File.new()
	file.open(path, 1)
	var serial = file.get_as_text()
	var struct = JSON.parse(serial).result
	if not "layout" in struct:
		LayoutInfo.load(struct)
		return
	if "devices" in struct:
		Devices.load(struct.devices)
	LayoutInfo.load(struct.layout)
	Settings.layout_path = $OpenLayoutDialog.current_path


func _on_LayoutNew_pressed():
	Devices.clear()
	LayoutInfo.clear()


func _on_control_devices_toggled(button_pressed):
	if not button_pressed:
		LayoutInfo.set_control_devices(false)
		return

	if Devices.get_ble_controller().are_hubs_ready():
		# TODO cleanup ble device state (stop everything?)
		LayoutInfo.set_control_devices(true)
	else:
		LayoutInfo.control_enabled = false
		LayoutInfo.set_random_targets(false)
		$LayoutSplit/LayoutModeTabs/run/ControlDevicesToggle.disabled = true
		$LayoutSplit/LayoutModeTabs/run/AutoTarget.disabled = true
		yield(Devices.get_ble_controller().connect_and_run_all_coroutine(), "completed")
		if Devices.get_ble_controller().are_hubs_ready():
			LayoutInfo.set_control_devices(true)
		$LayoutSplit/LayoutModeTabs/run/ControlDevicesToggle.disabled = false
		LayoutInfo.control_enabled = true
		$LayoutSplit/LayoutModeTabs/run/AutoTarget.disabled = false

func _on_layout_control_devices_changed(control_devices):
	$LayoutSplit/LayoutModeTabs/run/ControlDevicesToggle.pressed = control_devices
	$LayoutSplit/LayoutModeTabs/run/EmergencyStopButton.disabled = not control_devices

func _on_AutoTarget_toggled(button_pressed):
	LayoutInfo.set_random_targets(button_pressed)


func _on_SpinBox_value_changed(value):
	LayoutInfo.time_scale = value


func _on_add_layer_button_button_down():
	var edit = get_node(layer_index_edit)
	var l = int(edit.value)
	edit.value = l+1
	LayoutInfo.add_layer(l)


func _on_StopAllButton_pressed():
	LayoutInfo.set_random_targets(false)
	$LayoutSplit/LayoutModeTabs/run/AutoTarget.pressed = false
	for train in LayoutInfo.trains.values():
		if train.route != null:
			train.cancel_route()


func _on_LayoutModeTabs_tab_changed(tab):
	var mode = ["edit", "control"][tab]
	LayoutInfo.set_layout_mode(mode)


func _on_EmergencyStopButton_pressed():
	LayoutInfo.set_control_devices(false)
	for ble_train in Devices.trains.values():
		if ble_train.hub.running:
			ble_train.stop()
	_on_StopAllButton_pressed()
