Bot Templates File:

import discord                                      <-- Imports
import os                                           <-- Imports
import dotenv                                       <-- Imports
from datetime import datetime                       <-- Imports
import random                                       <-- Imports

dotenv.load_dotenv()                                <-- loads the .env with the token.

intents = discord.Intents.default()                 <-- important for a Discord bot
intents.message_content = True                      <-- important for a Discord bot
intents.members = True                              <-- important for a Discord bot
intents.presences = True                            <-- important for a Discord bot

client = discord.Bot(intents=intents)               <-- 'client' can be named differently. Creates the bot instance.

-----
ephemeral=True                                      <-- means only the command sender can see the following message


-----

@client.event                                       <-- a bot works and waits for events. this is how you create one.
async def on_ready():                               <-- define a new action (= def)
    for guild in client.guilds:                     <-- loop over all servers (guilds) the bot is in
        print(f"- {guild.name}")                    <-- print all server names the bot is on
    print("Bot is online!")                         <-- when the bot is online, it gives a sign of life (via 'print')

-----

@client.command(description="Test command")              <-- set description for the command. '@client.command' creates a command
async def testcmd(ctx):                                 <-- register the command
    try:                                                <-- the bot tries, if the command is called...
        embed = discord.Embed(                          <-- to send an embed
            title="DevCoderTestBot - TestCMD",          <-- the embed
            description=f"Hello {ctx.author}",          <-- the embed
            colour=0x00b0f4,                            <-- the embed
            timestamp=datetime.now()                    <-- the embed
        )
        await ctx.respond(embed=embed, ephemeral=True)  <-- output in chat of the embed: editor and embed creation at 'https://embed.dan.onl'.
                                            ^
                                            |
                                important to note: 'ephemeral=True' means only you can see the message

    except Exception as e:                          <-- if an error occurs, the bot should take this step
        print(f"An error occurred: {e}")       <-- the bot prints the error in the console

-----

@client.command(description="Minecraft info")                                   <-- command is described
async def minecraft(ctx):                                                       <-- command is registered
    try:                                                                        <-- try...
        await ctx.respond("Minecraft is a cool game!", ephemeral=True)    <-- post "Minecraft is a cool game!" in chat, but only for the command sender
    except Exception as e:                                                      <-- if an error occurs,
        print(f"An error occurred: {e}")                                   <-- print the error in the console: "An error occurred: <error>"

-----

@client.command(description="Discord bot help command")                         <-- command is described
async def help(ctx):                                                            <-- command is registered
    try:                                                                        <-- try...
        embed = discord.Embed(                                                  <-- create an embed
            title="Command Help List",                                         <-- appearance of the embed
            description="Commands:\n\n/help - Shows this view\n/testcmd - Tests the bot\n/minecraft - Fun command\n/say - Sends text as a bot message", <-- appearance of the embed
            colour=0x00f504,                                                    <-- appearance of the embed
            timestamp=datetime.now()                                            <-- appearance of the embed
        )                                                                       <-- embed header closed
        embed.set_footer(text="DevCoder")                                       <-- embed footer, appearance
        await ctx.respond(embed=embed)                                          <-- send the embed

    except Exception as e:                                                      <-- if an error occurs,
        print(f"An error occurred: {e}")                                   <-- print the error in the console
