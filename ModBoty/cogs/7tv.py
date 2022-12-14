import asyncio
import re

import twitchio
from twitchio.ext.commands import Cog, command, Context
from twitchio.ext.routines import routine
import aiohttp

from config import config

headers = {"Authorization": f"Bearer {config['Bot']['7tv_token']}"}


async def get_stv_user(session, user_id: int):
    async with session.get(f"https://7tv.io/v3/users/twitch/{user_id}") as response:
        return await response.json()


async def get_stv_user_gql(session, stv_id: str):
    json = {
        "operationName": "GetUser",
        "query": "query GetUser($id: ObjectID!) {\n  user(id: $id) {\n    id\n    username\n    "
        "display_name\n    created_at\n    avatar_url\n    style {\n      color\n      paint_id\n "
        "  __typename\n    }\n    biography\n    editors {\n      id\n      permissions\n      "
        "visible\n      user {\n        id\n        username\n        display_name\n        "
        "avatar_url\n        style {\n          color\n          paint_id\n          __typename\n "
        "}\n        __typename\n      }\n      __typename\n    }\n    roles\n    connections {\n "
        "     id\n      username\n      display_name\n      platform\n      linked_at\n      "
        "emote_capacity\n      emote_set_id\n      __typename\n    }\n    __typename\n  }\n}",
        "variables": {"id": stv_id},
    }

    async with session.post("https://7tv.io/v3/gql", json=json, headers=headers) as response:
        return await response.json()


async def update_emote_set(session, origins: list, emote_set_id: str):
    json = {
        "operationName": "UpdateEmoteSet",
        "query": "mutation UpdateEmoteSet($id: ObjectID!, $data: UpdateEmoteSetInput!) {\n  emoteSet(id: "
        "$id) {\n    update(data: $data) {\n      id\n      name\n      __typename\n    }\n    "
        "__typename\n  }\n}",
        "variables": {
            "data": {
                "origins": origins,
            },
            "id": emote_set_id,
        },
    }

    async with session.post("https://7tv.io/v3/gql", json=json, headers=headers) as response:
        return await response.json()


async def change_emote_in_set(session, set_id: str, emote_id: str, name: str, action="ADD"):
    json = {
        "operationName": "ChangeEmoteInSet",
        "query": "mutation ChangeEmoteInSet($id: ObjectID!, $action: ListItemAction!, $emote_id: "
        "ObjectID!, $name: String) {\n  emoteSet(id: $id) {\n    id\n    emotes(id: $emote_id, "
        "action: $action, name: $name) {\n      id\n      name\n      __typename\n    }\n    "
        "__typename\n  }\n}",
        "variables": {
            "action": action,
            "id": set_id,
            "emote_id": emote_id,
            "name": name,
        },
    }

    async with session.post("https://7tv.io/v3/gql", json=json, headers=headers) as response:
        return await response.json()


async def get_emote_set(session, emote_set_id: str):
    json = {
        "operationName": "GetEmoteSet",
        "query": "query GetEmoteSet($id: ObjectID!, $formats: [ImageFormat!]) {\n  emoteSet(id: $id) {\n    "
        "id\n    name\n    capacity\n    origins {\n      id\n      weight\n      __typename\n    "
        "}\n    emotes {\n      id\n      name\n      actor {\n        id\n        display_name\n    "
        "    avatar_url\n        __typename\n      }\n      origin_id\n      data {\n        id\n    "
        "    name\n        flags\n        listed\n        lifecycle\n        host {\n          url\n "
        "         files(formats: $formats) {\n            name\n            format\n            "
        "__typename\n          }\n          __typename\n        }\n        owner {\n          id\n   "
        "       display_name\n          style {\n            color\n            __typename\n         "
        " }\n          roles\n          __typename\n        }\n        __typename\n      }\n      "
        "__typename\n    }\n    owner {\n      id\n      username\n      display_name\n      style {"
        "\n        color\n        __typename\n      }\n      avatar_url\n      roles\n      "
        "connections {\n        id\n        display_name\n        emote_capacity\n        platform\n "
        "       __typename\n      }\n      __typename\n    }\n    __typename\n  }\n}",
        "variables": {"id": emote_set_id},
    }

    async with session.post("https://7tv.io/v3/gql", json=json, headers=headers) as response:
        return await response.json()


