import asyncio
import base64
import json
import random
import sys

import aiohttp
import websockets
from fake_useragent import UserAgent
from loguru import logger
from websockets.exceptions import ConnectionClosedOK

import settings


def generate_xsuperproperties():
    browsers = ["Chrome", "Firefox", "Edge", "Opera"]
    browser = random.choice(browsers)
    ua = UserAgent()
    xsuperproperties = json.dumps(
        {
            "os":"Windows",
            "browser":browser,
            "device":"",
            "system_locale":"ru-RU",
            "browser_user_agent":ua[browser],
            "browser_version":"98.0.4758.102",
            "os_version":"10",
            "referrer":"",
            "referring_domain":"",
            "referrer_current":"",
            "referring_domain_current":"",
            "release_channel":"stable",
            "client_build_number":116768,
            "client_event_source":None}
    )
    return base64.b64encode(xsuperproperties.encode("UTF-8")).decode("UTF-8")


async def telegram_alert(username, message):
    bottoken = settings.bot_token
    user_id = settings.tg_user_id

    if not bottoken and  not user_id:
        return

    url = f"https://api.telegram.org/bot{bottoken}/sendMessage?chat_id={user_id}&text={username} was mention. Message text:{message}"

    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            if response.status == 401:
                logger.error("invalid telegram bot token")
                settings.bot_token = None



