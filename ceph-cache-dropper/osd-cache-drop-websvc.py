# cherrypy script to let http clients request Ceph OSD cache drop
# to use, do HTTP GET on URL http://ip:port/DropOSDCache
# this script depends on the availability of the /usr/bin/ceph command 
# and ceph environment setup (see /usr/local/bin/toolbox.sh)

import subprocess
import atexit
import traceback
import cherrypy
import logging
from os import getenv
from os.path import exists

notok = 1   # process exit status

# script to watch for changes to monitor list and update
# comes from RHCS image

toolbox_watch_mons_script = '/usr/local/bin/toolbox.sh'

def flush_log():
    logging.shutdown()

atexit.register(flush_log)


# implements web server for URL DropOSDCache/

class DropOSDCache(object):
    @cherrypy.expose
    def DropOSDCache(self):
        try:
            cherrypy.log('received cache drop request')
            result = subprocess.check_output(
                ["/usr/bin/python3", "/usr/bin/ceph", "tell", "osd.*", "cache", "drop"], 
                timeout=cache_drop_timeout)
            cherrypy.log(result.decode())
        except subprocess.CalledProcessError as e:
            cherrypy.log('ERROR: failed to drop cache')
            cherrypy.log(str(e))
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


# parse environment variables if present

port = int(getenv("ceph_cache_drop_port", "9437"))
cherrypy.log('ceph cache drop port = %d' % port)

cache_drop_timeout = int(getenv('ceph_cache_drop_timeout', '120'))
cherrypy.log('cache drop timeout = %d sec' % cache_drop_timeout)

# keep list of monitors up to date in case monitors ever move
# this is a best-effort attempt but it might not succeed

if not exists(toolbox_watch_mons_script):
    cherrypy.log('WARNING: cannot react to changes in monitor list')

try:
    result_fd = subprocess.Popen(
        ["/bin/sh", "-c", "/usr/local/bin/toolbox.sh"])
except Exception:
    cherrypy.log('ERROR: failed to source toolbox')
    traceback.print_exc()
    sys.exit(notok)

startCherryPy()
