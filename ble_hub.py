from pybricksdev.connections import BLEPUPConnection
from pybricksdev.ble import find_device

import asyncio

class BLEHub:
    
    def __init__(self, name, script_path, address=None):

        self.hub = BLEPUPConnection()
        self.name = name
        self.script_path = script_path
        self.address = address
        self.run_task = None
    
    async def connect(self):
        if self.address is None:
            self.address = await find_device("Pybricks Hub")
        await self.hub.connect(self.address)
    
    async def handle_output(self, line):
        if line.find("data::") == 0:
            print("got return data from hub!", line)
            data = eval(line.split("data::")[1])
            print(f"data: {data}")
            return
        print(line)
    
    async def run(self):
        print("initiating run!")
        async def hub_run():
            print(f"hub {self.name} run start!")
            await self.hub.run(self.script_path, wait=False, print_output=False)
            await self.hub.wait_until_state(self.hub.RUNNING)

            print("starting output handler loop")

            while self.hub.state == self.hub.RUNNING:
                while self.hub.output:
                    line = self.hub.output.pop(0).decode()
                    await self.handle_output(line)
                await asyncio.sleep(0.05)

            print(f"hub {self.name} run complete!")
            self.run_task = None

        self.run_task = asyncio.create_task(hub_run())
        await self.hub.wait_until_state(self.hub.RUNNING)
        print(f"hub {self.name} is running now!")

    
    @property
    def running(self):
        assert self.connected
        return self.run_task is not None
    
    @property
    def connected(self):
        return self.hub.connected
    
    async def pipe_command(self, cmdstr):
        assert self.running
        await self.hub.write(bytearray(cmdstr, encoding='utf8'))


async def main():

    trainpath = "E:/repos/brickrail/autonomous_train.py"
    train = BLEHub("white train", trainpath, None)
    await train.connect()
    await train.run()

    await train.hub.write(b"xd some message lol")

    print("done with main!")

    await train.hub.wait_until_state(train.hub.IDLE)

if __name__ == "__main__":
    asyncio.run(main())