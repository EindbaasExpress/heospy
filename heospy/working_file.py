# working_file

from heospy import ssdp
import re
import telnetlib
import logging
import json

URN_SCHEMA = "urn:schemas-denon-com:device:ACT-Denon:1"
player_name = 'HEOS'
heosurl = 'heos://'
logging.basicConfig(level=logging.DEBUG)


def telnet_request(command, wait=True):
    """Execute a `command` and return the response(s)."""
    command = heosurl + command
    logging.debug("telnet request {}".format(command))
    telnet.write(command.encode('ascii') + b'\n')
    response = b''
    logging.debug("starting response loop")
    while True:
        response += telnet.read_some()
        try:
            response = json.loads(response.decode("utf-8"))
            logging.debug("found valid JSON: {}".format(json.dumps(response)))
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


def _get_player(name):
    response = telnet_request("player/get_players")
    if response.get("payload") is None:
        return None
    for player in response.get("payload"):
        logging.debug(u"found '{}', looking for '{}'".format(
            player.get("name"), name))
        if player.get("name") == name:
            return player.get("pid")
    return None


ssdp_list = ssdp.discover(URN_SCHEMA)
response = ssdp_list[0]

if (response.st == URN_SCHEMA):
    host = re.match(r"http:..([^\:]+):", response.location).group(1)
    telnet = telnetlib.Telnet(host, 1255)
    pid = _get_player(player_name)
    print(host, telnet, pid)
# logging.debug(host, telnet, pid)

telnet_request("heos://player/get_players")
telnet_request("system/heart_beat")
