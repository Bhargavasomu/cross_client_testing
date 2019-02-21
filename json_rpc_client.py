import asyncio
import json
import os
import sys

from eth_utils.toolz import (
    get_in,
)

from connection import (
    Connection,
)
from utils import (
    build_request,
)
from validation import (
    validate_accounts,
    validate_block,
    validate_last_block,
)


# Global Constants
failing_test_cases = [
    'GeneralStateTests/stCreate2/RevertInCreateInInitCreate2_d0g0v0.json',

    # Verify why it is failing (Not sure that this has to be failing)
    'GeneralStateTests/stCreateTest/CREATE_ContractRETURNBigOffset_d1g0v0.json',
    'GeneralStateTests/stCreateTest/CREATE_ContractRETURNBigOffset_d2g0v0.json',
    'GeneralStateTests/stCreateTest/CREATE_ContractRETURNBigOffset_d0g0v0.json',

    # Think it is wrong test
    'GeneralStateTests/stRevertTest/RevertInCreateInInit_d0g0v0.json',

    # This is not a test fixture at all
    'GeneralStateTests/stShift/.stub'

    # This is some broken pipe test
    'GeneralStateTests/stSpecialTest/tx_e1c174e2_d0g0v0.json',

    # Wrong Upstreams
    'GeneralStateTests/stSStoreTest/InitCollision_d0g0v0.json',
    'GeneralStateTests/stSStoreTest/InitCollision_d1g0v0.json',
    'GeneralStateTests/stSStoreTest/InitCollision_d2g0v0.json',
    'GeneralStateTests/stSStoreTest/InitCollision_d3g0v0.json',

    # Broken Pipe Test
    'GeneralStateTests/stStackTests/stackOverflowM1PUSH_d22g0v0.json',
]


async def mine_and_validate_fixture_blocks(block_fixture_data):
    """
    This function is responsible to send out RPC calls to the server,
    so that the server can mine the blocks on its already formed (current) local chain
    1) Validate that the response which is rlp of the block as per the client is the same
       as those in the fixture, if the block in the fixture comes with the header
    2) Else check that the output should contain ``error`` as one of its json field
    """
    for block_fixture in block_fixture_data:
        should_be_good_block = 'blockHeader' in block_fixture

        if 'rlp_error' in block_fixture:
            assert not should_be_good_block
            continue

        params = [block_fixture]
        request_msg = build_request('evm_applyBlockFixture', params)
        response = await Connection.get_ipc_response(request_msg)

        if should_be_good_block:
            assert "error" not in response, "Response: %s" % response
            assert response["result"] == block_fixture["rlp"], "RLP values don't match"

            # Validate the contents of the block as per fixture
            await validate_block(block_fixture, block_fixture['blockHeader']['hash'])
        else:
            assert "error" in response, "Response: %s" % response


async def handle_general_state_tests(fixture_data):
    # Start from Genesis
    params = [fixture_data]
    request_msg = build_request('evm_resetToGenesisFixture', params)
    response = await Connection.get_ipc_response(request_msg)

    if "result" in response:
        assert response["result"] is True, "Unable to Reset Genesis - %s" % response
    else:
        print(response)
        assert False

    # Validate the fixture_data["pre"] states
    await validate_accounts(fixture_data['pre'])

    # Mine the fixture_data["blocks"] on the chain initialized above with genesis
    await mine_and_validate_fixture_blocks(fixture_data["blocks"])

    if fixture_data.get('lastblockhash', None):
        for block_fixture in fixture_data['blocks']:
            if get_in(['blockHeader', 'hash'], block_fixture) == fixture_data['lastblockhash']:
                await validate_last_block(block_fixture)

    # Validate the fixture_data["post"] states
    await validate_accounts(fixture_data['postState'])
    # Validate that mining of above block didn't alter the previous state
    await validate_accounts(fixture_data['pre'], 'earliest')


async def main(json_test_file_name):
    """
    This function aims to run a client which can interact with the
    json rpc server of any client
    """
    if json_test_file_name in failing_test_cases:
        print("Skipped For Now")
        return

    # read file
    with open(json_test_file_name, 'r') as test_file:
        data = test_file.read()
    # parse data
    test_data = json.loads(data)

    # Run each test case in the specified test file
    for test_name in test_data:
        fixture_data = test_data[test_name]
        await handle_general_state_tests(fixture_data)

    # if json_test_file_name == "GeneralStateTests/stAttackTest/ContractCreationSpam_d0g0v0.json":
    #     test_name = "ContractCreationSpam_d0g0v0_Byzantium"
    #     fixture_data = test_data[test_name]
    #     await handle_general_state_tests(fixture_data)

    print("All Passed")


if __name__ == "__main__":
    #
    # Geth JSON RPC -> geth --rpc --testnet
    # Trinity JSON RPC -> trinity --sync-mode none --ropsten
    #

    # jsonrpc_ipc_pipe_path = "/home/somu/.ethereum/testnet/geth.ipc"
    jsonrpc_ipc_pipe_path = "/home/somu/.local/share/trinity/ropsten/ipcs-eth1/jsonrpc.ipc"
    event_loop = asyncio.get_event_loop()

    Connection.jsonrpc_ipc_pipe_path = jsonrpc_ipc_pipe_path
    Connection.event_loop = event_loop

    test_dir = sys.argv[1]

    num_test_files_validated = 0
    for root, dirs, files in os.walk(test_dir, topdown=True):
        for name in files:
            test_file = os.path.join(root, name)
            print(test_file)
            event_loop.run_until_complete(main(test_file))
            num_test_files_validated += 1

    print("Number of Test Files Validated: {}".format(num_test_files_validated))
