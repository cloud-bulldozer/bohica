# cherrypy script to let http clients request Ceph OSD cache drop
# to use, do HTTP GET on URL http://ip:port/DropOSDCache
# this script depends on the availability of the /usr/bin/ceph command 
# and ceph environment setup (see /usr/local/bin/toolbox.sh)

import subprocess
import atexit
import logging
import cherrypy
from os import getenv

logging.basicConfig(filename='/tmp/dropcache.log', level=logging.DEBUG)
logger = logging.getLogger('dropcache')
logger.setLevel(logging.INFO)

def flush_log():
    logging.shutdown()

atexit.register(flush_log)

class DropOSDCache(object):
    @cherrypy.expose
    def DropOSDCache(self):
        try:
            result = subprocess.check_output(
                ["/usr/bin/python3", "/usr/bin/ceph", "tell", "osd.*", "cache", "drop"])
            logger.info(result)
        except subprocess.CalledProcessError as e:
            logger.error('failed to drop cache')
            logger.exception(e)
            return 'FAIL'
        return 'SUCCESS'

    @cherrypy.expose
    def index(self):
        return 'I am here'

try:
    result = subprocess.Popen(
        ["/bin/sh", "-c", "/usr/local/bin/toolbox.sh"])
except subprocess.CalledProcessError as e:
    logger.error('failed to source toolbox')
    logger.exception(e)
port_str = getenv("ceph_cache_drop_port")
if port_str == None:
    port_str = '9437'
port = int(port_str)
config = { 
    'global': {
        'server.socket_host': '0.0.0.0' ,
        'server.socket_port': port,
    },
}
cherrypy.config.update(config)
cherrypy.quickstart(DropOSDCache())
