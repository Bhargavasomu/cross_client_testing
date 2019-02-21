from eth_utils import (
    is_hex,
    is_integer,
    is_string,
)
from eth_utils.toolz import (
    identity,
    dissoc,
)

from connection import (
    Connection,
)
from normalizers import (
    RPC_BLOCK_NORMALIZERS,
    RPC_BLOCK_REMAPPERS,
    RPC_STATE_LOOKUPS,
    RPC_STATE_NORMALIZERS,
    RPC_TRANSACTION_NORMALIZERS,
    RPC_TRANSACTION_REMAPPERS,
)
from utils import (
    build_request
)


#
# Account Validation
#

def fixture_state_in_rpc_format(state):
    return {
        key: RPC_STATE_NORMALIZERS.get(key, identity)(value)
        for key, value in state.items()
    }


async def validate_account_attribute(
        *,
        account_state_key,
        rpc_method,
        state,
        addr,
        at_block):
    params = [addr, at_block]
    request_msg = build_request(rpc_method, params)
    response = await Connection.get_ipc_response(request_msg)

    assert response["result"] == state[account_state_key], "Invalid state - %s" % response


async def validate_account_state(account_state, addr, at_block):
    standardized_state = fixture_state_in_rpc_format(account_state)
    for account_state_key, rpc_method in RPC_STATE_LOOKUPS:
        await validate_account_attribute(
            account_state_key=account_state_key,
            rpc_method=rpc_method,
            state=standardized_state,
            addr=addr,
            at_block=at_block,
        )
    for key in account_state['storage']:
        position = '0x0' if key == '0x' else key
        expected_storage = account_state['storage'][key]

        params = [addr, position, at_block]
        request_msg = build_request('eth_getStorageAt', params)
        response = await Connection.get_ipc_response(request_msg)

        assert response["result"] == expected_storage, "Invalid storage - %s" % response["error"]


async def validate_accounts(account_states_fixture_data, at_block="latest"):
    """
    Validate that the balance, code, nonce, storage for an address on
    the server is same as what is stated in the json file
    """
    for addr in account_states_fixture_data:
        await validate_account_state(
            account_states_fixture_data[addr],
            addr,
            at_block,
        )


#
# Block Validation
#

def fixture_block_in_rpc_format(state):
    return {
        RPC_BLOCK_REMAPPERS.get(key, key):
        RPC_BLOCK_NORMALIZERS.get(key, identity)(value)
        for key, value in state.items()
    }


def fixture_transaction_in_rpc_format(state):
    return {
        RPC_TRANSACTION_REMAPPERS.get(key, key):
        RPC_TRANSACTION_NORMALIZERS.get(key, identity)(value)
        for key, value in state.items()
    }


def validate_rpc_block_vs_fixture_header(block, header_fixture):
    expected = fixture_block_in_rpc_format(header_fixture)
    actual_block = dissoc(
        block,
        'size',
        'totalDifficulty',
        'transactions',
        'uncles',
    )
    assert actual_block == expected


def validate_rpc_block_vs_fixture(block, block_fixture):
    return validate_rpc_block_vs_fixture_header(block, block_fixture['blockHeader'])


def is_by_hash(at_block):
    if is_string(at_block) and is_hex(at_block) and len(at_block) == 66:
        return True
    elif is_integer(at_block) or at_block in ('latest', 'earliest', 'pending'):
        return False
    else:
        raise ValueError("Unrecognized 'at_block' value: %r" % at_block)


def validate_rpc_transaction_vs_fixture(transaction, fixture):
    expected = fixture_transaction_in_rpc_format(fixture)
    actual_transaction = dissoc(
        transaction,
        'hash',
    )
    assert actual_transaction == expected


async def validate_transaction_by_index(transaction_fixture, at_block, index):
    if is_by_hash(at_block):
        rpc_method = 'eth_getTransactionByBlockHashAndIndex'
    else:
        rpc_method = 'eth_getTransactionByBlockNumberAndIndex'

    params = [at_block, hex(index)]
    request_msg = build_request(rpc_method, params)
    response = await Connection.get_ipc_response(request_msg)
    assert "error" not in response, "Error in getting transaction: %s" % response
    validate_rpc_transaction_vs_fixture(response["result"], transaction_fixture)


async def validate_transaction_count(block_fixture, at_block):
    if is_by_hash(at_block):
        rpc_method = 'eth_getBlockTransactionCountByHash'
    else:
        rpc_method = 'eth_getBlockTransactionCountByNumber'
    expected_transaction_count = hex(len(block_fixture['transactions']))

    params = [at_block]
    request_msg = build_request(rpc_method, params)
    response = await Connection.get_ipc_response(request_msg)
    assert "error" not in response
    assert response["result"] == expected_transaction_count


async def validate_uncle_count(block_fixture, at_block):
    if is_by_hash(at_block):
        rpc_method = 'eth_getUncleCountByBlockHash'
    else:
        rpc_method = 'eth_getUncleCountByBlockNumber'

    num_uncles = len(block_fixture['uncleHeaders'])
    params = [at_block]
    request_msg = build_request(rpc_method, params)
    response = await Connection.get_ipc_response(request_msg)
    assert "error" not in response
    assert response["result"] == hex(num_uncles)


async def validate_uncle_headers(block_fixture, at_block):
    if is_by_hash(at_block):
        rpc_method = 'eth_getUncleByBlockHashAndIndex'
    else:
        rpc_method = 'eth_getUncleByBlockNumberAndIndex'

    for idx, uncle in enumerate(block_fixture['uncleHeaders']):
        params = [at_block, hex(idx)]
        request_msg = build_request(rpc_method, params)
        response = await Connection.get_ipc_response(request_msg)
        assert "error" not in response
        validate_rpc_block_vs_fixture_header(response["result"], uncle)


async def validate_uncles(block_fixture, at_block):
    await validate_uncle_count(block_fixture, at_block)
    await validate_uncle_headers(block_fixture, at_block)


async def validate_block(block_fixture, at_block):
    if is_by_hash(at_block):
        rpc_method = 'eth_getBlockByHash'
    else:
        rpc_method = 'eth_getBlockByNumber'

    # validate without transaction bodies
    params = [at_block, False]
    request_msg = build_request(rpc_method, params)
    response = await Connection.get_ipc_response(request_msg)
    assert "error" not in response, "Error in getting block: %s" % response

    result = response["result"]
    validate_rpc_block_vs_fixture(result, block_fixture)
    assert len(result['transactions']) == len(block_fixture['transactions'])

    for index, transaction_fixture in enumerate(block_fixture['transactions']):
        await validate_transaction_by_index(transaction_fixture, at_block, index)

    await validate_transaction_count(block_fixture, at_block)

    # TODO validate transaction bodies
    # result, error = await call_rpc(rpc, rpc_method, [at_block, True])
    # assert error is None
    # assert result['transactions'] == block_fixture['transactions']

    await validate_uncles(block_fixture, at_block)


#
# Last Block Validation
#

async def validate_last_block(block_fixture):
    header = block_fixture['blockHeader']

    await validate_block(block_fixture, 'latest')
    await validate_block(block_fixture, header['hash'])
    await validate_block(block_fixture, int(header['number'], 16))
