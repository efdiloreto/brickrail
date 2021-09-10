class_name BLETrain

extends Reference

var name
var hub
var current_speed = 0
var target_speed = 0
var acceleration = 40
var deceleration = 90
var braking = false
var state = "stopped"
var slow_marker = "blue_marker"
var stop_marker = "red_marker"
var mode = "block"

signal state_changed(state)
signal mode_changed(mode)
signal slow_marker_changed(marker)
signal stop_marker_changed(marker)
signal name_changed(old_name, new_name)

func _init(p_name, p_address):
	name = p_name
	hub = BLEHub.new(p_name, "train", p_address)
	hub.connect("data_received", self, "_on_data_received")

func _on_data_received(key, data):
	prints("train received:", key, data)
	if key == "state_changed":
		set_state(data)
	if key == "mode_changed":
		mode = data
		emit_signal("mode_changed", data)
	if key == "slow_marker_changed":
		slow_marker = data
		emit_signal("slow_marker_changed", data)
	if key == "stop_marker_changed":
		stop_marker = data
		emit_signal("stop_marker_changed", data)

func set_state(p_state):
	state = p_state
	emit_signal("state_changed", state)

func set_name(p_new_name):
	var old_name = name
	name = p_new_name
	hub.set_name(p_new_name)
	emit_signal("name_changed", old_name, p_new_name)

func set_target(value):
	var cmd = "train.set_target(" + str(value) + ")"
	hub.hub_command(cmd)

func set_speed(value):
	var cmd = "train.set_speed(" + str(value) + ")"
	hub.hub_command(cmd)

func brake():
	hub.hub_command("train.brake()")

func start():
	hub.rpc("start", [])

func stop():
	hub.rpc("stop", [])

func wait():
	hub.rpc("wait", [])

func slow():
	hub.rpc("slow", [])

func flip_heading():
	hub.rpc("flip_heading", [])

func set_slow_marker(marker):
	slow_marker = marker
	hub.rpc("set_slow_marker", [marker])

func set_stop_marker(marker):
	stop_marker = marker
	hub.rpc("set_stop_marker", [marker])

func set_mode(p_mode):
	mode = p_mode
	hub.rpc("set_mode", [mode])
