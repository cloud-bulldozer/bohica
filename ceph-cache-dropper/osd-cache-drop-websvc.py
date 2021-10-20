# cherrypy script to let http clients request Ceph OSD cache drop
# to use, do HTTP GET on URL http://ip:port/DropOSDCache
# this script depends on the availability of the /usr/bin/ceph command 
# and ceph environment setup (see /usr/local/bin/toolbox.sh)

import subprocess
import atexit
import logging
import cherrypy
from os import getenv
from os.path import exists

# script to watch for changes to monitor list and update
# comes from RHCS image

toolbox_watch_mons_script = '/usr/local/bin/toolbox.sh'

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('dropcache')

def flush_log():
    logging.shutdown()

atexit.register(flush_log)

# parse environment variables if present

port_str = getenv("ceph_cache_drop_port")
if port_str == None:
    port_str = '9437'
port = int(port_str)
logger.info('ceph cache drop port = %d' % port)

cache_drop_timeout = int(getenv('ceph_cache_drop_timeout', '120'))
logger.info('cache drop timeout = %d sec' % cache_drop_timeout)


# implements web server for URL DropOSDCache/

class DropOSDCache(object):
    @cherrypy.expose
    def DropOSDCache(self):
        try:
            logger.info('received cache drop request')
            result = subprocess.check_output(
                ["/usr/bin/python3", "/usr/bin/ceph", "tell", "osd.*", "cache", "drop"], 
                timeout=cache_drop_timeout)
            logger.info(result)
        except subprocess.CalledProcessError as e:
            logger.error('failed to drop cache')
            logger.exception(e)
            return 'FAIL'
        return 'SUCCESS'

    @cherrypy.expose
    def index(self):
        return 'I am here'


# code to start up CherryPy

def startCherryPy():
  config = { 
    'global': {
        'server.socket_host': '0.0.0.0' ,
        'server.socket_port': port,
    },
  }
  cherrypy.config.update(config)
  cherrypy.quickstart(DropOSDCache())

# keep list of monitors up to date in case monitors ever move
# this is a best-effort attempt but it might not succeed

if not exists(toolbox_watch_mons_script):
    logger.warning('cannot react to changes in monitor list')

try:
    result_fd = subprocess.Popen(
        ["/bin/sh", "-c", "/usr/local/bin/toolbox.sh"])
except Exception as e:
    logger.error('failed to source toolbox')
    logger.exception(e)
    sys.exit(1)

startCherryPy()
