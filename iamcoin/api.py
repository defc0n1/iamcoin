import iamcoin
import logging
import asyncio
import sys


from aiohttp import web,ClientSession
from .p2p import peers, handle_peer_msg, broadcast_latest
from . import wallet
from . import transaction
from . import block

log = logging.getLogger(__name__)


async def api_get_block_count(request):
    log.info("Get block count API request.")
    return web.Response(text=str({'count': len(iamcoin.blockchain.blockchain)}),content_type='application/json')


async def api_get_peers(request):
    resp=[]
    for p in peers.keys():
        resp.append(p)

    return web.json_response({"peers":resp})


async def api_add_raw_block(request):

    data = await request.json()
    log.info("mining new block, data: {}".format(data))
    data = [transaction.Transaction.from_json(_) for _ in data["data"]]
    if request.method == "POST":
        block = await iamcoin.block.generate_raw_next_block(data)

        if not block:
            log.info("Could not generate block")
            return web.json_response({"response": "failure!"})
        iamcoin.block.add_block_to_blockchain(block)
        await broadcast_latest()
    return web.json_response({"response": "success!"})


async def api_add_block(request):
    if await block.generate_next_block():
        resp="success"
    else:
        resp="failure"
    return web.json_response({"response":resp})


async def api_mine_transaction(request):
    data = await request.json()
    if await block.generate_next_block_with_tx(data["address"], data["amount"]):
        resp = "success"
    else:
        resp = "failure"
    return web.json_response({"response":resp})


async def api_balance(request):
    balance = wallet.get_account_balance()
    return web.json_response({"address": wallet.get_pubkey_from_wallet(),
                              "balance": balance
                              })


async def api_add_peer(request):

    data = await request.post()

    if request.method == "POST":
        peer_addr = data.get('peer')
        log.info("Adding peer: {}".format(peer_addr))
        loop.create_task(add_peer(peer_addr))
        return web.json_response({"response": "success!"})


async def add_peer(peer_addr):
    async  with ClientSession() as session:
        async with session.ws_connect(peer_addr) as ws:
            log.info("{}".format(ws.get_extra_info('peername')))
            key = ws.get_extra_info('peername')[0]
            peers[key] = ws
            log.info("Added peer.")
            await handle_peer_msg(key,ws)
    # except Exception:
    #     session.close()
    log.info("Closing and Removing peer: {}".format(peer_addr))
    await peers[key].close()
    del peers[key]
    log.info("Removed peer {}".format(peer_addr))


async def wshandle(request):
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    log.info("Incoming WS connection...")
    key = request.transport.get_extra_info('peername')[0]
    peers[key]=ws
    await handle_peer_msg(key, ws)
    log.info("Incoming is in...")
    return ws


app = web.Application(logger=log)
app.add_routes([web.get('/blockcount', api_get_block_count),
                web.post("/minerawblock", api_add_raw_block),
                web.post("/mineblock", api_add_block),
                web.post("/minetransaction", api_mine_transaction),
                web.get("/balance", api_balance),
                web.post("/addpeer", api_add_peer),
                web.get("/peers", api_get_peers),
                web.get('/ws', wshandle)])


loop = asyncio.get_event_loop()
handler = app.make_handler()
server = loop.create_server(handler, "0.0.0.0", iamcoin.PORT)
loop.run_until_complete(server)