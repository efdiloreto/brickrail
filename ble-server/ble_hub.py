
import asyncio
from random import randint
import time
from datetime import datetime
from pathlib import Path
from struct import pack, unpack

from reactivex.subject import Subject

from pybricksdev.ble import find_device
from pybricksdev.connections.pybricks import PybricksHub

from serial_data import SerialData
import config
import utils

_IN_ID_START   = 2  #ASCII start of text
_IN_ID_END     = 10 #ASCII line feed
_IN_ID_MSG_ACK = 6  #ASCII ack
_IN_ID_RPC     = 17 #ASCII device control 1
_IN_ID_SYS     = 18 #ASCII device control 2
_IN_ID_STORE   = 19 #ASCII device control 3
_IN_ID_MSG_ERR = 21 #ASCII nak

_OUT_ID_START   = 2  #ASCII start of text
_OUT_ID_END     = 10 #ASCII line feed
_OUT_ID_MSG_ACK = 6  #ASCII ack
_OUT_ID_DATA    = 17 #ASCII device control 1
_OUT_ID_SYS     = 18 #ASCII device control 2
# _OUT_ID_ALIVE  = 19 #ASCII device control 3
_OUT_ID_MSG_ERR = 21 #ASCII nak
_OUT_ID_DUMP    = 20

_SYS_CODE_STOP  = 0
_SYS_CODE_READY = 1
_SYS_CODE_ALIVE = 2
_SYS_CODE_VERSION = 3

_DUMP_TYPE_NONE   = 0
_DUMP_TYPE_COLORS = 1

_CHUNK_LENGTH = 80

def xor_checksum(bytes):
    checksum = 0xFF
    for byte in bytes:
        checksum ^= byte
    return checksum

def mod_checksum(data):
    checksum = 0x00
    for byte in data:
        checksum += byte
    return checksum%256