async def get_user_emote_sets(session, stv_id: str):
    json = {
        "operationName": "GetUserEmoteSets",
        "query": "query GetUserEmoteSets($id: ObjectID!) {\n  user(id: $id) {\n    id\n    emote_sets {\n      id\n   "
        "   name\n      capacity\n      emote_count\n      origins {\n        id\n        weight\n        "
        "__typename\n      }\n      owner {\n        id\n        display_name\n        style {\n          "
        "color\n          __typename\n        }\n        avatar_url\n        connections {\n          id\n   "
        "       emote_capacity\n          emote_set_id\n          platform\n          display_name\n         "
        " __typename\n        }\n        __typename\n      }\n      __typename\n    }\n    __typename\n  "
        "}\n}",
        "variables": {"id": stv_id},
    }

    async with session.post("https://7tv.io/v3/gql", json=json, headers=headers) as response:
        return await response.json()


class SevenTV(Cog):
    def __init__(self, bot):
        self.bot = bot
        self.stv_ids: dict[str:str] = {}

        self.update_editors.start(stop_on_error=False)

    @command(
        name="7add",
        cooldown={"per": 0, "gen": 5},
        aliases=["7del", "7alias", "7editor", "7dele"],
        description="Редактирование 7TV смайлов и управление редакторами. Полное описание - https://vk.cc/cjGqPg ",
        flags=["whitelist", "7tv-editor"],
    )
    async def command(self, ctx: Context):
        if ctx.channel.name not in self.stv_ids:
            await ctx.reply(
                "Боту необходима редакторка 7TV для работы этой команды. Если редакторка выдана, команда заработает в течение 5 минут"
            )
            return

        if ctx.command_alias == "7add":
            await self.add(ctx)
        elif ctx.command_alias == "7del":
            await self.delete(ctx)
        elif ctx.command_alias == "7alias":
            await self.alias(ctx)
        elif ctx.command_alias in ("7editor", "7dele") and (
            ctx.author.is_broadcaster
            or self.bot.stv_editors[ctx.author.name] in (81, 255)
            or ctx.author.name == self.bot.admin
        ):
            await self.manage_editors(ctx, ctx.command_alias == "7editor")
        else:
            await ctx.reply("У вас недостаточно прав для управления редакторами")

    async def add(self, ctx: Context):
        if not ctx.content:
            await ctx.reply("Введите название смайла")
            return

        ctx.content.replace("#", "")

        content_split = ctx.content.split()
        exact = "exact" in content_split
        if exact:
            content_split.remove("exact")

        emote_id = content_split[0].split("/")[-1] if "7tv.app/" in content_split[0] else None

        other_channel = alias = tags = None
        emotes = []
        if "from" in content_split:
            if emote_id:
                await ctx.reply("Укажите названия смайлов с указанного канала")
                return

            index = content_split.index("from")
            if not index:
                await ctx.reply('Введите названия смайлов перед "from"')
                return

            emotes = set(content_split[:index])
            try:
                other_channel = content_split[index + 1]
            except IndexError:
                await ctx.reply('Введите логин канала после "from"')
                return

            if len(content_split) > index + 2 and content_split[index + 2] == "as":
                if len(emotes) > 1:
                    await ctx.reply("Элиас можно указывать только про копировании одного смайла")
                    return

                alias = content_split[index + 3]
        else:
            index = content_split.index("as") if "as" in content_split else len(content_split)
            tags = (
                content_split[1:index]
                if (("as" in content_split and index != 1) or ("as" not in content_split))
                and (("to" in content_split and index != 1) or ("to" not in content_split))
                else None
            )
            tags = {tag.lower() for tag in tags} if tags else None

            if "as" in content_split:
                try:
                    alias = content_split[content_split.index("as") + 1]
                except IndexError:
                    await ctx.reply("Укажите элиас")
                    return

        emote_set_name = None
        if "to" in content_split:
            emote_set_name = " ".join(content_split[content_split.index("to") + 1 :])
            if not emote_set_name:
                await ctx.reply("Укажите название набора")
                return

        if alias and not re.match(r"^[-_A-Za-z(!?&)$+:0-9]{2,100}$", alias):
            await ctx.reply("Недопустимый элиас")
            return

        async with aiohttp.ClientSession() as session:

            if other_channel:
                try:
                    if emote_set_name:
                        emote_sets, other_channel = await asyncio.gather(
                            get_user_emote_sets(session, self.stv_ids[ctx.channel.name]),
                            self.bot.fetch_users(names=[other_channel]),
                        )
                    else:
                        stv_message_channel, other_channel = await asyncio.gather(
                            get_stv_user_gql(session, self.stv_ids[ctx.channel.name]),
                            self.bot.fetch_users(names=[other_channel]),
                        )
                except twitchio.HTTPException:
                    await ctx.reply(f'Некорректный никнейм - "{other_channel}"')
                    return
                if not other_channel:
                    await ctx.reply(f'Канал не найден - "{other_channel}"')
                    return
                other_channel = other_channel[0]
            else:
                if emote_set_name:
                    emote_sets = await get_user_emote_sets(session, self.stv_ids[ctx.channel.name])
                else:
                    stv_message_channel = await get_stv_user_gql(session, self.stv_ids[ctx.channel.name])

            if emote_set_name:
                emote_set_id = [
                    emote_set["id"]
                    for emote_set in emote_sets["data"]["user"]["emote_sets"]
                    if emote_set["name"].lower() == emote_set_name.lower()
                ]
                if not emote_set_id:
                    await ctx.reply(f'Набор "{emote_set_name}" не найден')
                    return
                emote_set_id = emote_set_id[0]
            else:
                emote_set_id = [
                    connection["emote_set_id"]
                    for connection in stv_message_channel["data"]["user"]["connections"]
                    if connection["platform"] == "TWITCH"
                ][0]

            added_emotes, emotes_count, errors = [], len(emotes), set()

            if other_channel:
                emote_set, stv_other_channel = await asyncio.gather(
                    get_emote_set(session, emote_set_id), get_stv_user(session, other_channel.id)
                )

                if stv_other_channel.get("status_code") == 404:
                    await ctx.reply("Указанный канал не подключён к 7TV")
                    return

                emotes = [
                    {"id": e["id"], "name": e["name"]}
                    for e in stv_other_channel["emote_set"]["emotes"]
                    if e["name"] in emotes
                ]

                if emotes_count != len(emotes):
                    errors.add("смайл не найден")
            else:
                if emote_id:

                    async def get_emote():
                        json = {
                            "operationName": "Emote",
                            "query": "query Emote($id: ObjectID!) {\n  emote(id: $id) {\n    id\n    created_at\n    "
                            "name\n    lifecycle\n    listed\n    trending\n    tags\n    owner {\n      id\n    "
                            "  username\n      display_name\n      avatar_url\n      style {\n        color\n    "
                            "    paint_id\n        __typename\n      }\n      __typename\n    }\n    flags\n    "
                            "host {\n      url\n      __typename\n    }\n    versions {\n      id\n      name\n  "
                            "    description\n      created_at\n      lifecycle\n      listed\n      host {\n    "
                            "    url\n        files {\n          name\n          format\n          width\n       "
                            "   height\n          size\n          __typename\n        }\n        __typename\n    "
                            "  }\n      __typename\n    }\n    animated\n    __typename\n  }\n}",
                            "variables": {"id": emote_id},
                        }

                        async with session.post("https://7tv.io/v3/gql", json=json) as response:
                            return await response.json()

                    emote_set, emote = await asyncio.gather(get_emote_set(session, emote_set_id), get_emote())
                    if "errors" in emote:
                        await ctx.reply("Смайл не найден")
                        return

                    emote = emote["data"]["emote"]

                else:

                    async def search_emote():
                        json = {
                            "operationName": "SearchEmotes",
                            "query": "query SearchEmotes($query: String!, $page: Int, $sort: Sort, $limit: Int, $filter: "
                            "EmoteSearchFilter) {\n  emotes(query: $query, page: $page, sort: $sort, "
                            "limit: $limit, filter: $filter) {\n    count\n    items {\n      id\n      tags\n      name\n   "
                            "   listed\n      trending\n      owner {\n        id\n        username\n        "
                            "display_name\n        style {\n          color\n          __typename\n        }\n   "
                            "     __typename\n      }\n      flags\n      host {\n        url\n        files {\n "
                            "         name\n          format\n          width\n          height\n          "
                            "__typename\n        }\n        __typename\n      }\n      __typename\n    }\n    "
                            "__typename\n  }\n}",
                            "variables": {
                                "query": content_split[0],
                                "sort": {"value": "popularity", "order": "DESCENDING"},
                                "filter": {
                                    "category": "TOP",
                                    "exact_match": exact,
                                    "case_sensitive": exact,
                                    "ignore_tags": False,
                                    "zero_width": False,
                                    "animated": False,
                                    "aspect_ratio": "",
                                },
                            },
                        }

                        async with session.post("https://7tv.io/v3/gql", json=json) as response:
                            return await response.json()

                    emote_set, emote_search = await asyncio.gather(get_emote_set(session, emote_set_id), search_emote())

                    if not emote_search["data"]["emotes"]["count"]:
                        await ctx.reply("Смайл не найден")
                        return

                    if tags:
                        emote = None
                        for e in emote_search["data"]["emotes"]["items"]:
                            if e.get("tags") and set(e["tags"]) & tags:
                                emote = e
                                break

                        if not emote:
                            await ctx.reply("Смайл с указанными тегами не найден")
                            return
                    else:
                        emote = emote_search["data"]["emotes"]["items"][0]

                for e in emote_set["data"]["emoteSet"]["emotes"]:
                    if e["name"] == (alias or emote["name"]):
                        await ctx.reply(f'На канале уже есть смайл с именем "{e["name"]}"')
                        return

                emotes = [emote]

            async def add_emote(emote):
                for e in emote_set["data"]["emoteSet"]["emotes"]:
                    if e["name"] == (alias or emote["name"]):
                        errors.add("конфликт названий")
                        return

                response = await change_emote_in_set(session, emote_set_id, emote["id"], alias or emote["name"])

                if "errors" not in response:
                    added_emotes.append(emote)
                else:
                    for error in response["errors"]:
                        errors.add(error["message"])

            requests = [add_emote(emote) for emote in emotes]
            await asyncio.gather(*requests)

            if not added_emotes:
                message = f"Не удалось добавить смайл{'ы' if emotes_count > 1 else ''}"
            else:

                message = (
                    f'(7TV) Добавлен смайл "{alias or added_emotes[0]["name"]}"'
                    if len(added_emotes) == 1
                    else f"(7TV) Добавлено {len(added_emotes)} смайлов"
                )

                message = f"{message} с канала {other_channel.name}" if other_channel else message
                message = (
                    f"{message}, не добавлено {emotes_count - len(added_emotes)} смайлов"
                    if emotes_count != len(added_emotes) and emotes_count > 1
                    else message
                )
            message = (
                f"{message}, {'произошли ошибки' if len(errors) > 1 else 'произошла ошибка'}: {', '.join(errors)}"
                if errors
                else message
            )

            if "Insufficient Privilege" in message:
                await ctx.reply("Боту нужна редакторка 7TV с правами редактирования смайлов и наборов")
                return

            await ctx.reply(message)

    async def delete(self, ctx: Context):
        if not ctx.content:
            await ctx.reply("Введите названия смайлов")
            return

        deleted, errors = [], set()

        async with aiohttp.ClientSession() as session:
            stv_message_channel = await get_stv_user_gql(session, self.stv_ids[ctx.channel.name])
            emote_set_id = [
                connection["emote_set_id"]
                for connection in stv_message_channel["data"]["user"]["connections"]
                if connection["platform"] == "TWITCH"
            ][0]

            response = await get_emote_set(session, emote_set_id)

            async def delete_emote(emote):
                emote_id, origin_id = None, None
                for e in response["data"]["emoteSet"]["emotes"]:
                    if e["name"] == emote:
                        emote_id = e["id"]
                        origin_id = e.get("origin_id")

                if not emote_id:
                    return

                resp = await change_emote_in_set(session, origin_id or emote_set_id, emote_id, emote, "REMOVE")

                if "errors" not in resp:
                    deleted.append(emote)
                else:
                    for error in resp["errors"]:
                        errors.add(error["message"])

            requests = [delete_emote(emote) for emote in ctx.content.split()]

            await asyncio.gather(*requests)

        if not deleted:
            if errors:
                message = f"Не удалось удалить смайл, произошли ошибки : {', '.join(errors)}"
                if "Insufficient Privilege" in message:
                    await ctx.reply("Боту нужна редакторка 7TV с правами редактирования смайлов и наборов")
                    return

                await ctx.reply(message)
                return

            message = f"{'Смайлы не найдены' if len(ctx.content.split()) > 1 else 'Смайл не найден'}"
        else:
            message = f"(7TV) Удалено {len(deleted)} смайлов" if len(deleted) > 1 else f'Удалён смайл "{deleted[0]}"'
            message = (
                f"{message}, {'произошли ошибки' if len(errors) > 1 else 'произошла ошибка'}: {', '.join(errors)}"
                if errors
                else message
            )

        await ctx.reply(message)

    async def alias(self, ctx: Context):
        try:
            name, alias = ctx.content.split()
        except ValueError:
            await ctx.reply("Введите название смайла и элиас")
            return

        errors = set()
        async with aiohttp.ClientSession() as session:
            stv_message_channel = await get_stv_user_gql(session, self.stv_ids[ctx.channel.name])
            emote_set_id = [
                connection["emote_set_id"]
                for connection in stv_message_channel["data"]["user"]["connections"]
                if connection["platform"] == "TWITCH"
            ][0]

            emote_set = await get_emote_set(session, emote_set_id)

            emote_id, origin_id = None, None
            for e in emote_set["data"]["emoteSet"]["emotes"]:
                if e["name"] == name:
                    emote_id = e["id"]
                    origin_id = e.get("origin_id")

            if not emote_id:
                await ctx.reply(f'Смайл "{name}" не найден')
                return

            for e in emote_set["data"]["emoteSet"]["emotes"]:
                if e["name"] == alias and (e.get("origin_id") or not origin_id):
                    await ctx.reply(f'На канале уже есть смайл с именем "{alias}"')
                    return

            if not re.match(r"^[-_A-Za-z(!?&)$+:0-9]{2,100}$", alias):
                await ctx.reply("Недопустимый элиас")
                return

            if emote_set["data"]["emoteSet"]["origins"] and not origin_id:
                response = await update_emote_set(session, [], emote_set_id)

                if "errors" in response:
                    for error in response["errors"]:
                        errors.add(error)

            resp = await change_emote_in_set(session, origin_id or emote_set_id, emote_id, alias, "UPDATE")

            if emote_set["data"]["emoteSet"]["origins"] and not origin_id:
                origins = [
                    {"id": origin["id"], "weight": origin["weight"]}
                    for origin in emote_set["data"]["emoteSet"]["origins"]
                ]
                r = await update_emote_set(session, origins, emote_set_id)

                for error in r.get("errors", []):
                    errors.add(error["message"])

            for error in resp.get("errors", []):
                errors.add(error["message"])

        if errors:
            message = f"Не удалось изменить название, {'произошли ошибки' if len(errors) > 1 else 'произошла ошибка'}: {', '.join(errors)}"
            if "Insufficient Privilege" in message:
                await ctx.reply("Боту нужна редакторка 7TV с правами редактирования смайлов и наборов")
                return

            await ctx.reply(message)
            return

        await ctx.reply(f'(7TV) Смайл "{name}" переименован в "{alias}"')

    async def manage_editors(self, ctx: Context, add=None):
        if not ctx.content:
            await ctx.reply(f"Введите никнейм {'будущего' if add else ''} редактора")
            return

        login = ctx.content.lstrip("@").rstrip(",").lower()

        if login == self.bot.nick and not add:
            await ctx.reply("NOIDONTTHINKSO")
            return

        try:
            user = await self.bot.fetch_users(names=[login])
        except twitchio.HTTPException:
            await ctx.reply(f'Некорректный никнейм - "{login}"')
            return

        if not user:
            await ctx.reply(f'Пользователь не найден - "{login}"')
            return

        user = user[0]

        async with aiohttp.ClientSession() as session:
            stv_user, message_channel = await asyncio.gather(
                get_stv_user(session, user.id), get_stv_user_gql(session, self.stv_ids[ctx.channel.name])
            )

            if stv_user.get("status_code") == 404:
                await ctx.reply("Указанный пользователь не подключён к 7TV")
                return

            editors = [editor["user"]["username"] for editor in message_channel["data"]["user"]["editors"]]
            if add and user.name in editors:
                await ctx.reply("Этот пользователь уже редактор")
                return
            if not add and user.name not in editors:
                await ctx.reply("У этого пользователя нет редакторки")
                return

            json = {
                "operationName": "UpdateUserEditors",
                "query": "mutation UpdateUserEditors($id: ObjectID!, $editor_id: ObjectID!, $d: UserEditorUpdate!) {"
                "\n  user(id: $id) {\n    editors(editor_id: $editor_id, data: $d) {\n      id\n      "
                "visible\n      user {\n        id\n        username\n        display_name\n        style {"
                "\n          color\n          __typename\n        }\n        roles\n        avatar_url\n     "
                "   __typename\n      }\n      added_at\n      permissions\n      __typename\n    }\n    "
                "__typename\n  }\n}",
                "variables": {
                    "d": {
                        "permissions": 17 if add else 0,
                    },
                    "editor_id": stv_user["user"]["id"],
                    "id": self.stv_ids[ctx.channel.name],
                },
            }

            async with session.post("https://7tv.io/v3/gql", json=json, headers=headers) as response:
                response = await response.json()

            if "errors" in response:
                if "Insufficient Privilege" in response["errors"][0]["message"]:
                    await ctx.reply("Боту нужна редакторка 7TV с правами управления редакторами")
                else:
                    errors = "; ".join([error["message"] for error in response["errors"]])
                    await ctx.reply(
                        f"{'произошли ошибки' if len(response['errors']) > 1 else 'произошла ошибка'}: {errors}"
                    )
                return

            if add:
                if ctx.channel.name not in self.bot.stv_editors:
                    self.bot.stv_editors[ctx.channel.name] = {user.name: 17}
                elif user.name not in self.bot.stv_editors[ctx.channel.name]:
                    self.bot.stv_editors[ctx.channel.name][user.name] = 17
            else:
                self.bot.stv_editors[ctx.channel.name].pop(user.name, None)

            await ctx.reply(f"(7TV) {'Добавлен' if add else 'Удалён'} редактор {user.display_name}")

    @routine(minutes=5)
    async def update_editors(self):
        async with aiohttp.ClientSession() as session:
            json = {
                "operationName": "GetCurrentUser",
                "query": "query GetCurrentUser {\n  user: actor {\n    id\n    username\n    display_name\n    "
                "created_at\n    avatar_url\n    style {\n      color\n      paint_id\n      __typename\n    "
                "}\n    biography\n    inbox_unread_count\n    editor_of {\n      id\n      permissions\n    "
                "  user {\n        emote_sets {\n          id\n          __typename\n        }\n        "
                "connections {\n          id\n          display_name\n          platform\n          "
                "emote_capacity\n          emote_set_id\n          __typename\n        }\n        "
                "__typename\n      }\n      __typename\n    }\n    roles\n    emote_sets {\n      id\n      "
                "name\n      capacity\n      emotes {\n        id\n        name\n        data {\n          "
                "name\n          __typename\n        }\n        __typename\n      }\n      owner {\n        "
                "id\n        display_name\n        style {\n          color\n          __typename\n        "
                "}\n        avatar_url\n        __typename\n      }\n      __typename\n    }\n    "
                "connections {\n      id\n      display_name\n      platform\n      linked_at\n      "
                "emote_capacity\n      emote_set_id\n      __typename\n    }\n    __typename\n  }\n}",
                "variables": {},
            }

            async with session.post("https://7tv.io/v3/gql", json=json, headers=headers) as response:
                response = await response.json()

            channels = config["Bot"]["channels"].split()
            stv_ids = [
                channel["id"]
                for channel in response["data"]["user"]["editor_of"]
                for connection in channel["user"]["connections"]
                if connection["platform"] == "TWITCH" and connection["display_name"].lower() in channels
            ]

            for stv_id in stv_ids:
                response = await get_stv_user_gql(session, stv_id)

                self.stv_ids[response["data"]["user"]["username"]] = stv_id
                self.bot.stv_editors[response["data"]["user"]["username"]] = {
                    editor["user"]["username"]: editor["permissions"] for editor in response["data"]["user"]["editors"]
                }
                await asyncio.sleep(2)


def prepare(bot):
    bot.add_cog(SevenTV(bot))