class DiscordAccount:

    def __init__(self, token, delay):
        self.s = 0
        self.token = token
        self._channelid = None
        self.headers = {
            "authorization": self.token,
            "user-agent": UserAgent().random,
            "x-super-properties": generate_xsuperproperties(),
            "content-type": "application/json"
        }
        self.companion = None
        self.delay = delay
        self.first = False


    def set_channelid(self, channelid):
        self._channelid = channelid


    async def me(self):
        url = f"https://discord.com/api/v9/users/@me"

        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=self.headers) as response:
                if response.status == 401:
                    return "Invalid token"
                data = json.loads(await response.text())
                self.username = data["username"]
                self.id = data["id"]
                return data 


    
    async def typing(self):
        url = f"https://discord.com/api/v9/channels/{self._channelid}/typing"

        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=self.headers) as response:
                logger.info(f"{self.username} typing...")


    async def send_message(self, text):
        url = f"https://discord.com/api/v9/channels/{self._channelid}/messages"

        data = json.dumps(
            {
                "content":text,
                "nonce":"".join([str(random.randint(0,9)) for _ in range(18)]),
                "tts":False
            }
        )

        while True:
            await self.typing()
            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=self.headers, data=data) as response:
                    if response.status == 429:
                        retry_time = int(json.loads(await response.text())["retry_after"])+1
                        logger.error(f"{self.username} Rate limit. Sleep for {retry_time}")
                        await asyncio.sleep(retry_time)
                        continue
                    elif response.status == 200:
                        logger.success(f"{self.username} sent message")
                        return
                    else:
                        logger.error(f"Unexcpected error {await response.text()}")
                

    async def reply_to(self, text, guild_id, channel_id, message_id):
        await asyncio.sleep(0.5)
        logger.info(f"{self.username} waiting {self.delay} seconds until reply")
        await asyncio.sleep(random.randint(self.delay-2, self.delay+2))
        await self.typing()
        url = f"https://discord.com/api/v9/channels/{self._channelid}/messages"

        data = json.dumps(
            {
                "content":text,
                "nonce":"".join([str(random.randint(0,9)) for _ in range(18)]),
                "tts":False,
                "message_reference":{
                    "guild_id":guild_id,
                    "channel_id":channel_id,
                    "message_id":message_id
                }
            }
        )
        while True:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=self.headers, data=data) as response:
                    if response.status == 429:
                        retry_time = int(json.loads(await response.text())["retry_after"])
                        logger.error(f"{self.username} Rate limit. Sleep for {retry_time}")
                        await asyncio.sleep(retry_time)
                        continue
                    elif response.status == 200:
                        logger.success(f"{self.username} sent message [{text}]")
                        return
                    else:
                        logger.error(f"Unexcpected error {await response.text()}")
                    


    
    async def heartbeat(self, ws, milliseconds):
        heartbeat = json.dumps({
            "op": 1,
            "d": self.s
        })
        while True:
            await ws.send(heartbeat)
            await asyncio.sleep(milliseconds*10**-3)


    async def online(self, ws):
        online = json.dumps({
            "op":3,
            "d":{
                "status":"online",
                "since":0,
                "activities":[],
                "afk":True
                }
        })
        while True:
            await ws.send(online)
            await asyncio.sleep(60)


    async def gateway(self, dialog):

        if self.first:
            dialogline = 0
        else:
            dialogline = 1
        
        if self.first:
            await asyncio.sleep(5)
            await self.send_message(dialog[dialogline])
            dialogline +=2
        
        url = "wss://gateway.discord.gg/?encoding=json&v=9"
        authdata = json.dumps({
            "op":2,
            "d":{
                "token":self.token,
                "capabilities":509,
                "properties":{
                    "os":"Windows",
                    "browser":"Chrome",
                    "device":"",
                    "system_locale":"ru-RU",
                    "browser_user_agent":UserAgent().random,
                    "browser_version":"98.0.4758.102",
                    "os_version":"10",
                    "referrer":"https://discord.com/",
                    "referring_domain":"discord.com",
                    "referrer_current":"",
                    "referring_domain_current":"",
                    "release_channel":"stable",
                    "client_build_number":116961,
                    "client_event_source":None
                    },"presence":{"status":"online","since":0,"activities":[],"afk":False},"compress":False,"client_state":{"guild_hashes":{},"highest_last_message_id":"0","read_state_version":0,"user_guild_settings_version":-1,"user_settings_version":-1}}})
        while True:
            try:
                async with websockets.connect(url) as ws:
                    
                    await ws.send(authdata)
                    online = asyncio.create_task(self.online(ws))
                    asyncio.gather(online)

                    async for message in ws:
                        data = json.loads(message)
                        self.s = data["s"]

                        if data["op"] == 10:
                            heartbeat = asyncio.create_task(self.heartbeat(ws, data["d"]["heartbeat_interval"]))
                            asyncio.gather(heartbeat)  

                        if data["t"] == "MESSAGE_CREATE":
                            
                            if len(data["d"]["mentions"]) > 0:
                                if data["d"]["mentions"][0]["id"] == self.id and data["d"]["author"]["id"] != self.companion and data["d"]["author"]["id"] != self.id:
                                    logger.warning(f"{self.username} was ping")
                                    alert = asyncio.create_task(telegram_alert(self.username, data["d"]["content"]))
                                    asyncio.gather(alert)
                            if data["d"]["author"]["id"] == self.companion:
                                if len(dialog)-1 >= dialogline:
                                    if data["d"]["content"] == dialog[dialogline-1]:
                                        task = asyncio.create_task(self.reply_to(dialog[dialogline], data["d"]["guild_id"], data["d"]["channel_id"],data["d"]["id"]))
                                        asyncio.gather(task)
                                        dialogline += 2
            except ConnectionClosedOK:
                logger.info(f"[{self.username}] reconnecting...")
                continue
            except Exception as e:
                logger.error(e)
                continue
        


async def main():
    ds1 = DiscordAccount(settings.token1, settings.delay)
    ds1.set_channelid(settings.channel_id)
    ds1_info = await ds1.me()
    if ds1_info == "Invalid token":
        logger.error(f"{settings.token1} invalid token")
        quit()
    ds1.first = True

    ds2 = DiscordAccount(settings.token2, settings.delay)
    ds2.set_channelid(settings.channel_id)
    ds2_info = await ds2.me()
    if ds2_info == "Invalid token":
        logger.error(f"{settings.token2} invalid token")
        quit()

    ds1.companion = ds2_info["id"]
    ds2.companion = ds1_info["id"]
    
    with open("dialog.txt", "r", encoding="utf-8") as file:
        dialog = file.read().splitlines()
        dialog = [line.strip() for line in dialog]
        
    ds1_gateway = asyncio.create_task(ds1.gateway(dialog))
    ds2_gateway = asyncio.create_task(ds2.gateway(dialog))
    await asyncio.gather(ds1_gateway, ds2_gateway)



if __name__ == "__main__":
    print("Dialog bot by @Zexten")
    logger.remove()
    logger.add(sys.stderr, format="<white>{time:HH:mm:ss}</white> | <level>{level: <8}</level> | <level>{message}</level>")
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(main())
