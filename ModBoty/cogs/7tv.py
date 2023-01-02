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


def conv(n: int) -> str:
    """Converts a number to an ending for the word 'смайл' in Russian"""
    endings = ["а", "ов", ""]
    n %= 100
    if 5 <= n <= 20:
        s = endings[1]
    else:
        i = n % 10
        if i == 1:
            s = endings[2]
        elif i in [2, 3, 4]:
            s = endings[0]
        else:
            s = endings[1]
    return s


class SevenTV(Cog):
    def __init__(self, bot):
        self.bot = bot
        self.stv_ids: dict[str:str] = {}

        self.update_editors.start(stop_on_error=False)

    @command(
        name="7add",
        cooldown={"per": 0, "gen": 5},
        aliases=["7del", "7alias", "7editor", "7set", "7origin"],
        description="Редактирование 7TV смайлов и управление редакторами. Полное описание ‒ https://vk.cc/cjGqPg ",
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
        elif ctx.command_alias == "7set":
            await self.set(ctx)
        elif ctx.command_alias == "7origin":
            await self.origin(ctx)
        elif ctx.command_alias == "7editor" and (
            ctx.author.is_broadcaster
            or self.bot.stv_editors[ctx.author.name] in (81, 255)
            or ctx.author.name == self.bot.admin
        ):
            await self.editor(ctx)
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
        emote_names = set()

        if "from" in content_split:
            if emote_id:
                await ctx.reply("Укажите названия смайлов с указанного канала")
                return

            index = content_split.index("from")
            if not index:
                await ctx.reply('Введите названия смайлов перед "from"')
                return

            emote_names = set(content_split[:index])
            try:
                other_channel = content_split[index + 1]
            except IndexError:
                await ctx.reply('Введите логин канала после "from"')
                return

            if len(content_split) > index + 2 and content_split[index + 2] == "as":
                if len(emote_names) > 1:
                    await ctx.reply("Элиас можно указывать только про копировании одного смайла")
                    return

                alias = content_split[index + 3]
        else:
            try:
                index = content_split.index("as") if "as" in content_split else content_split.index("to")
            except ValueError:
                index = 0

            tags = (
                {tag.lower() for tag in content_split[1:index]}
                if (("as" in content_split and index != 1) or ("as" not in content_split))
                and (("to" in content_split and index != 1) or ("to" not in content_split))
                else None
            )

            if "as" in content_split:
                try:
                    alias = content_split[content_split.index("as") + 1]
                except IndexError:
                    await ctx.reply("Укажите элиас")
                    return

        emote_set_name = None
        if "to" in content_split:
            emote_set_name = " ".join(content_split[content_split.index("to") + 1 :]).lower()
            if not emote_set_name:
                await ctx.reply("Укажите название набора")
                return

        if alias and not re.match(r"^[-_A-Za-z(!?&)$+:0-9]{2,100}$", alias):
            await ctx.reply("Недопустимый элиас")
            return

        if other_channel:
            try:
                if emote_set_name:
                    emote_sets, other_channel = await asyncio.gather(
                        get_user_emote_sets(self.bot.session, self.stv_ids[ctx.channel.name]),
                        self.bot.fetch_users(names=[other_channel]),
                    )
                else:
                    stv_message_channel, other_channel = await asyncio.gather(
                        get_stv_user_gql(self.bot.session, self.stv_ids[ctx.channel.name]),
                        self.bot.fetch_users(names=[other_channel]),
                    )
            except twitchio.HTTPException:
                await ctx.reply(f'Некорректный никнейм ‒ "{other_channel}"')
                return
            if not other_channel:
                await ctx.reply(f'Канал не найден‒"{other_channel}"')
                return
            other_channel = other_channel[0]
        else:
            if emote_set_name:
                emote_sets = await get_user_emote_sets(self.bot.session, self.stv_ids[ctx.channel.name])
            else:
                stv_message_channel = await get_stv_user_gql(self.bot.session, self.stv_ids[ctx.channel.name])

        if emote_set_name:
            emote_set_id = [
                emote_set["id"]
                for emote_set in emote_sets["data"]["user"]["emote_sets"]
                if emote_set["name"].lower() == emote_set_name
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

        added_emotes, errors = [], set()

        if other_channel:
            emote_set, stv_other_channel = await asyncio.gather(
                get_emote_set(self.bot.session, emote_set_id), get_stv_user(self.bot.session, other_channel.id)
            )

            if stv_other_channel.get("status_code") == 404:
                await ctx.reply("Указанный канал не подключён к 7TV")
                return

            emotes = [
                {"id": e["id"], "name": e["name"]}
                for e in stv_other_channel["emote_set"]["emotes"]
                if e["name"] in emote_names
            ]

            if len(emote_names) != len(emotes):
                if len(emote_names) - len(emotes) == 1:
                    errors.add("смайл не найден")
                else:
                    errors.add("смайлы не найдены")
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

                    async with self.bot.session.post("https://7tv.io/v3/gql", json=json) as response:
                        return await response.json()

                emote_set, emote = await asyncio.gather(get_emote_set(self.bot.session, emote_set_id), get_emote())
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
                            "limit": 1000,
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

                    async with self.bot.session.post("https://7tv.io/v3/gql", json=json) as response:
                        return await response.json()

                emote_set, emote_search = await asyncio.gather(
                    get_emote_set(self.bot.session, emote_set_id), search_emote()
                )

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

            response = await change_emote_in_set(self.bot.session, emote_set_id, emote["id"], alias or emote["name"])

            if "errors" not in response:
                added_emotes.append(emote["name"])
            else:
                for error in response["errors"]:
                    if "No Space Available" in error["message"]:
                        errors.add("недостаточно слотов")
                    elif "Emote Already Enabled" in error["message"]:
                        if "смайл уже добавлен" not in errors and "смайлы уже добавлены" not in errors:
                            errors.add("смайл уже добавлен")
                        elif "смайлы уже добавлены" not in errors:
                            errors.remove("смайл уже добавлен")
                            errors.add("смайлы уже добавлены")
                    else:
                        errors.add(error["message"])

        requests = [add_emote(emote) for emote in emotes]
        await asyncio.gather(*requests)

        if not added_emotes:
            message = f"Не удалось добавить смайл{'ы' if len(emote_names) > 1 else ''}"
        else:

            message = (
                f'(7TV) Добавлен смайл "{alias or added_emotes[0]}"'
                if len(added_emotes) == 1
                else f"(7TV) Добавлен{'о' if conv(len(added_emotes)) != '' else ''} {len(added_emotes)} смайл{conv(len(added_emotes))}"
            )

            message = f"{message} с канала {other_channel.name}" if other_channel else message
            message = (
                f"{message}, не удалось добавить {', '.join(emote_names - set(added_emotes))}"
                if len(emote_names) != len(added_emotes) and len(emote_names) > 1
                else message
            )
        message = f"{message} ‒ {'; '.join(errors)}" if errors else message

        if "Insufficient Privilege" in message:
            await ctx.reply("Боту нужна редакторка 7TV с правами редактирования смайлов и наборов")
            return

        await ctx.reply(message)

    async def delete(self, ctx: Context):
        if not ctx.content:
            await ctx.reply("Введите названия смайлов")
            return

        deleted, errors = [], set()
        emotes = set(ctx.content.split())

        stv_message_channel = await get_stv_user_gql(self.bot.session, self.stv_ids[ctx.channel.name])
        emote_set_id = [
            connection["emote_set_id"]
            for connection in stv_message_channel["data"]["user"]["connections"]
            if connection["platform"] == "TWITCH"
        ][0]

        response = await get_emote_set(self.bot.session, emote_set_id)

        async def delete_emote(emote):
            emote_id, origin_id = None, None
            for e in response["data"]["emoteSet"]["emotes"]:
                if e["name"] == emote:
                    emote_id = e["id"]
                    origin_id = e.get("origin_id")

            if not emote_id:
                if "смайл не найден" not in errors and "смайлы не найдены" not in errors:
                    errors.add("смайл не найден")
                elif "смайлы не найдены" not in errors:
                    errors.remove("смайл не найден")
                    errors.add("смайлы не найдены")
                return

            resp = await change_emote_in_set(self.bot.session, origin_id or emote_set_id, emote_id, emote, "REMOVE")

            if "errors" not in resp:
                deleted.append(emote)
            else:
                for error in resp["errors"]:
                    errors.add(error["message"])

        requests = [delete_emote(emote) for emote in emotes]
        await asyncio.gather(*requests)

        if not deleted:
            message = f"Не удалось выполнить команду ‒ {'; '.join(errors)}"
            if "Insufficient Privilege" in message:
                message = "Боту нужна редакторка 7TV с правами редактирования смайлов и наборов"

            await ctx.reply(message)
            return
        else:
            message = (
                f"(7TV) Удал{'ено' if conv(len(deleted)) != '' else 'ён'} {len(deleted)} смайл{conv(len(deleted))}"
                if len(deleted) > 1
                else f'Удалён смайл "{deleted[0]}"'
            )
            message = (
                f"{message}, не удалось удалить {', '.join(emotes - set(deleted))}"
                if len(emotes) != len(deleted)
                else message
            )

            message = f"{message} ‒ {'; '.join(errors)}" if errors else message

        await ctx.reply(message)

    async def alias(self, ctx: Context):
        try:
            name, alias = ctx.content.split()
        except ValueError:
            await ctx.reply("Введите название смайла и элиас")
            return

        errors = set()
        stv_message_channel = await get_stv_user_gql(self.bot.session, self.stv_ids[ctx.channel.name])
        emote_set_id = [
            connection["emote_set_id"]
            for connection in stv_message_channel["data"]["user"]["connections"]
            if connection["platform"] == "TWITCH"
        ][0]

        emote_set = await get_emote_set(self.bot.session, emote_set_id)

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

        # removing origins if emote has no origin because of 7tv behaviour
        if emote_set["data"]["emoteSet"]["origins"] and not origin_id:
            response = await update_emote_set(self.bot.session, [], emote_set_id)

            if "errors" in response:
                for error in response["errors"]:
                    errors.add(error)

        resp = await change_emote_in_set(self.bot.session, origin_id or emote_set_id, emote_id, alias, "UPDATE")

        # return origins if emote has no origin
        if emote_set["data"]["emoteSet"]["origins"] and not origin_id:
            origins = [
                {"id": origin["id"], "weight": origin["weight"]} for origin in emote_set["data"]["emoteSet"]["origins"]
            ]
            r = await update_emote_set(self.bot.session, origins, emote_set_id)

            for error in r.get("errors", []):
                errors.add(error["message"])

        for error in resp.get("errors", []):
            errors.add(error["message"])

        if errors:
            message = f"Не удалось изменить название ‒ {'; '.join(errors)}"
            if "Insufficient Privilege" in message:
                await ctx.reply("Боту нужна редакторка 7TV с правами редактирования смайлов и наборов")
                return

            await ctx.reply(message)
            return

        await ctx.reply(f'(7TV) Смайл "{name}" переименован в "{alias}"')

    async def set(self, ctx: Context):
        if not ctx.content:
            stv_message_channel = await get_stv_user_gql(self.bot.session, self.stv_ids[ctx.channel.name])
            emote_set_id = [
                connection["emote_set_id"]
                for connection in stv_message_channel["data"]["user"]["connections"]
                if connection["platform"] == "TWITCH"
            ][0]
            emote_set = await get_emote_set(self.bot.session, emote_set_id)
            emote_set = emote_set["data"]["emoteSet"]
            if origins := emote_set["origins"]:
                requests = [get_emote_set(self.bot.session, origin["id"]) for origin in emote_set["origins"]]
                origins = await asyncio.gather(*requests)
                origins = [origin["data"]["emoteSet"]["name"] for origin in origins]

            message = (
                f"(7TV) Сейчас активен набор \"{emote_set['name']}\" со {len(emote_set['emotes'])}/"
                f"{emote_set['capacity']} слотами{', с источниками: ' + ', '.join(origins) if origins else ''}"
            )
            await ctx.reply(message)
            return

        emote_set_name = ctx.content.lower()
        emote_sets = await get_user_emote_sets(self.bot.session, self.stv_ids[ctx.channel.name])

        emote_set = [
            {"name": emote_set["name"], "id": emote_set["id"]}
            for emote_set in emote_sets["data"]["user"]["emote_sets"]
            if emote_set["name"].lower() == emote_set_name
        ]
        if not emote_set:
            await ctx.reply(f'Набор "{emote_set_name}" не найден')
            return

        current_emote_set = [
            {"conn_id": connection["id"], "id": connection["emote_set_id"]}
            for emote_set in emote_sets["data"]["user"]["emote_sets"]
            for connection in emote_set["owner"]["connections"]
            if emote_set["owner"]["display_name"].lower() == ctx.channel.name and connection["platform"] == "TWITCH"
        ]

        if current_emote_set and emote_set[0]["id"] == current_emote_set[0]["id"]:
            await ctx.reply("Этот набор уже активен")
            return

        if not current_emote_set:
            await ctx.reply("Сейчас ни один набор не активен, активируйте его вручную через 7tv.app")
            return

        json = {
            "operationName": "UpdateUserConnection",
            "query": "mutation UpdateUserConnection($id: ObjectID!, $conn_id: String!, $d: UserConnectionUpdate!) "
            "{\n  user(id: $id) {\n    connections(id: $conn_id, data: $d) {\n      id\n      platform\n "
            "     display_name\n      emote_set_id\n      __typename\n    }\n    __typename\n  }\n}",
            "variables": {
                "conn_id": current_emote_set[0]["conn_id"],
                "d": {"emote_set_id": emote_set[0]["id"]},
                "id": self.stv_ids[ctx.channel.name],
            },
        }

        async with self.bot.session.post("https://7tv.io/v3/gql", json=json, headers=headers) as response:
            response = await response.json()

        if "errors" in response:
            if "Insufficient Privilege" in response["errors"][0]["message"]:
                await ctx.reply("Боту нужна редакторка 7TV с правами редактирования 7TV смайлов и наборов")
            else:
                errors = "; ".join([error["message"] for error in response["errors"]])
                await ctx.reply(
                    f"{'Произошли ошибки' if len(response['errors']) > 1 else 'Произошла ошибка'} ‒ {errors}"
                )
            return

        await ctx.reply(f"(7TV) Активирован набор {emote_set[0]['name']}")

    async def origin(self, ctx: Context):
        if not ctx.content:
            await ctx.reply("Введите действие (add, del) и название набора")
            return

        try:
            action, set_name = ctx.content.lower().split(maxsplit=1)
        except ValueError:
            await ctx.reply("Введите действие (add, del) и название набора")
            return

        if action not in ("add", "del"):
            await ctx.reply("Введите действие (add, del) и название набора")
            return

        emote_sets = await get_user_emote_sets(self.bot.session, self.stv_ids[ctx.channel.name])

        current_emote_set = [
            {"conn_id": connection["id"], "id": connection["emote_set_id"], "name": emote_set["name"]}
            for emote_set in emote_sets["data"]["user"]["emote_sets"]
            for connection in emote_set["owner"]["connections"]
            if emote_set["owner"]["display_name"].lower() == ctx.channel.name
            and connection["platform"] == "TWITCH"
            and emote_set["id"] == connection["emote_set_id"]
        ]

        if not current_emote_set:
            await ctx.reply("Сейчас ни один набор не активен, активируйте его вручную через 7tv.app")
            return

        if current_emote_set[0]["name"].lower() == set_name:
            await ctx.reply("Нельзя добавить источник самого в себя" if "action" == "add" else "Источник не найден")
            return

        emote_sets_names = [emote_set["name"].lower() for emote_set in emote_sets["data"]["user"]["emote_sets"]]

        if set_name not in emote_sets_names:
            await ctx.reply("Набор не найден")
            return

        current_origins = [
            {"id": origin["id"], "weight": origin["weight"]}
            for emote_set in emote_sets["data"]["user"]["emote_sets"]
            for origin in emote_set["origins"]
            if emote_set["id"] == current_emote_set[0]["id"]
        ]

        current_origins_names = []

        if current_origins:
            requests = [get_emote_set(self.bot.session, origin["id"]) for origin in current_origins]
            current_origins_detailed = await asyncio.gather(*requests)

            current_origins_names = [origin["data"]["emoteSet"]["name"].lower() for origin in current_origins_detailed]

            if action == "add" and set_name in current_origins_names:
                await ctx.reply("Этот источник уже добавлен")
                return

        if action != "add" and set_name not in current_origins_names:
            await ctx.reply("Этот набор не добавлен как источик")
            return

        origin = [
            {"id": emote_set["id"], "name": emote_set["name"]}
            for emote_set in emote_sets["data"]["user"]["emote_sets"]
            if emote_set["name"].lower() == set_name
        ][0]

        if action == "add":
            origins = [{"id": origin["id"], "weight": origin["weight"]} for origin in current_origins] + [
                {"id": origin["id"], "weight": 0}
            ]
        else:
            origins = [
                {"id": origin["id"], "weight": origin["weight"]}
                for origin in current_origins
                if origin["id"] != origin["id"]
            ]
        response = await update_emote_set(self.bot.session, origins, current_emote_set[0]["id"])

        if errors := {error["message"] for error in response.get("errors", [])}:
            message = f"Не удалось {'добавить' if action == 'add' else 'удалить'} источник ‒ {'; '.join(errors)}"
            if "Insufficient Privilege" in message:
                await ctx.reply("Боту нужна редакторка 7TV с правами редактирования смайлов и наборов")
                return

            await ctx.reply(message)
            return

        message = f"(7TV) {'Добавлен' if action == 'add' else 'Удалён'} источник \"{origin['name']}\""
        await ctx.reply(message)

    async def editor(self, ctx: Context):
        if not ctx.content:
            await ctx.reply("Введите действие (add, del) и логин")
            return

        try:
            action, login = ctx.content.lower().split()
        except ValueError:
            await ctx.reply("Введите действие (add, del) и логин")
            return

        if action not in ("add", "del"):
            await ctx.reply("Введите действие (add, del) и логин")
            return

        login = login.lstrip("@").rstrip(",")

        try:
            user = await self.bot.fetch_users(names=[login])
        except twitchio.HTTPException:
            await ctx.reply(f'Некорректный никнейм ‒ "{login}"')
            return

        if not user:
            await ctx.reply(f'Пользователь не найден ‒ "{login}"')
            return

        if login == self.bot.nick and action != "add":
            await ctx.reply("NOIDONTTHINKSO")
            return

        user = user[0]

        stv_user, message_channel = await asyncio.gather(
            get_stv_user(self.bot.session, user.id), get_stv_user_gql(self.bot.session, self.stv_ids[ctx.channel.name])
        )

        if stv_user.get("status_code") == 404:
            await ctx.reply("Указанный пользователь не подключён к 7TV")
            return

        editors = [editor["user"]["username"] for editor in message_channel["data"]["user"]["editors"]]
        if action == "add" and user.name in editors:
            await ctx.reply("Этот пользователь уже редактор")
            return
        if action != "add" and user.name not in editors:
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
                    "permissions": 17 if action == "add" else 0,
                },
                "editor_id": stv_user["user"]["id"],
                "id": self.stv_ids[ctx.channel.name],
            },
        }

        async with self.bot.session.post("https://7tv.io/v3/gql", json=json, headers=headers) as response:
            response = await response.json()

        if "errors" in response:
            if "Insufficient Privilege" in response["errors"][0]["message"]:
                await ctx.reply("Боту нужна редакторка 7TV с правами управления редакторами")
            else:
                errors = "; ".join([error["message"] for error in response["errors"]])
                await ctx.reply(
                    f"{'Произошли ошибки' if len(response['errors']) > 1 else 'Произошла ошибка'} ‒ {errors}"
                )
            return

        if action == "add":
            if ctx.channel.name not in self.bot.stv_editors:
                self.bot.stv_editors[ctx.channel.name] = {user.name: 17}
            elif user.name not in self.bot.stv_editors[ctx.channel.name]:
                self.bot.stv_editors[ctx.channel.name][user.name] = 17
        else:
            self.bot.stv_editors[ctx.channel.name].pop(user.name, None)

        await ctx.reply(f"(7TV) {'Добавлен' if action == 'add' else 'Удалён'} редактор {user.display_name}")

    @routine(minutes=5)
    async def update_editors(self):
        if not self.bot.session:
            self.bot._http.session = self.bot._http.session or aiohttp.ClientSession()
            self.bot.session = self.bot._http.session

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

        async with self.bot.session.post("https://7tv.io/v3/gql", json=json, headers=headers) as response:
            response = await response.json()

        channels = config["Bot"]["channels"].split()
        stv_ids = [
            channel["id"]
            for channel in response["data"]["user"]["editor_of"]
            for connection in channel["user"]["connections"]
            if connection["platform"] == "TWITCH" and connection["display_name"].lower() in channels
        ]

        for stv_id in stv_ids:
            try:
                response = await get_stv_user_gql(self.bot.session, stv_id)
            except aiohttp.ContentTypeError:
                continue

            self.stv_ids[response["data"]["user"]["username"]] = stv_id
            self.bot.stv_editors[response["data"]["user"]["username"]] = {
                editor["user"]["username"]: editor["permissions"] for editor in response["data"]["user"]["editors"]
            }
            await asyncio.sleep(2)


def prepare(bot):
    bot.add_cog(SevenTV(bot))
