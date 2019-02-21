import asyncio
import json
import os
import time


def wait_for(path):
    for _ in range(100):
        if os.path.exists(path):
            return True
        time.sleep(0.01)
    return False


def can_decode_json(potential):
    try:
        json.loads(potential.decode())
        return True
    except json.decoder.JSONDecodeError:
        return False


class Connection:
    jsonrpc_ipc_pipe_path = None
    event_loop = None

    @classmethod
    def check_connection_parameters(cls):
        if cls.jsonrpc_ipc_pipe_path is None:
            raise TypeError("JSON RPC IPC Pipe file is not specified")
        if cls.event_loop is None:
            raise TypeError("Event Loop is not specified")

    @classmethod
    async def connect_json_rpc_server(cls):
        """
        Connect to the server and return the reader and writer objects
        """
        cls.check_connection_parameters()
        if not wait_for(cls.jsonrpc_ipc_pipe_path):
            raise Exception("IPC server did not successfully start with IPC file")

        reader, writer = await asyncio.open_unix_connection(
            path=cls.jsonrpc_ipc_pipe_path,
            loop=cls.event_loop,
        )

        return reader, writer

    @classmethod
    async def get_ipc_response(cls, request_msg):
        reader, writer = await cls.connect_json_rpc_server()
        writer.write(request_msg)
        await writer.drain()
        result_bytes = b''
        while not can_decode_json(result_bytes):
            result_bytes += await asyncio.tasks.wait_for(
                fut=reader.readuntil(b'}'),
                timeout=30,
                loop=cls.event_loop,
            )

        writer.close()
        return json.loads(result_bytes.decode())