class BLEHub:

    def __init__(self, name=None, program_name=None, out_queue=None):

        self.name = name
        self.program_name = program_name
        self.hub = PybricksHub()
        self.data_queue = asyncio.Queue()
        self.data_subject = Subject()
        self.input_queue = asyncio.Queue()
        self.out_queue = out_queue

        self.hub_ready = asyncio.Event()
        self.program_stopped = asyncio.Event()

        self.input_lock = asyncio.Lock()
        self.output_queue = asyncio.Queue()
        self.hub.stdout_observable.subscribe(self._on_hub_stdout)
        self.msg_ack = asyncio.Queue()
        self.line_buffer = bytearray()
        self.output_buffer = bytearray()
        self.output_lines = []
        self.msg_len = None
        self.msg_dump = False
        self.output_byte_arrived = asyncio.Event()
        self.output_byte_time = time.time()
        self.disable_response = False

    def to_out_queue(self, key, data):
        if self.out_queue is None:
            return
        serial_data = SerialData(key, self.name, data)
        self.out_queue.put_nowait(serial_data)
    
    def set_name(self, name):
        self.name = name
    
    def add_to_output_buffer(self, byte):
        self.output_byte_arrived.set()
        self.output_byte_time = time.time()

        if self.msg_len is None:
            self.msg_len = byte
            self.msg_dump = False
            return
        
        if self.output_buffer == bytearray([_OUT_ID_DUMP]) and not self.msg_dump:
            print([self.msg_len, byte])
            data = bytes([self.msg_len, byte])
            print("bytes:", data)
            self.msg_len = unpack(">H", data)[0]
            print("len:", self.msg_len)
            self.msg_dump = True
            return
        
        if byte == _OUT_ID_END:
            if len(self.output_buffer) >=2 and self.output_buffer[-1] == b"\r"[0]:
                if self.output_buffer[0] >= 32:
                    try:
                        line = (bytes([self.msg_len]) + self.output_buffer[:-1]).decode()
                    except UnicodeDecodeError:
                        pass
                    else:
                        print(f"[IOHub {self.name}]", line)
                        self.output_lines.append(line)
                        self.output_buffer = bytearray()
                        self.msg_len = None
                        if "ERROR" in line.upper() or "EXCEPTION" in line.upper():
                            self.to_out_queue("program_error", line)
                        return

        if len(self.output_buffer) == self.msg_len and byte == _OUT_ID_END:
            if len(self.output_buffer) == self.msg_len:
                self.output_queue.put_nowait(self.output_buffer)
            else:
                # print("output buffer len!", self.output_bufferself.output_buffer)
                asyncio.create_task(self.send_ack(False))
            self.output_buffer = bytearray()
            self.msg_len = None
            return
        
        self.output_buffer += bytes([byte])
    
    def _on_hub_stdout(self, data):
        
        for byte in data:
            self.add_to_output_buffer(byte)
    
    async def hub_message_handler(self, bytes):
        out_id = bytes[0]

        # print("handling msg:", bytes)

        if out_id == _OUT_ID_MSG_ACK:
            await self.msg_ack.put(True)
            return
        if out_id == _OUT_ID_MSG_ERR:
            await self.msg_ack.put(False)
            return

        if out_id == _OUT_ID_DUMP:
            dump_type = bytes[1]
            buf = bytes[2:]
            print(f"received data dump of len({len(buf)})")
            print(list(buf))
            now = datetime.now().strftime("%Y-%m-%d_%H.%M.%S")
            dump_path = config.user_path / f"hub_{self.name}_dump_{now}.txt"
            print(dump_path)
            buf_hex = ''.join(format(byte, '02x') for byte in buf)
            with open(dump_path, "w") as dumpfil:
                dumpfil.write(buf_hex)
            if dump_type == _DUMP_TYPE_COLORS:
                plot_path = config.user_path / f"hub_{self.name}_colors_{now}.png"
                utils.plot_color_buffer(buf, plot_path)
                self.to_out_queue("info", ["Sensor debug files written", f"Data written to {dump_path.name}\nPlot written to {plot_path.name}\nDirectory:\n{plot_path.parent}"])
            return

        checksum = bytes[-1]
        output_checksum = xor_checksum(bytes[:-1])
        if not checksum == output_checksum:
            print(f"received {bytes[:-1]}, checksum mismatch! {checksum} != {output_checksum}", self.output_buffer)
            await self.send_ack(False)
            return
        if not self.disable_response:
            await self.send_ack(True)
        else:
            print("response supressed!!")
        data = bytes[1:-1] #strip out_id and checksum

        if out_id == _OUT_ID_SYS:
            sys_code = data[0]
            if sys_code == _SYS_CODE_READY:
                self.io_hub_version = "1.0.0"
                self.hub_ready.set()
            if sys_code == _SYS_CODE_VERSION:
                self.io_hub_version = data[1:].decode()
                self.hub_ready.set()
            if sys_code == _SYS_CODE_STOP:
                self.hub_ready.clear()
            if sys_code == _SYS_CODE_ALIVE:
                # print(f"{self.name} is alive!")
                if len(data)>1:
                    voltage = (data[1] << 8) + data[2]
                    current = (data[3] << 8) + data[4]
                    # print(f"voltage: {voltage} mV")
                    # print(f"current: {current} mA")

                    self.to_out_queue("battery", {"voltage": voltage, "current": current})
        
        if out_id == _OUT_ID_DATA:
            # print("got data:", [byte for byte in data])
            await self.data_queue.put(data)
            self.data_subject.on_next(data)
            self.to_out_queue("runtime_data", list(data))
    
    def queue_rpc(self, funcname, args=None):
        self.input_queue.put_nowait({"funcname": funcname, "args": args})
    
    async def rpc(self, funcname, args=None):
        encoded = bytes(funcname, "ascii")
        attr_hash1 = xor_checksum(encoded)
        attr_hash2 = mod_checksum(encoded)
        funcname_hash = bytes([attr_hash1,attr_hash2])
        if args is None:
            args = b""
        if not isinstance(args, bytes):
            args = bytes(args)
        msg = bytes([_IN_ID_RPC]) + funcname_hash + args
        await self.send_safe(msg)
    
    async def store_value(self, address, value):
        assert self.io_hub_version!="1.0.0"
        shifted = int(value)
        data = []
        while shifted > 0:
            data.insert(0, shifted & 0xFF)
            shifted >>= 8
        # print("deconstructed value:", data)
        msg = bytes([_IN_ID_STORE, address, 0] + data)
        await self.send_safe(msg)
    
    async def send_ack(self, success):
        if success:
            await self.send_unsafe(bytes([_IN_ID_MSG_ACK]))
        else:
            await self.send_unsafe(bytes([_IN_ID_MSG_ERR]))
        
    async def send_safe(self, data, unreliable=False, persistent=True):
        assert len(data) <= _CHUNK_LENGTH
        # print("sending safe:", data)
        checksum = xor_checksum(data)
        ack_result = False
        try_counter = 0
        while not ack_result:
            assert self.hub_ready.is_set()
            try_counter += 1
            if try_counter > 20:
                raise Exception("Maximum send tries exceeded!")
            
            full_data = bytes([len(data)+1]) + data + bytes([checksum, _IN_ID_END])

            if unreliable:
                if randint(0, 10) > 6:
                    print("data modified!")
                    full_data = bytearray(full_data)
                    mod_index = randint(0, len(full_data)-1)
                    # full_data.insert(mod_index, 88)
                    full_data.pop(mod_index)
                    # full_data[mod_index] = 88

            # print(f"sending msg: {repr(full_data)}, checksum={checksum}")
            async with self.input_lock:
                await self.hub.write(full_data)
            try:
                ack_result = await asyncio.wait_for(self.msg_ack.get(), timeout=.5)
            except asyncio.TimeoutError:
                if persistent:
                    print(f"Wait for acknowledgement timed out, resending {data}")
                else:
                    raise Exception(f"Wait for acknowledgement timed out!")
            else:
                if not ack_result:
                    if persistent:
                        print(f"Error received from hub, resending {data}")
                    else:
                        raise Exception(f"Error received from hub!")
        # print("...successful!")
    
    async def send_unsafe(self, data):
        async with self.input_lock:
            # print(f"sending unsafe: {repr(data)}")
            await self.hub.write(bytes([len(data)]) + data + bytes([_IN_ID_END]))
    
    async def send_sys_code(self, code):
        await self.send_safe(bytes([_IN_ID_SYS, code]))
    
    async def connect(self, device=None):
        # workaround for https://github.com/pybricks/support/issues/971
        # self.hub.nus_observable.dispose()
        # self.hub = PybricksHub()
        # self.hub.nus_observable.subscribe(self._on_hub_nus)
        try:
            if device is None:
                device = await find_device(self.name)
            await self.hub.connect(device)
        except Exception:
            self.to_out_queue("connect_error", [repr(Exception)])
        else:
            self.to_out_queue("connected", None)
    
    async def disconnect(self):
        try:
            await asyncio.wait_for(self.hub.disconnect(), 20.0)
        except asyncio.TimeoutError:
            print("disconnect timeout")
            await asyncio.sleep(1.0)
        self.to_out_queue("disconnected", None)
    
    async def brickrail_run(self, skip_download):
        await self.run(skip_download=skip_download)
    
    async def run(self, program=None, wait=False, skip_download=False):
        if skip_download:
            program = None
        else:
            if program is None:
                program = str(Path(__file__).parent / "hub_programs" / f"{self.program_name}.py")
            if not Path(program).exists():
                program = str(Path(__file__).parent / "hub_programs" / f"{program}.py")

        async def run_coroutine():
            await self.hub._wait_for_user_program_stop()
            self.program_stopped.set()
            self.to_out_queue("program_stopped", None)
        
        async def output_loop():
            while True:
                msg = await self.output_queue.get()
                await self.hub_message_handler(msg)
        
        async def input_loop():
            while True:
                command = await self.input_queue.get()
                await self.rpc(command["funcname"], command["args"])
        
        async def timeout_loop():
            while True:
                if self.msg_len is not None and (time.time()-self.output_byte_time)>0.2:
                    for sub_data in self.output_buffer.split(b"\n"):
                        if len(sub_data)<1:
                            continue
                        if sub_data[0]>31 and sub_data[-1] == b"\r"[0]:
                            try:
                                print(f"[IOHub {self.name}]", sub_data[:-1].decode())
                            except UnicodeDecodeError:
                                pass
                    print("output buffer timeout! Sending NAK", self.output_buffer)
                    self.output_buffer = bytearray()
                    self.msg_len = None
                    await self.send_ack(False)
                await asyncio.sleep(0.05)
        
        self.program_stopped.clear()
        self.hub_ready.clear()
        await self.hub.run(program, print_output=False, wait=False, line_handler=False)
        run_task = asyncio.create_task(run_coroutine())
        output_task = asyncio.create_task(output_loop())
        input_task = asyncio.create_task(input_loop())
        timeout_task = asyncio.create_task(timeout_loop())

        try:
            await asyncio.wait_for(self.hub_ready.wait(), timeout=3.0)
        except asyncio.TimeoutError:
            print(f"hub '{self.name}' wait for hub_ready timed out!!")
            self.to_out_queue("program_error", "program_start_timeout")
            return

        self.to_out_queue("io_hub_version", self.io_hub_version)
        self.to_out_queue("program_started", None)
        print("io_hub_version:", self.io_hub_version)

        if not wait:
            return

        try:
            await run_task
            await asyncio.sleep(0.5)
        finally:
            output_task.cancel()
            input_task.cancel()
            timeout_task.cancel()
    
    async def stop_program(self):
        await self.send_sys_code(_SYS_CODE_STOP)
    
    async def wait_for_data_id(self, id):
        while True:
            get_task = asyncio.ensure_future(self.data_queue.get())
            program_stop_task = asyncio.ensure_future(self.program_stopped.wait())
            done, pending = await asyncio.wait({get_task, program_stop_task}, return_when=asyncio.FIRST_COMPLETED)
            assert not program_stop_task in done , "Program stopped before data arrived!"
            
            data = get_task.result()
            if data[0] == id:
                return data
