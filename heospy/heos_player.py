#!/usr/bin/env python
"""
Rewritten version of heos_player from ping13.
interface & commands: http://rn.dmglobal.com/euheos/HEOS_CLI_ProtocolSpecification.pdf
"""

import os
import json
import telnetlib
import re

import logging
from typing import Optional, Sequence

# Simple Service Discovery Protocol (SSDP), https://gist.github.com/dankrause/6000248
from heospy import ssdp


class HeosPlayerConfigException(Exception):
    pass


class HeosPlayerGeneralException(Exception):
    pass


class HeosPlayer(object):
    """
    Representation of an HEOS player with a specific player id.
    This needs a JSON config file with a minimal content:
    {
    "player_name": "Heos",
    "user": "me@example.com",
    "pw": "do-not-use-qwerty-as-password"
    }
    """

    URN_SCHEMA: str = "urn:schemas-denon-com:device:ACT-Denon:1"
    heosurl: str = 'heos://'

    config_file: str
    player_name: str
    user: str
    pw: str
    login: tuple
    host: str
    pid: str

    telnet: object
    _timeout: int = 15

    def __init__(self, rediscover: bool=False,
                 config_file: str =os.path.join(os.getcwd(), 'config.json')):
        """Initialize HEOS player."""

        try:
            with open(config_file) as json_data_file:
                config = json.load(json_data_file)
        except IOError:
            error_msg = "cannot read your config file '{}'".format(config_file)
            logging.error(error_msg)
            raise HeosPlayerConfigException(error_msg)

        logging.debug("config file recognized: '{}'".format(config_file))

        self.host = config.get("host")
        self.pid = config.get("pid")
        self.player_name = config.get(
            "player_name", config.get("main_player_name"))
        self.config_file = config_file

        if self.player_name is None:
            logging.warn("No player name given.")
            raise HeosPlayerGeneralException("No player name given.")

        # if host and pid is not known, detect the first HEOS device.
        if rediscover or (not self.host or not self.pid):
            logging.info("Starting to discover your HEOS player '{}' in your local network".format(
                self.player_name))
            ssdp_list: list = ssdp.discover(self.URN_SCHEMA)
            logging.debug("found {} possible hosts: {}".format(
                len(ssdp_list), ssdp_list))

            self.telnet = None
            for response in ssdp_list:
                if response.st == self.URN_SCHEMA:
                    try:
                        self.host = re.match(
                            r"http:..([^\:]+):", response.location).group(1)
                        logging.debug("Testing host '{}'".format(self.host))

                        self.telnet = telnetlib.Telnet(self.host, 1255)
                        logging.debug("Telnet '{}'".format(self.telnet))

                        self.pid = self._get_player(self.player_name)
                        logging.debug("pid '{}'".format(self.pid))

                        if self.pid:
                            self.player_name = config.get(
                                "player_name", config.get("main_player_name"))
                            logging.info(
                                "Found '{}' in your local network".format(self.player_name))
                            break
                    except Exception as e:
                        logging.error(e)
                        pass

            if self.telnet == None:
                msg = "couldn't discover any HEOS player with Simple Service Discovery Protocol (SSDP)."
                logging.error(msg)
                raise HeosPlayerGeneralException(msg)

        else:
            logging.info("My cache says your HEOS player '{}' is at {}".format(self.player_name,
                                                                               self.host))
            try:
                self.telnet = telnetlib.Telnet(
                    self.host, 1255, timeout=self._timeout)
            except Exception as e:
                raise HeosPlayerGeneralException("telnet failed")

        # check if we've found what we were looking for
        if self.host is None:
            logging.error("No HEOS player found in your local network")
        elif self.pid is None:
            logging.error(
                "No player with name '{}' found!".format(self.player_name))
        else:
            if self.login(user=config.get("user"),
                          pw=config.get("pw")):
                self.user = config.get("user")

        # save config
        if (rediscover or config.get("pid") is None) and self.host and self.pid:
            logging.info("Save host and pid in {}".format(config_file))
            config["pid"] = self.pid
            config["host"] = self.host
            with open(os.path.join(self.config_file), "w") as json_data_file:
                json.dump(config, json_data_file, indent=2)

    def __repr__(self):
        return "<HeosPlayer({player_name}, {user}, {host}, {pid})>".format(**self.__dict__)

    def telnet_request(self, command, wait=True):
        """Execute a `command` and return the response(s)."""
        command = self.heosurl + command
        logging.debug("telnet request {}".format(command))
        self.telnet.write(command.encode('ascii') + b'\n')
        response = b''
        logging.debug("starting response loop")
        while True:
            response += self.telnet.read_some()
            try:
                response = json.loads(response.decode("utf-8"))
                logging.debug("found valid JSON: {}".format(
                    json.dumps(response)))
                if not wait:
                    logging.debug(
                        "I accept the first response: {}".format(response))
                    break
                # sometimes, I get a response with the message "under
                # process". I might want to wait here
                message = response.get("heos", {}).get("message", "")
                if "command under process" not in message:
                    logging.debug(
                        "I assume this is the final response: {}".format(response))
                    break
                logging.debug("Wait for the final response")
                response = b''  # forget this message
            except ValueError:
                logging.debug("... unfinished response: {}".format(response))
                # response is not a complete JSON object
                pass
            except TypeError:
                logging.debug("... unfinished response: {}".format(response))
                # response is not a complete JSON object
                pass
        if response.get("result") == "fail":
            logging.warn(response)
            return None

        logging.debug("found valid response: {}".format(json.dumps(response)))
        return response

    def _get_groups_players(self):
        groups = self.telnet_request("player/get_groups").get("payload")
        players = self.telnet_request("player/get_players").get("payload")
        return {"players": players, "groups": groups}

    def _get_player(self, name):
        response = self.telnet_request("player/get_players")
        if response.get("payload") is None:
            return None
        for player in response.get("payload"):
            logging.debug(u"found '{}', looking for '{}'".format(
                player.get("name"), name))
            if player.get("name") == name:
                return player.get("pid")
        return None
