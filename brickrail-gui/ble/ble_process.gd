class_name BLEProcess
extends Node

var process_pid

func start_process():
	print("starting python server process")
	var output = []
	process_pid = OS.execute("CMD.exe", ["/K", "ble-server\\.env\\python.exe", "ble-server/ble_server.py"], false, [], false, true)
	prints("pid:", process_pid)

func kill():
	print("killing python server process")
	OS.kill(process_pid)
