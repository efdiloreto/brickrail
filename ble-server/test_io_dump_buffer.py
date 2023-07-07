import asyncio

from pybricksdev.ble import find_device

from ble_hub import BLEHub

async def io_test():

    response_queue = asyncio.Queue()

    def on_data(data):
        print(f"got data: {list(data)}")
        response_queue.put_nowait(data)
    
    async def test_response(data):
        await test_hub.rpc("respond", data)
        while not response_queue.empty():
            _ = response_queue.get_nowait()
        received = await asyncio.wait_for(response_queue.get(), 1.0)
        assert received == data

    device = await find_device()
    print(device)
    test_hub = BLEHub()
    test_hub.data_subject.subscribe(on_data)
    await test_hub.connect(device)
    try:
        await test_hub.run("test_io", wait=False)
        print("run started!")
        await asyncio.sleep(1.0)
        print("first rpc call:")
        await test_hub.rpc("dump_buffer", [4, 55])
        await asyncio.sleep(1)
        await test_hub.stop_program()
        await asyncio.sleep(1)
    finally:
        await test_hub.disconnect()
    
asyncio.run(io_test())